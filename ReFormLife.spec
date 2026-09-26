# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


voice_runtime_data = collect_data_files('vosk', include_py_files=False) + collect_data_files('_sounddevice_data', include_py_files=False)


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('voice-models/vosk-model-small-ru-0.22', 'voice-models/vosk-model-small-ru-0.22'),
        *voice_runtime_data,
    ],
    hiddenimports=[
        "eve_agent",
        "eve_assistant",
        "vosk",
        "vosk.vosk_cffi",
        "sounddevice",
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
