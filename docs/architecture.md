# Architecture and migration

## Ownership

| Module | Owns | Does not own |
|---|---|---|
| `start_pilot` | Preflight checks, child startup/shutdown, launcher recap | Signal processing and messaging logic |
| `config` | Defaults, TOML loading, validation, CLI options and child propagation | Machine-specific selections |
| `audio.recording` | Capture queue, live segment assembly, audio and attribution saving | Whisper implementation |
| `audio.calibration` | Interactive first-run calibration, validated boundary settings and one-time legacy migration | Ongoing audio recording |
| `audio.attribution` | Channel-energy measurement, calibrated boundary, labels, offline attribution | Device capture |
| `audio.monitoring` | Headphone playback and listening gain | Saved recording gain |
| `transcription.live` | Lazy Whisper invocation | Capture and session lifecycle |
| `transcription.turns` | Offline span grouping and transcription exports | Live capture |
| `guidance.core` | Sessions, journal, CSV and existing HTTP/UI behavior | Audio processing |
| `guidance.server` | Separate local operator and tunneled student listeners | Recording startup |
| `guidance.recovery` | Rebuilding a CSV from journal events | Editing original journal |

## File mapping

| Original archive | Active location |
|---|---|
| `start_pilot.py` | `dbag/start_pilot.py` |
| `live_speakers.py` | `dbag/audio/recording.py` plus `transcription/live.py` |
| `attribute_speech.py` | `dbag/audio/attribution.py` |
| `monitor_audio.py` | `dbag/audio/monitoring.py` |
| `transcribe_turns.py` | `dbag/transcription/turns.py` |
| `guidance/core.py` | `dbag/guidance/core.py` |
| `guidance/online.py` | `dbag/guidance/server.py` |
| `recover_guidance.py` | `dbag/guidance/recovery.py` |
| `tools/check_channels.py` | `dbag/tools/check_channels.py` |
| `tools/review_speakers.py` | `dbag/tools/review_speakers.py` |

No duplicate compatibility scripts are included. Use `python -m` commands from the README.

## Data contracts

| Record | Fields and units |
|---|---|
| Audio file | Two channels, original device sample rate, PCM 24-bit for live capture |
| Attribution window | `start`, `end` in seconds from recording start; `label` in `person_1`, `person_2`, `uncertain`, `low_audio`; `status` for live device warnings |
| Transcribed segment | `speaker`, `start`, `end`, `text`; live entries also include `processing_seconds` and optionally `error` |
| Offline attribution | `threshold_db`, `margin_db`, `spans`; new outputs additionally retain direction, centres, window and activity settings |
| Guidance event | Existing session ID, event, UTC and messaging elapsed time, with event-specific fields |
| Launcher recap | Effective settings, process metadata, UTC timestamps, logs and saved output references |

The capture callback enqueues audio. The recording loop writes stereo audio and builds segments. A separate thread consumes segments and calls the Whisper adapter. Transcription errors are logged per segment. The launcher waits for recording and queued transcription during shutdown.

The original unbounded queues are retained; slow transcription can accumulate pending work. Offline span grouping and live segmentation preserve their different original rules. A future extraction of a shared segment assembler should be a separate behavior change, with recorded reference sessions.

## Migration

Extract into a new folder; install; no old calibration needed; copy other data only if wanted; create local settings; verify a short pilot. Keep your old folder as a backup until verified. Avoid copying `code_for_reorganization`, `reorganization_bundle`, `.venv`, or code snapshots into the new active tree. Later use Git commits for code history. Nothing in this download deletes or moves files on your computer.

Calibration still has a fixed 30-second speaking protocol, with 1–14 seconds and 16–29 seconds used to estimate centres. The minimum audible duration is two seconds per participant; at the default 0.1-second windows this matches the original 20-window requirement. Tiny sub-sample windows are rejected, and offline timestamps use the actual rounded sample-window duration.

Live startup now persists speaker direction directly. Its calibration audio is temporary and is deleted after computing the boundary. Existing legacy folders can be migrated once, but are not required. Use --recalibrate for changed microphone placement/gain.
