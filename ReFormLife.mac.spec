# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files


project = Path(SPECPATH).resolve()
voice_runtime_data = collect_data_files("vosk", include_py_files=False) + collect_data_files("_sounddevice_data", include_py_files=False)
model_source = Path(os.environ.get("EVE_SILERO_MODEL_DIR", "")).expanduser()
if not model_source.is_dir() or not (model_source / "hubconf.py").is_file():
    raise RuntimeError("EVE_SILERO_MODEL_DIR must point to the complete Silero source directory.")
if not list(model_source.rglob("*.pt")):
    raise RuntimeError("The Silero voice checkpoint is missing from EVE_SILERO_MODEL_DIR.")

model_data = []
for item in model_source.rglob("*"):
    if not item.is_file() or any(part in {".git", ".cache", "__pycache__"} for part in item.parts):
        continue
    relative = item.relative_to(model_source)
    model_data.append((str(item), str(Path("tts-models/silero-v5-ru") / relative.parent)))

torch_datas, torch_binaries, torch_hiddenimports = collect_all("torch")
for package in ("omegaconf", "yaml"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    torch_datas += package_datas
    torch_binaries += package_binaries
    torch_hiddenimports += package_hiddenimports

a = Analysis(
    [str(project / "launcher.py")],
    pathex=[str(project)],
    binaries=torch_binaries,
    datas=[
        (str(project / "templates"), "templates"),
        (str(project / "static"), "static"),
        (str(project / "voice-models" / "vosk-model-small-ru-0.22"), "voice-models/vosk-model-small-ru-0.22"),
        (str(project / "build-profiles" / "personal.json"), "build-profiles"),
        *voice_runtime_data,
        *torch_datas,
        *model_data,
    ],
    hiddenimports=[
        "eve_agent",
        "eve_assistant",
        "eve_local",
        "vosk",
        "vosk.vosk_cffi",
        "sounddevice",
        # socket.getaddrinfo() loads the IDNA codec dynamically in the
        # frozen Python runtime used by the local Flask server.
        "encodings.idna",
        "webview.platforms.cocoa",
        *torch_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["qwen_tts", "transformers", "accelerate", "safetensors", "torchaudio"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RE-FORM LIFE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RE-FORM LIFE",
)

app = BUNDLE(
    coll,
    name="RE-FORM LIFE.app",
    icon=str(project / "app.icns"),
    bundle_identifier="com.reformlife.app",
    info_plist={
        "CFBundleDisplayName": "RE-FORM LIFE",
        "CFBundleShortVersionString": "1.0.0",
        "NSMicrophoneUsageDescription": "RE-FORM LIFE использует микрофон для голосового ассистента EVE.",
    },
)
