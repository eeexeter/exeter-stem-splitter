import argparse
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryFile

from models import DEFAULT_MODEL, MODEL_STEMS, MODEL_WEIGHTS, REMOVABLE_STEMS, mix_name


def status(message, *, device=None):
    update = {"status": message}
    if device is not None:
        update["device"] = device
    print(json.dumps(update), flush=True)


def load_checkpoint(checkpoint, checksum):
    import torch
    from demucs.states import load_model as restore_model

    if not checkpoint.is_file():
        raise FileNotFoundError(f"The Demucs model file {checkpoint.name} is missing. Extract the entire application archive.")
    with checkpoint.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != checksum:
            raise ValueError(f"The Demucs model file {checkpoint.name} failed its integrity check.")
        file.seek(0)
        package = torch.load(file, map_location="cpu", weights_only=True)
    return restore_model(package).eval()


def load_model(cache, model_name):
    import numpy as np
    from numpy._core.multiarray import scalar
    import torch
    from demucs.apply import BagOfModels
    from demucs.htdemucs import HTDemucs

    status("Loading the Demucs model…")
    globals_for_checkpoint = [Fraction, HTDemucs, np.dtype, np.dtypes.Float64DType,
                              (scalar, "numpy.core.multiarray.scalar")]
    with torch.serialization.safe_globals(globals_for_checkpoint):
        members = [load_checkpoint(cache / filename, checksum) for filename, checksum in MODEL_WEIGHTS[model_name]]
    if len(members) == 1:
        return members[0]
    # The official htdemucs_ft ensemble takes each source from its corresponding checkpoint.
    return BagOfModels(members, weights=np.eye(len(members)).tolist()).eval()


BLOCK_SECONDS = 60
CONTEXT_SECONDS = 8


def decode_track(path, rate, channels, decoded):
    import imageio_ffmpeg

    with TemporaryFile() as errors:
        result = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error",
             "-i", str(path), "-map", "0:a:0", "-ac", str(channels), "-ar", str(rate),
             "-f", "f32le", "pipe:1"],
            stdout=decoded, stderr=errors, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        size = decoded.seek(0, os.SEEK_END)
        if result.returncode or not size or size % (4 * channels):
            errors.seek(0)
            detail = errors.read(16384).decode("utf-8", errors="replace").strip()
            raise ValueError(f"Couldn't read the audio file. {detail}".strip())
    return size // (4 * channels)


def read_frames(file, start, count, channels):
    import numpy as np

    file.seek(start * channels * 4)
    return np.fromfile(file, dtype="<f4", count=count * channels).reshape(count, channels)


def track_statistics(decoded, frames, channels, block_size):
    import numpy as np

    means = np.zeros(2)
    squared_deviations = np.zeros(2)
    counts = np.zeros(2)
    for start in range(0, frames, block_size):
        samples = read_frames(decoded, start, min(block_size, frames - start), channels)
        if not np.isfinite(samples).all():
            raise ValueError("The audio file contains invalid samples (NaN or infinity). Try another copy.")
        mono = samples.mean(axis=1, dtype=np.float64)
        batch_means = np.array([mono.mean(), samples.mean(dtype=np.float64)])
        batch_counts = np.array([mono.size, samples.size])
        combined_counts = counts + batch_counts
        delta = batch_means - means
        squared_deviations += (
            np.array([mono.var(), samples.var(dtype=np.float64)]) * batch_counts
            + delta**2 * counts * batch_counts / combined_counts
        )
        means += delta * batch_counts / combined_counts
        counts = combined_counts
    mono_scale, stereo_scale = np.sqrt(squared_deviations / counts)
    return float(means[0]), float(mono_scale if mono_scale >= 1e-8 else max(stereo_scale, 1e-8))


def split_blocks(model, decoded, separated, frames, block_size, mean, scale, device):
    import torch
    from demucs.apply import apply_model

    channels = model.audio_channels
    context = CONTEXT_SECONDS * model.samplerate
    # Blend one second around each boundary. Both estimates use neighboring audio as context.
    overlap = min(model.samplerate, block_size // 2)
    fade = torch.linspace(0, 1, overlap).view(1, 1, -1)
    carry = None
    peak = 1.0
    separated.seek(0)
    separated.truncate()
    for start in range(0, frames, block_size):
        end = min(start + block_size, frames)
        read_start = max(0, start - context)
        read_end = min(frames, end + context)
        samples = read_frames(decoded, read_start, read_end - read_start, channels)
        mix = torch.from_numpy(samples.T.copy()).sub_(mean).div_(scale)
        estimate = apply_model(model, mix.unsqueeze(0), device=device)[0].cpu()
        offset = start - read_start
        block = estimate[..., offset:offset + end - start]
        if carry is not None:
            blend = carry.shape[-1]
            block[..., :blend].mul_(fade[..., :blend]).add_(carry * (1 - fade[..., :blend]))
        tail = min(overlap, frames - end)
        carry = estimate[..., offset + end - start:offset + end - start + tail].clone() if tail else None
        block.mul_(scale).add_(mean)
        low, high = torch.aminmax(block)
        peak = max(peak, -low.item(), high.item())
        block.permute(2, 0, 1).contiguous().numpy().tofile(separated)
        print(json.dumps({"progress": end * 100 // frames}), flush=True)
    return peak


def save_stems(model, separated, destination, frames, block_size, peak, excluded):
    import numpy as np
    import soundfile as sf

    sources = model.sources
    channels = model.audio_channels
    rate = model.samplerate
    with ExitStack() as files:
        outputs = [files.enter_context(sf.SoundFile(destination / f"{name}.wav", "w", rate, channels, "PCM_24"))
                   for name in sources]
        mixed = files.enter_context(TemporaryFile(dir=destination)) if excluded else None
        if excluded:
            kept = [index for index, name in enumerate(sources) if name not in excluded]
        mix_peak = 1.0
        for start in range(0, frames, block_size):
            count = min(block_size, frames - start)
            block = read_frames(separated, start, count, len(sources) * channels)
            block = block.reshape(count, len(sources), channels)
            block /= peak
            np.clip(block, -1.0, 0.99999988, out=block)
            for index, output in enumerate(outputs):
                output.write(block[:, index, :])
            if mixed is not None:
                mix = sum(block[:, index, :] for index in kept)
                mix_peak = max(mix_peak, -float(mix.min()), float(mix.max()))
                mix.tofile(mixed)
        if mixed is not None:
            with sf.SoundFile(destination / f"{mix_name(excluded)}.wav", "w", rate, channels, "PCM_24") as output:
                for start in range(0, frames, block_size):
                    block = read_frames(mixed, start, min(block_size, frames - start), channels)
                    np.clip(block / mix_peak, -1.0, 0.99999988, out=block)
                    output.write(block)


def separate(source, destination, cache, model_name=DEFAULT_MODEL, excluded=()):
    if excluded and (not set(excluded).issubset(REMOVABLE_STEMS) or not set(excluded).issubset(MODEL_STEMS[model_name])):
        raise ValueError("Choose the 6-stem model to exclude guitar or piano.")
    status("Starting…")
    import torch
    from demucs.apply import BagOfModels

    torch.set_num_threads(min(6, os.cpu_count() or 1))
    model = load_model(cache, model_name)
    block_size = BLOCK_SECONDS * model.samplerate
    with TemporaryFile(dir=destination) as decoded, TemporaryFile(dir=destination) as separated, torch.no_grad():
        status("Reading audio…")
        frames = decode_track(source, model.samplerate, model.audio_channels, decoded)
        mean, scale = track_statistics(decoded, frames, model.audio_channels, block_size)

        use_gpu = torch.cuda.is_available()
        peak = None
        if use_gpu:
            try:
                free_memory, _ = torch.cuda.mem_get_info()
                if free_memory < 5 * 1024**3:
                    # HTDemucs also pads inside the model to model.segment.
                    for member in model.models if isinstance(model, BagOfModels) else (model,):
                        member.segment = min(member.segment, 4)
                status("Splitting on GPU…", device="GPU")
                peak = split_blocks(model, decoded, separated, frames, block_size, mean, scale, "cuda")
            except RuntimeError as exc:
                print(f"GPU separation failed: {exc}", file=sys.stderr, flush=True)

        if peak is None:
            if use_gpu:
                del model
                model = load_model(cache, model_name)
                status("GPU split failed. Retrying on CPU…", device="CPU")
            else:
                status("Splitting on CPU…", device="CPU")
            peak = split_blocks(model, decoded, separated, frames, block_size, mean, scale, "cpu")

        status("Saving WAV files…")
        save_stems(model, separated, destination, frames, block_size, peak, excluded)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--model", choices=MODEL_STEMS, default=DEFAULT_MODEL)
    parser.add_argument("--exclude", nargs="+", choices=REMOVABLE_STEMS, default=())
    parser.add_argument("--wait-for-start", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.wait_for_start and sys.stdin.readline() != "start\n":
        sys.exit(1)
    try:
        separate(args.source, args.destination, args.cache, args.model, args.exclude)
    except Exception as exc:
        print(json.dumps({"error": str(exc) or type(exc).__name__}), flush=True)
        raise
