# EVE: local conversation, voice profiles, and PC actions

## Conversation and privacy

EVE now sends recent conversation turns to the selected language model. The
default is local Ollama / `deepseek-r1:8b`; conversation text stays on this
computer. Known planner, finance, utility, and allow-listed PC commands are
handled separately and are never passed to the language model as executable
instructions.

The optional cloud selector is off by default. Choosing it sends unknown chat
messages and recent chat history to the configured OpenAI-compatible API. Set
`OPENAI_API_KEY` in the Windows user environment and restart RE:FORM LIFE to
enable the official API. A ChatGPT subscription is not an API key, and API
usage may be billed. The key is not stored in the application database. The
default API base is `https://api.openai.com/v1`; `EVE_OPENAI_MODEL` may be
configured separately. The API key is sent only to the official HTTPS API host.

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
  Kseniya/Baya samples. Silero voice weights have a non-commercial CC BY-NC
  restriction. Do not redistribute or use this profile commercially.
- `commercial`: Qwen3-TTS VoiceDesign 1.7B, Apache-2.0, with EVE's warm,
  natural Russian female voice description. The local model snapshot is several
  gigabytes. If the GTX 1660 runs out of VRAM, synthesis retries on CPU.

Install the appropriate `requirements-tts-*.txt`, place the complete official
model source/checkpoint directory at a local path, then set the profile and
model-directory environment variables before running PyInstaller with
`ReFormLife.spec`. The spec rejects a build without model weights, verifies the
license profile, and packages only the selected model. For the commercial
profile, use the official model ID in `build-profiles/commercial.json` and save
the full Hugging Face snapshot as a normal directory (not only a cache
symlink). The personal source directory must contain upstream `hubconf.py` and
the downloaded `.pt` checkpoint.

Example PowerShell build selection:

```powershell
$env:EVE_BUILD_PROFILE = 'personal'
$env:EVE_SILERO_MODEL_DIR = 'F:\EVE-models\silero-v5-ru'
pyinstaller --noconfirm ReFormLife.spec
```

For the commercial profile, set `EVE_BUILD_PROFILE='commercial'` and
`EVE_QWEN_MODEL_DIR` to the complete VoiceDesign snapshot. Do not commit either
model directory or the resulting `dist` folder.
