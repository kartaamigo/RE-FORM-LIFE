# EVE: Gemini conversation, voice profiles, and PC actions

## Conversation and privacy

EVE uses one simple conversation provider: the Gemini Developer API. Unknown
chat messages and recent chat history are sent to Gemini, while known planner,
finance, utility, and allow-listed PC commands are handled by the deterministic
command parser. Gemini never receives executable instructions and cannot run
commands by itself.

Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey),
set `GEMINI_API_KEY` in the Windows user environment, and restart RE:FORM LIFE.
The default model is the stable `gemini-flash-lite-latest` alias, so the app
does not remain pinned to a retired model version. Set `GEMINI_MODEL` only when
you need a specific model. Google may offer a free quota, but limits and
availability can change. The key is read only from the environment, never
stored in the application database, and sent only to the official Gemini HTTPS
endpoint.

## Optional Yandex SpeechKit voice

EVE can use the official Yandex Cloud SpeechKit API for microphone recognition
and spoken answers. This is a speech service; Gemini still writes replies.
The default speech mode remains local. In SpeechKit mode, microphone clips from
the assistant window and text being spoken are sent to Yandex Cloud. The wake
word and background microphone recognition remain local in Vosk; background
spoken replies use the selected voice provider.

Create a Yandex Cloud service account with access to SpeechKit, an API key for
that account, and note the cloud folder ID. Set `YANDEX_SPEECHKIT_API_KEY` and
`YANDEX_SPEECHKIT_FOLDER_ID` in the environment used to launch RE:FORM LIFE,
then restart the app. Select **Yandex SpeechKit** under **Голос и распознавание**
on the assistant page. The API key is never saved in the app database or sent
to the browser; requests go to the official `tts.api.cloud.yandex.net` and
`stt.api.cloud.yandex.net` HTTPS hosts. SpeechKit use may incur Yandex Cloud
charges. If the key is missing or the service fails, EVE displays an error and
does not silently send audio to another provider.

## PC actions

The deterministic command parser may open known folders, Start Menu shortcuts,
web addresses and searches; read or change selected RE:FORM LIFE data; adjust
Windows volume; inspect or toggle Wi-Fi; or minimize the active window. Actions
such as closing a window, deleting a file, changing Wi-Fi, creating a folder,
restarting, or shutting down require explicit confirmation. File deletion moves
to the Recycle Bin. EVE deliberately does not execute arbitrary shell commands
or scripts, including text suggested by either language model.

The browser microphone keeps a conversation active until the user presses the
microphone/stop button or says “stop conversation”. Browser-based speech
recognition may send microphone audio to its recognition provider. The optional
native Vosk agent uses the wake word and then stays in a short conversational
session, returning to wake-word listening after silence. Native audio is
processed in memory and is not saved as a file.

## Voice distributions

Build only one profile into a portable folder at a time. The selected profile
file, model weights, and license notice are packaged together; model weights
are excluded from Git.

- `personal`: Silero Russian V5 with Xenia selected by default and optional
  Kseniya/Baya samples. The upstream Silero repository's license is
  CC BY-NC-SA 4.0: attribution is required, commercial use is prohibited,
  and adapted material must retain the same license. Its complete license
  travels with the model files in the personal build.
- `commercial`: Qwen3-TTS VoiceDesign 1.7B, Apache-2.0, with EVE's original,
  calm Russian female voice description. It creates speech from that description
  without copying a recorded person's voice. The local model snapshot is several
  gigabytes. If the GTX 1660 runs out of VRAM, synthesis retries on CPU.
  The commercial portable build also includes the Apache-2.0 license text.

The commercial profile offers three VoiceDesign styles. **EVE Original** is
brighter; **EVE · мягкий женский · русский** uses a warmer lower-mid register.
**EVE · спокойный женский гид · русский** has a softer, steadier delivery and
is tuned to a middle female pitch. This last style was tuned using
isolated female speech from the user's Karen reference; Peter's male speech
and the separate Edith recording were not used for its voice description.
The film recordings are not bundled or uploaded. VoiceDesign approximates timbre
through a written description, so generated phrases can vary.

An optional fourth selection, **EVE · голос по вашему образцу**, uses the
user-provided four-second original EVE recording and the Apache-2.0 Qwen3-TTS
0.6B Base model to speak new Russian text in that sample voice. Place the full
Base snapshot at `models/qwen3-tts-0.6b-base` or set `EVE_QWEN_BASE_MODEL_DIR`.
Keep the private audio file only on the user's computer at
`%LOCALAPPDATA%\RE-FORM LIFE\voice-samples\eve-russian-soft-voice.wav`, or set
`EVE_QWEN_SAMPLE_VOICE_FILE` to its path. Put an exact transcript of that
sample in a UTF-8 `.txt` file with the same name next to it. The sample and
transcript are never committed or
bundled into a distributable build. The selection appears only when both the
Base model and local sample are available. Commercial builds include the Base
model when it is available at build time. Voice matching can vary across
phrases, especially with a short sample.

The second local recording, `eve-sample-final.wav`, can be placed in the same
`voice-samples` directory with its exact transcript in `eve-sample-final.txt`.
It appears separately as **EVE · доработанный образец**. Set
`EVE_QWEN_SAMPLE_FINAL_VOICE_FILE` to use another local path. Both recordings
stay on the user's computer.

Install the appropriate `requirements-tts-*.txt`, place the complete official
model source/checkpoint directory at a local path, then set the profile and
model-directory environment variables before running PyInstaller with
`ReFormLife.spec`. The spec rejects a build without model weights, verifies the
license profile, and packages only the selected model. For the commercial
profile, use the official model ID in `build-profiles/commercial.json` and save
the full Hugging Face snapshot as a normal directory (not only a cache
symlink). The personal source directory must contain upstream `hubconf.py` and
the downloaded `.pt` checkpoint.

To try the original EVE voice directly from source without building a portable
app, launch the project with its commercial TTS dependencies and set
`EVE_BUILD_PROFILE=commercial` plus `EVE_QWEN_MODEL_DIR` to the local VoiceDesign
snapshot. These source-run variables do not override a packaged build's
license profile.

Example PowerShell build selection:

```powershell
$env:EVE_BUILD_PROFILE = 'personal'
$env:EVE_SILERO_MODEL_DIR = 'F:\EVE-models\silero-v5-ru'
pyinstaller --noconfirm ReFormLife.spec
```

To make a single-file executable that embeds the selected voice model and all
runtime files, set `EVE_BUILD_ONEFILE='1'` before building. For example:

```powershell
$env:EVE_BUILD_PROFILE = 'personal'
$env:EVE_SILERO_MODEL_DIR = 'F:\RE-FORM-LIFE\voice-models\silero-v5-ru'
$env:EVE_BUILD_ONEFILE = '1'
pyinstaller --noconfirm --distpath dist\EVE-personal-onefile --workpath build\EVE-personal-onefile ReFormLife.spec
```

The resulting executable contains the complete profile, including Silero's
checkpoint and license. One-file builds are several gigabytes and unpack their
contents to a temporary directory on each launch, so the temp drive needs
enough free space. This can make every launch take several minutes and can also
trigger extra antivirus checks. Leave `EVE_BUILD_ONEFILE` unset (or set it to
`0`) for the recommended fast-start portable-folder build. Keep that folder
together and launch `RE-FORM LIFE.exe` inside it; it does not require
administrator privileges. User data is stored separately under the current
user's local application-data directory.

For the commercial profile, set `EVE_BUILD_PROFILE='commercial'` and
`EVE_QWEN_MODEL_DIR` to the complete VoiceDesign snapshot. Do not commit either
model directory or the resulting `dist` folder.

## Sharing portable builds

Pushing a version tag such as `v0.3.0` starts the GitHub workflow in
`.github/workflows/release-portable.yml`. It builds separate Windows and macOS
archives and attaches them to a GitHub Release. GitHub accepts at most 2 GiB
per release asset, so a large archive is split into numbered parts. Download
every part for one platform and join the parts in filename order before
extracting the ZIP. A private-repository release is visible only to GitHub
accounts that have been granted access to the repository.

The macOS archive contains an Intel application. It runs on Intel Macs and on
Apple Silicon through Rosetta 2. Because this personal build is not signed with
an Apple Developer certificate, open it with Finder's **Open** command on the
first launch and approve the standard macOS prompt.

## Hardware verification

On the development PC (GTX 1660 6 GB, PyTorch 2.9.1+cu126), the Qwen BF16
profile generated a finite 24 kHz WAV in about 17 seconds, including model
loading. A forced CPU FP32 run on the same PC generated a finite WAV in about
47 seconds. Actual latency varies with available GPU memory and system load;
when the GPU cannot use BF16 or has less than 4.5 GiB free, EVE selects CPU.
