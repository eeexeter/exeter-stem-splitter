# Stem Splitter — Demucs

Stem Splitter uses Demucs v4 to separate tracks on Windows x64. Both portable builds include Python and all three model modes for offline use.

- **CPU-only** is the smaller download and processes tracks on the CPU.
- **CUDA** automatically uses a compatible NVIDIA GPU with a CUDA-capable driver. It falls back to the CPU when GPU processing is unavailable. The CUDA runtime is included.

## Getting started

1. Extract the entire ZIP archive. Keep the `runtime` folder beside `Stem Splitter.exe`.
2. Open `Stem Splitter.exe`. Select an audio file with **Browse…** or drop it anywhere in the app window. The app saves each track to `Documents\<track name> stems` by default. Use **Browse…** next to **Output folder** to change the location.
3. Choose **4 stems · Fast** (`htdemucs`), **4 stems · Quality (slower)** (`htdemucs_ft`), or **6 stems · + Guitar & Piano** (`htdemucs_6s`). Quality mode takes longer and can produce cleaner separation, depending on the track.
4. Select **Split track**. The status shows whether splitting is using the GPU or CPU. When processing finishes, click any stem card or its play icon. Click or drag its timeline to seek. Switching stems starts the next one at the current time. Drag a stem by its name or icon into File Explorer or a DAW that accepts WAV files. To transfer several WAVs at once, check the desired stems or use **Select all**, then drag any checked stem. Select **Open output folder** to view the saved files.

Stem Splitter accepts WAV, MP3, FLAC, M4A, AAC, OGG, and other formats that FFmpeg can read. For `Song.mp3`, it saves `Song - vocal.wav`, `Song - drums.wav`, `Song - bass.wav`, and `Song - other.wav` as 24-bit stereo WAV files at 44.1 kHz. In **6 stems** mode, it also saves `Song - guitar.wav` and `Song - piano.wav`. Running the same track again creates a new numbered folder.

Piano separation quality varies by recording. [Demucs documentation](https://github.com/facebookresearch/demucs#separating-tracks)

## Building from source

Install Python 3.14 x64 for Windows with Tcl/Tk. Run `.\build.ps1` from the project directory to build both variants. Run `.\build.ps1 -Variant CPU` for the CPU-only build or `.\build.ps1 -Variant CUDA` for the CUDA build. The CPU-only build skips the CUDA 12.6 dependency download. The versioned portable folders and ZIP archives are created in `dist`. The CPU-only filenames include `CPU-only`.

## Components

[Demucs](https://github.com/facebookresearch/demucs), [PyTorch](https://github.com/pytorch/pytorch), [Python](https://www.python.org/), [SoundFile](https://github.com/bastibe/python-soundfile), [FFmpeg](https://ffmpeg.org/) via [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg), and [PyInstaller](https://github.com/pyinstaller/pyinstaller).
