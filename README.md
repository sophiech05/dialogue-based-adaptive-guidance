# DBAG — Dialogue-Based Adaptive Guidance

A research prototype for capturing spoken collaboration between two participants and delivering human-operated guidance during scientific inquiry.

DBAG combines stereo audio recording, calibrated speaker attribution, French speech transcription with MLX Whisper, and an operator/student messaging interface. It provides infrastructure for investigating dialogue-informed support during collaborative data analysis.

**Status:** experimental research prototype. Guidance is currently human-operated; automated dialogue analysis and AI-generated interventions are not implemented.

## Features

- Continuous stereo recording from two microphone channels.
- Guided 30-second calibration for energy-based speaker attribution.
- Live speech segmentation and asynchronous transcription.
- Local headphone monitoring with adjustable listening gain.
- Separate operator and student guidance interfaces.
- Temporary remote student access through a Cloudflare tunnel.
- Audio, transcript, guidance-event and process logging.
- Offline attribution, transcription, diagnostic and recovery tools.

## Requirements

- Python 3.11 or newer.
- macOS on Apple Silicon for MLX Whisper transcription.
- `uv` for the installation commands below.
- A stereo microphone receiver with separate participant channels.
- Headphones for live monitoring.
- `cloudflared` for the integrated pilot's student-access tunnel.

The guidance server and offline audio diagnostics can run without MLX Whisper.

## Installation

Open a terminal in the project root:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install --no-deps -e .
```

For an installation without transcription, use `uv pip install -e .`. The transcription extra is available with `uv pip install -e '.[transcription]'` on a compatible Mac.

## Configuration

Create a local configuration file and list available audio devices:

```bash
cp config.example.toml config.local.toml
python -m dbag.tools.list_devices
```

Copy the example only when creating your local settings; repeating the copy overwrites existing settings.

Edit `config.local.toml` to set the receiver and headphone names, calibration directory and `cloudflared` executable. Device names are matched using unique, case-insensitive fragments.

Under `[pilot]`, set:

```toml
calibration = "calibration_data"
```

Settings follow this order: **command-line arguments > local configuration > shared defaults**. The launcher forwards effective settings to its child processes.

| Section | Controls |
|---|---|
| `audio` | Devices, monitoring gain and recording location |
| `transcription` | Model, language, prompt, offline mode and transcript context |
| `attribution` | Energy thresholds, window size, segmentation and calibration parameters |
| `guidance` | Operator/student ports and guidance output location |
| `pilot` | Calibration directory, tunnel executable, launcher output location and browser opening |

`config.local.toml` is automatically loaded from the current working directory. Use `--config /absolute/path/settings.toml` to select another file. Output and calibration paths resolve relative to that file's directory, or the current directory when no configuration file exists. Keep the configuration at the project root and run commands there.

The model must be cached when `offline = true`. To allow downloading the selected model on its first transcription, use `--no-offline` with a network connection.

## Running a pilot

Connect the receiver and headphones, then run:

```bash
python -m dbag.start_pilot
```

On the first run, follow the calibration prompts:

1. Place the microphones as they will be used during the session.
2. Assign person 1 to channel 1 and person 2 to channel 2.
3. Press Enter when ready.
4. Person 1 speaks for 15 seconds while person 2 stays silent.
5. At the terminal cue, person 2 speaks for 15 seconds while person 1 stays silent.

DBAG saves the decision boundary, uncertainty margin and speaker direction in `calibration_data/speaker_attribution.json`. Temporary calibration audio is discarded. Later runs reuse the saved settings.

After startup, copy the fresh student link from the operator interface to the group's device. Make and retain a synchronization event to relate audio and guidance timelines.

To stop, press **Control+C once** and leave the terminal open until audio and queued transcription finish saving.

Recalibrate after changing microphone placement or recording gain:

```bash
python -m dbag.start_pilot --recalibrate
```

To calibrate without launching a pilot:

```bash
python -m dbag.audio.calibration
```

Cancelling or failing recalibration preserves the previous saved settings.

### Command-line overrides

```bash
python -m dbag.start_pilot --output-name "External Headphones"
python -m dbag.start_pilot --operator-port 9001 --student-port 9002
python -m dbag.start_pilot --activity-db -45 --pause-seconds 0.8
python -m dbag.start_pilot --no-open-browser
```

Use `--help` on any command to inspect its options. Attribution boundary and margin normally come from calibration; `--threshold-db` and `--margin-db` provide deliberate overrides.

## Project structure

| Location | Purpose |
|---|---|
| `dbag/start_pilot.py` | Integrated pilot startup, process monitoring and shutdown |
| `dbag/config.py` | Shared defaults, configuration loading and validation |
| `dbag/audio/` | Calibration, capture, attribution and headphone monitoring |
| `dbag/transcription/` | Whisper adapter and offline transcription |
| `dbag/guidance/` | Messaging interfaces, session logging and CSV recovery |
| `dbag/tools/` | Audio device inspection and diagnostics |
| `docs/` | Technical and operational documentation |
| `tests/` | Automated checks |
| `config.example.toml` | Configuration template |
| `config.local.toml` | Local settings, excluded from Git |

## Standalone commands

| Task | Command |
|---|---|
| Record and transcribe using saved calibration | `python -m dbag.audio.recording calibration_data` |
| Inspect a stereo recording | `python -m dbag.tools.check_channels recordings/SESSION` |
| Transcribe offline attributed spans | `python -m dbag.transcription.turns recordings/SESSION` |
| Replay offline attribution labels | `python -m dbag.tools.review_speakers recordings/SESSION` |
| Monitor headphones | `python -m dbag.audio.monitoring --input 1 --output 2` |
| Guidance through an existing tunnel | `python -m dbag.guidance.server --public-origin https://NAME.trycloudflare.com` |
| Guidance on a local network | `python -m dbag.guidance.core` |
| Recover a guidance CSV | `python -m dbag.guidance.recovery guidance_sessions/SESSION` |

Device numbers and session names above are placeholders. A standalone tunnel must target the configured student port. Local-network guidance uses `--port` or the configured operator port.

Offline attribution uses a separately saved 30-second calibration recording containing `stereo.wav`, following the same two-person speaking protocol:

```bash
python -m dbag.audio.attribution recordings/CALIBRATION --recording recordings/SESSION
```

This writes `speaker_attribution.json` for the target session. Offline transcription and replay use that file. The automatic calibration settings directory contains no audio and cannot replace the saved recording required by this offline command. Offline commands may overwrite derived attribution or transcript files in the selected session.

## Saved data

| Directory | Contents |
|---|---|
| `calibration_data/` | Reusable speaker-calibration settings |
| `recordings/SESSION/` | Stereo audio, live attribution, transcripts, recent dialogue and effective recording settings |
| `guidance_sessions/SESSION/` | Guidance event journal and CSV recap |
| `pilot_runs/SESSION/` | Process logs and launcher metadata, settings and output references |

Live recording produces `stereo.wav`, `attribution.jsonl`, `dialogue.jsonl`, `dialogue.txt`, `recent_dialogue.json` and `settings.json`.

Research data, calibration settings and local configuration are excluded from Git. Back up these files separately. Audio and guidance are logged on separate timelines and are not automatically aligned.

## Tests and limitations

Run the automated checks:

```bash
python -m unittest discover -s tests -v
```

Checks cover calibration, configuration precedence and propagation, module imports, command help, student-endpoint restrictions, and simulated capture and shutdown. They do not verify physical microphone reliability, actual Whisper recognition quality, tunnel availability or concurrent audio-device access.

Energy-based attribution is sensitive to cross-talk, overlapping speech, microphone placement and speaking volume. Uncertain speech may be omitted from transcription. Acoustic segments are not validated conversational or discourse units. Transcription is asynchronous, and guidance is human-operated.
