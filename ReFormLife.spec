# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


voice_runtime_data = collect_data_files('vosk', include_py_files=False) + collect_data_files('_sounddevice_data', include_py_files=False)
piper_runtime_data = collect_data_files('piper', include_py_files=False)
piper_hiddenimports = collect_submodules('piper') + ['onnxruntime', 'onnxruntime.capi._pybind_state']


piper_model = Path(os.environ.get('EVE_PIPER_MODEL', '')).expanduser()
piper_model_data = []
if piper_model.is_file() and Path(f'{piper_model}.json').is_file():
    piper_model_data = [
        (str(piper_model), 'tts-models'),
        (f'{piper_model}.json', 'tts-models'),
    ]


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('voice-models/vosk-model-small-ru-0.22', 'voice-models/vosk-model-small-ru-0.22'),
        *voice_runtime_data,
        *piper_runtime_data,
        *piper_model_data,
    ],
    hiddenimports=[
        "eve_agent",
        "eve_assistant",
        "eve_local",
        "vosk",
        "vosk.vosk_cffi",
        "sounddevice",
        *piper_hiddenimports,
        "encodings.idna",
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
    [],
    name='RE-FORM LIFE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RE-FORM LIFE',
)
