import argparse
from importlib.metadata import PathDistribution
from pathlib import Path
import shutil
import sysconfig
from tempfile import TemporaryDirectory
import zipfile

from models import MODEL_WEIGHTS
from version import VERSION


ROOT = Path(__file__).resolve().parent
BUILD = ROOT / ".runtime"
DIST = ROOT / "dist"


def package_sources(installed, variant):
    flavor = "+cu126" if variant == "cuda" else "+cpu"
    torch_site = BUILD / "cuda-site" if variant == "cuda" else installed
    for name in ("torch", "torchaudio"):
        metadata = list(torch_site.glob(f"{name}-*.dist-info"))
        if len(metadata) != 1 or not PathDistribution(metadata[0]).version.endswith(flavor):
            raise ValueError(f"The {variant.upper()} build requires {name} with {flavor} in {torch_site}.")
    has_cuda = (torch_site / "torch" / "lib" / "torch_cuda.dll").is_file()
    if has_cuda != (variant == "cuda"):
        raise ValueError(f"Unexpected PyTorch DLLs in {torch_site}.")

    build_only = ("pip", "pyinstaller", "_pyinstaller_hooks_contrib", "altgraph", "pefile", "peutils",
                  "win32ctypes", "pywin32_ctypes")
    packages = {item.name: item for item in installed.iterdir()
                if not item.name.lower().startswith(build_only) and item.name != "__pycache__"}
    if variant == "cuda":
        packages = {name: item for name, item in packages.items()
                    if not name.lower().startswith(("torch-", "torchaudio-"))}
        packages.update((item.name, item) for item in torch_site.iterdir()
                        if item.name not in {"bin", "__pycache__"})
    return packages.values()


def populate(bundle, variant):
    shutil.copy2(BUILD / "pyinstaller-dist" / "Stem Splitter.exe", bundle)
    runtime = bundle / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BUILD / "python-embed.zip") as archive:
        archive.extractall(runtime)
    (runtime / "python314._pth").write_text("python314.zip\n.\nLib\\site-packages\nimport site\n", encoding="ascii")

    installed = Path(sysconfig.get_path("purelib"))
    site_packages = runtime / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    for item in package_sources(installed, variant):
        if item.is_dir():
            shutil.copytree(item, site_packages / item.name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, site_packages / item.name)

    for module in ("models.py", "separator.py"):
        shutil.copy2(ROOT / module, runtime / module)
    models = runtime / "models"
    models.mkdir(exist_ok=True)
    for filename, _ in MODEL_WEIGHTS.values():
        shutil.copy2(BUILD / "models" / filename, models)
    shutil.copy2(ROOT / "README.md", bundle)


def package(variant):
    suffix = " CPU-only" if variant == "cpu" else ""
    release = DIST / f"Stem Splitter {VERSION}{suffix}"
    output = DIST / f"{release.name} Windows x64.zip"
    DIST.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".build-", dir=DIST) as folder:
        workspace = Path(folder)
        bundle = workspace / release.name
        bundle.mkdir()
        populate(bundle, variant)
        partial = workspace / output.name
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for file in bundle.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(workspace))

        backup = workspace / "previous-release"
        if release.exists():
            release.rename(backup)
        try:
            bundle.rename(release)
            try:
                partial.replace(output)
            except OSError:
                release.rename(bundle)
                raise
        finally:
            if backup.exists() and not release.exists():
                backup.rename(release)
    print(f"Built {output} ({output.stat().st_size / 1024**2:.0f} MiB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", choices=("cpu", "cuda"))
    package(parser.parse_args().variant)
