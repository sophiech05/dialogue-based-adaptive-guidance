# Verification performed

Refactor verified on 13 October 2026 using Python 3.12 on Linux. The code requires Python 3.11 or newer; MLX execution requires Apple Silicon macOS.

`python -m unittest discover -s tests -v`: **10 tests passed**.

- TOML settings resolve relative paths, CLI overrides take precedence, and effective settings reach child commands.
- Port collisions in configuration and unknown setting names are rejected.
- Synthetic stereo calibration correctly handles both energy orientations and rejects indistinguishable channels.
- The offline attribution command creates the expected speaker spans and full recording endpoint.
- All executable modules import without parsing command arguments; each command's `--help` succeeds.
- A real local HTTP student listener rejects operator/export endpoints and serves a token-authenticated student page.
- A simulated input stream exercises the actual recording queue, segment assembly, transcription worker and shutdown flushing. Stereo audio, two speaker segments and effective settings are saved. The device and Whisper adapter are substituted in this test.

No physical microphone/headphone, MLX model execution or Cloudflare tunnel was available for validation. Run the short pilot checklist on your Mac to verify those components. No production recording or guidance session was used in the automated checks.

Self-contained calibration checks cover guided capture with a synthetic device, first-run persistence, reuse without audio, and preservation of existing settings after cancellation. Device capture is simulated; real audio hardware still requires verification on your Mac.
