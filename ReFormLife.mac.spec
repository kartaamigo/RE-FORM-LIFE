# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files


project = Path(SPECPATH).resolve()
voice_runtime_data = collect_data_files("vosk", include_py_files=False) + collect_data_files("_sounddevice_data", include_py_files=False)

a = Analysis(
    [str(project / "launcher.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[
        (str(project / "templates"), "templates"),
        (str(project / "static"), "static"),
        (str(project / "voice-models" / "vosk-model-small-ru-0.22"), "voice-models/vosk-model-small-ru-0.22"),
        *voice_runtime_data,
    ],
    hiddenimports=[
        "eve_agent",
        "eve_assistant",
        "vosk",
        "vosk.vosk_cffi",
        "sounddevice",
        # socket.getaddrinfo() loads the IDNA codec dynamically in the
        # frozen Python runtime used by the local Flask server.
        "encodings.idna",
        "webview.platforms.cocoa",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
