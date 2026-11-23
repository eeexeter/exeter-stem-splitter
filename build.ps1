param(
    [ValidateSet('Both', 'CPU', 'CUDA')]
    [string]$Variant = 'Both'
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Program, [string[]]$CommandArgs)
    & $Program @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Program exited with code $LASTEXITCODE"
    }
}

function Get-VerifiedDownload {
    param([string]$Url, [string]$File, [string]$Sha256)
    if ((Test-Path -LiteralPath $File) -and (Get-FileHash -LiteralPath $File).Hash -eq $Sha256) {
        return
    }
    $partial = "$File.download"
    Invoke-Checked curl.exe @('-fsSL', '--retry', '2', $Url, '-o', $partial)
    if ((Get-FileHash -LiteralPath $partial).Hash -ne $Sha256) {
        throw "Invalid SHA-256 for $Url"
    }
    Move-Item -LiteralPath $partial -Destination $File -Force
}

$buildRoot = Join-Path $PSScriptRoot '.runtime'
$tempDir = Join-Path $buildRoot 'temp'
$models = Join-Path $buildRoot 'models'
New-Item -ItemType Directory -Force -Path $tempDir, $models | Out-Null
$env:TEMP = $tempDir
$env:TMP = $tempDir

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Invoke-Checked python @('-m', 'venv', '.venv')
}
Invoke-Checked $python @('-c', 'import struct, sys, tkinter; assert sys.version_info[:2] == (3, 14) and struct.calcsize("P") == 8, "Use Python 3.14 x64"')
Invoke-Checked $python @('-m', 'pip', 'install', '--no-cache-dir', '--index-url', 'https://download.pytorch.org/whl/cpu', 'torch==2.10.0+cpu', 'torchaudio==2.10.0+cpu')
Invoke-Checked $python @('-m', 'pip', 'install', '--no-cache-dir', '-r', 'requirements.txt', 'pyinstaller==6.22.3')

$cudaSite = Join-Path $buildRoot 'cuda-site'
if ($Variant -ne 'CPU' -and -not ((Test-Path -LiteralPath (Join-Path $cudaSite 'torch\lib\torch_cuda.dll')) -and
          (Test-Path -LiteralPath (Join-Path $cudaSite 'torch-2.10.0+cu126.dist-info')) -and
          (Test-Path -LiteralPath (Join-Path $cudaSite 'torchaudio-2.10.0+cu126.dist-info')))) {
    Invoke-Checked $python @('-m', 'pip', 'install', '--target', $cudaSite, '--upgrade', '--no-deps', '--no-cache-dir', '--index-url', 'https://download.pytorch.org/whl/cu126', 'torch==2.10.0+cu126', 'torchaudio==2.10.0+cu126')
}

$embedded = Join-Path $buildRoot 'python-embed.zip'
Get-VerifiedDownload 'https://www.python.org/ftp/python/3.14.4/python-3.14.4-embed-amd64.zip' $embedded 'cda80a9b1e75c0f1b4f9872ca1b417f0d19bce32facc811aea9180e70fad5fb9'
$weightsJson = Invoke-Checked $python @('-c', 'import json; from itertools import chain; from models import MODEL_WEIGHTS; print(json.dumps(dict(chain.from_iterable(MODEL_WEIGHTS.values()))))')
$weights = ConvertFrom-Json -InputObject $weightsJson
foreach ($checkpoint in $weights.PSObject.Properties) {
    $filename = $checkpoint.Name
    $target = Join-Path $models $filename
    Get-VerifiedDownload "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/$filename" $target $checkpoint.Value
}

$manifest = Join-Path $PSScriptRoot 'windows.manifest'
$icon = Join-Path $PSScriptRoot 'stem-splitter-taskbar.ico'
$dropIcon = Join-Path $PSScriptRoot 'stem-splitter-upload-icon.png'
$stemIcons = Join-Path $PSScriptRoot 'stem-icons'
$guiArgs = @('-m', 'PyInstaller', '--onefile', '--windowed', '--noconfirm', '--name', 'Stem Splitter',
             '--manifest', $manifest, '--icon', $icon, '--add-data', "${icon}:.", '--add-data', "${dropIcon}:.",
             '--distpath', '.runtime\pyinstaller-dist', '--workpath', '.runtime\pyinstaller', '--specpath', '.runtime')
foreach ($name in @('vocals', 'drums', 'bass', 'other', 'guitar', 'piano', 'play')) {
    $stemIcon = Join-Path $stemIcons "$name.png"
    $guiArgs += @('--add-data', "${stemIcon}:stem-icons")
}
Invoke-Checked $python ($guiArgs + (Join-Path $PSScriptRoot 'app.pyw'))
if ($Variant -ne 'CUDA') {
    Invoke-Checked $python @('package.py', 'cpu')
}
if ($Variant -ne 'CPU') {
    Invoke-Checked $python @('package.py', 'cuda')
}
