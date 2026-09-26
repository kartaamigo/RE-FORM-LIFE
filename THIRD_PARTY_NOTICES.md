# Third-party voice notices

The portable EVE build includes exactly one voice profile. Confirm the
corresponding upstream model card and license before redistributing model
weights.

- Personal profile: Silero Russian V5 voice weights are restricted to
  non-commercial use under CC BY-NC. This profile must not be used in a
  commercial distribution.
- Commercial profile: Qwen3-TTS VoiceDesign 1.7B is distributed under the
  Apache License 2.0. The model is several gigabytes; its weights are included
  in the portable build but are not stored in this Git repository.

The active build profile and the model license are shown in EVE's voice
status. Switching profiles requires rebuilding the portable distribution.
