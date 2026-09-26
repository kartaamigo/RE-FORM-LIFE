# -*- mode: python ; coding: utf-8 -*-

import os
import json
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


voice_runtime_data = collect_data_files('vosk', include_py_files=False) + collect_data_files('_sounddevice_data', include_py_files=False)
build_profile = os.environ.get('EVE_BUILD_PROFILE', 'personal').strip().lower()
if build_profile not in {'personal', 'commercial'}:
    raise RuntimeError('EVE_BUILD_PROFILE must be either personal or commercial.')
onefile_setting = os.environ.get('EVE_BUILD_ONEFILE', '0').strip().lower()
if onefile_setting not in {'0', '1', 'false', 'true', 'no', 'yes', 'off', 'on'}:
    raise RuntimeError('EVE_BUILD_ONEFILE must be a boolean value (0 or 1).')
build_onefile = onefile_setting in {'1', 'true', 'yes', 'on'}
if importlib.util.find_spec('torch') is None:
    raise RuntimeError('Install the TTS runtime for the selected EVE profile before building.')

if build_profile == 'personal':
    model_env = 'EVE_SILERO_MODEL_DIR'
    model_folder = 'silero-v5-ru'
    model_dest = 'tts-models/silero-v5-ru'
else:
    model_env = 'EVE_QWEN_MODEL_DIR'
    model_folder = 'qwen3-tts-1.7b-voicedesign'
    model_dest = 'models/qwen3-tts-1.7b-voicedesign'
    if importlib.util.find_spec('qwen_tts') is None:
        raise RuntimeError('Install qwen-tts and its dependencies before making the commercial build.')

model_source = Path(os.environ.get(model_env, '')).expanduser()
if not model_source.is_dir():
    raise RuntimeError(f'{model_env} must point to the downloaded, offline-ready model directory.')
if build_profile == 'personal' and not (model_source / 'hubconf.py').is_file():
    raise RuntimeError('The personal Silero directory must include the official hubconf.py and model weights.')
if build_profile == 'commercial' and not (model_source / 'config.json').is_file():
    raise RuntimeError('The commercial Qwen directory must be a complete local Hugging Face model snapshot.')
if build_profile == 'personal' and not list(model_source.rglob('*.pt')):
    raise RuntimeError('The Silero voice checkpoint is missing; the portable build must include it.')
if build_profile == 'commercial' and not any(model_source.glob('*.safetensors')) and not any(model_source.glob('*.bin')):
    raise RuntimeError('The Qwen model weight files are missing; the portable build must include them.')

model_data = []
for item in model_source.rglob('*'):
    if not item.is_file() or any(part in {'.git', '.cache', '__pycache__'} for part in item.parts):
        continue
    relative = item.relative_to(model_source)
    model_data.append((str(item), str(Path(model_dest) / relative.parent)))

clone_data = []
if build_profile == 'commercial':
    clone_setting = os.environ.get('EVE_QWEN_BASE_MODEL_DIR', '').strip()
    clone_source = Path(clone_setting).expanduser() if clone_setting else Path('models/qwen3-tts-0.6b-base')
    if clone_setting and not clone_source.is_dir():
        raise RuntimeError('EVE_QWEN_BASE_MODEL_DIR must point to the complete Qwen3-TTS Base model.')
    if clone_source.is_dir():
        clone_config = clone_source / 'config.json'
        clone_tokenizer = clone_source / 'speech_tokenizer'
        if (not clone_config.is_file()
                or json.loads(clone_config.read_text(encoding='utf-8')).get('tts_model_type') != 'base'
                or not (list(clone_source.glob('*.safetensors')) or list(clone_source.glob('*.bin')))
                or not (list(clone_tokenizer.glob('*.safetensors')) or list(clone_tokenizer.glob('*.bin')))):
            raise RuntimeError('The Qwen3-TTS Base voice-cloning model is incomplete.')
        for item in clone_source.rglob('*'):
            if item.is_file() and not any(part in {'.git', '.cache', '__pycache__'} for part in item.parts):
                relative = item.relative_to(clone_source)
                clone_data.append((str(item), str(Path('models/qwen3-tts-0.6b-base') / relative.parent)))

torch_datas, torch_binaries, torch_hiddenimports = collect_all('torch')
profile_hiddenimports = list(torch_hiddenimports)
for package in ('pycaw', 'omegaconf', 'yaml'):
    package_datas, package_bins, package_hidden = collect_all(package)
    torch_datas += package_datas
    torch_binaries += package_bins
    profile_hiddenimports += package_hidden
if build_profile == 'commercial':
    for package in ('qwen_tts', 'transformers', 'accelerate', 'safetensors', 'librosa'):
        package_datas, package_bins, package_hidden = collect_all(package)
        torch_datas += package_datas
        torch_binaries += package_bins
        profile_hiddenimports += package_hidden
profile_excludes = []
if build_profile == 'personal':
    profile_excludes = ['qwen_tts', 'transformers', 'accelerate', 'safetensors', 'torchaudio']

profile_file = (Path('build-profiles') / f'{build_profile}.json').as_posix()
license_data = [('licenses/Apache-2.0.txt', 'licenses')] if build_profile == 'commercial' else []


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=torch_binaries,
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('voice-models/vosk-model-small-ru-0.22', 'voice-models/vosk-model-small-ru-0.22'),
        (profile_file, 'build-profiles'),
        ('THIRD_PARTY_NOTICES.md', '.'),
        *license_data,
        *voice_runtime_data,
        *torch_datas,
        *model_data,
        *clone_data,
    ],
    hiddenimports=[
        "eve_agent",
        "eve_assistant",
        "eve_local",
        "vosk",
        "vosk.vosk_cffi",
        "sounddevice",
        *profile_hiddenimports,
        "encodings.idna",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=profile_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if build_onefile:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='RE-FORM LIFE',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        # The bundle is already dominated by compressed model/runtime files.
        # UPX adds antivirus scanning and decompression work without a useful
        # size win here, so keep startup predictable and fast.
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=['app.ico'],
        exclude_binaries=False,
        uac_admin=False,
        uac_uiaccess=False,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        [],
        name='RE-FORM LIFE',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
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
        uac_admin=False,
        uac_uiaccess=False,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='RE-FORM LIFE',
    )
