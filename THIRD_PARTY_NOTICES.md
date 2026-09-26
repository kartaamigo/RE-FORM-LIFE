# Third-party voice notices

The portable EVE build includes exactly one voice profile. Confirm the
corresponding upstream model card and license before redistributing model
weights.

- Personal profile: Silero Russian V5 is from the
  [official Silero models repository](https://github.com/snakers4/silero-models).
  Its repository license is CC BY-NC-SA 4.0 (see the included
  `tts-models/silero-v5-ru/LICENSE`): attribution is required, commercial use
  is prohibited, and adapted material must use the same license. Do not use
  this profile commercially.
- Commercial profile: Qwen3-TTS VoiceDesign 1.7B is distributed under the
  [Apache License 2.0](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign).
  The commercial portable build includes the full license text at
  `licenses/Apache-2.0.txt`. The model is several gigabytes; its weights are
  included in the portable build but are not stored in this Git repository.

The active build profile and the model license are shown in EVE's voice
status. Switching profiles requires rebuilding the portable distribution.
