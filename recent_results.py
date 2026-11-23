from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from models import MODEL_STEMS, SIX_STEM_MODEL


STEMS = MODEL_STEMS[SIX_STEM_MODEL]
FILE_LABELS = {"vocal": "vocals", **{stem: stem for stem in STEMS}}
RECENT_LIMIT = 10


@dataclass(frozen=True)
class RecentResult:
    folder: Path
    stems: dict[str, str]

    def available_files(self):
        files = {stem: self.folder / self.stems[stem] for stem in STEMS if stem in self.stems}
        return {stem: path for stem, path in files.items() if path.is_file()}


def history_folder():
    app_data = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(app_data) / "Stem Splitter" / "recent-results"


def remember_result(result):
    history = history_folder()
    history.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(os.path.normcase(result.folder).encode("utf-8")).hexdigest()
    target = history / f"{key}.json"
    temporary = None
    try:
        with NamedTemporaryFile(dir=history, suffix=".tmp", delete=False, mode="w", encoding="utf-8") as stream:
            temporary = Path(stream.name)
            json.dump({"folder": str(result.folder), "stems": result.stems}, stream, ensure_ascii=False)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_result(file):
    record = json.loads(file.read_text(encoding="utf-8"))
    folder = Path(record["folder"])
    stems = record["stems"]
    if not folder.is_absolute() or not isinstance(stems, dict) or not stems:
        raise ValueError("Invalid recent result")
    if any(stem not in STEMS or Path(name).name != name or ":" in name or Path(name).suffix.lower() != ".wav"
           for stem, name in stems.items()):
        raise ValueError("Invalid recent stem file")
    return RecentResult(folder, stems)


def recent_results():
    records = []
    try:
        for file in history_folder().glob("*.json"):
            try:
                records.append((file.stat().st_mtime_ns, read_result(file)))
            except (OSError, UnicodeError, ValueError, TypeError, KeyError):
                continue
    except OSError:
        return []
    records.sort(key=lambda item: item[0], reverse=True)
    return [result for _, result in records[:RECENT_LIMIT]]


def find_existing_result(folder):
    folder = folder.resolve()
    tracks = {}
    for path in sorted(folder.glob("*.wav")):
        title, separator, label = path.stem.rpartition(" - ")
        stem = FILE_LABELS.get(label.lower())
        if title and separator and stem is not None and path.is_file():
            tracks.setdefault(title, {})[stem] = path.name
    if len(tracks) != 1:
        raise ValueError("Choose a folder containing the exported WAV stems for a single track.")
    return RecentResult(folder, next(iter(tracks.values())))
