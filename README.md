# DBAG — Dialogue-Based Adaptive Guidance

A research prototype for capturing spoken collaboration between two students and delivering human-operated guidance during inquiry based learning.

DBAG combines stereo audio recording, calibrated speaker attribution, French speech transcription with MLX Whisper, and an operator/student messaging interfaces. It provides infrastructure for investigating dialogue-informed support during collaborative inquiry based learning.

**Status:** first research prototype. Early-stage research prototype. Guidance is currently human-operated using a Wizard-of-Oz (WoZ) approach. Automated dialogue analysis and AI-generated interventions are planned for a later stage, following proof-of-concept validation. 

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

## Installation

Open a terminal in the project root:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt 
uv pip install --no-deps -e . 
```

## Configuration

Create a local configuration file and list available audio devices:

```bash
cp config.example.toml config.local.toml
python -m dbag.tools.list_devices
```

Copy the example only when creating your local settings; repeating the copy overwrites existing settings.

Edit `config.local.toml` to set (1) the receiver and (2) headphone names, (3) calibration directory and (4) `cloudflared` executable. Device names are matched using unique, case-insensitive fragments.


Settings follow this order: **command-line arguments > local configuration > shared defaults**. The launcher forwards effective settings to its child processes.

| Section | Controls |
|---|---|
| `audio` | Microphone/headphone selection, headphone monitoring gain, and recordings directory |
| `transcription` | Whisper model, language, initial prompt, offline model access, recent transcript history, and audio padding for offline transcription |
| `attribution` | Speech activity threshold, analysis window size, speech segmentation rules, and speaker calibration parameters |
| `guidance` | Operator/student server ports and guidance logs directory |
| `pilot` | Saved calibration directory, `cloudflared` executable, launcher logs directory, and automatic opening of the operator page |

Keep `config.local.toml` in the project root, alongside `README.md`, and run commands from that folder. The program loads your local settings automatically.

If the Whisper model hasn’t been downloaded yet, run `python -m dbag.start_pilot --no-offline` with an internet connection. Once downloaded, the model can be reused with `offline = true`.

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
python -m dbag.start_pilot --input-name "External Mic"
python -m dbag.start_pilot --operator-port 9001 --student-port 9002
python -m dbag.start_pilot --activity-db -45 --pause-seconds 0.8
python -m dbag.start_pilot --no-open-browser
```

Use `--help` on any command to inspect its options. Attribution boundary and margin normally come from calibration; `--threshold-db` and `--margin-db` provide deliberate overrides (useful for testing).

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
| Transcribe previously attributed audio | `python -m dbag.transcription.turns recordings/SESSION` |
| Play audio while displaying attribution labels | `python -m dbag.tools.review_speakers recordings/SESSION` |
| Listen to microphones through headphones | `python -m dbag.audio.monitoring --input 1 --output 2` |
| Start guidance using an existing tunnel | `python -m dbag.guidance.server --public-origin https://NAME.trycloudflare.com` |
| Start guidance on a local network | `python -m dbag.guidance.core` |
| Rebuild a guidance CSV from saved events | `python -m dbag.guidance.recovery guidance_sessions/SESSION` |

Replace `SESSION` with your actual session folder name, `1` and `2` with the device numbers shown by `list_devices`, and `https://NAME.trycloudflare.com` with your tunnel’s actual URL.

- **Offline transcription and replay:** the session folder must contain `stereo.wav` and a `speaker_attribution.json` file containing attributed spans. Live recording saves `attribution.jsonl`, which these tools do not read directly.
- **Guidance through an existing tunnel:** the tunnel must target the configured student port—for example, `http://127.0.0.1:8766`. The standalone guidance command does not create the tunnel.
- **Local-network guidance:** uses the configured operator port unless overridden with `--port`. In this mode, operator and student pages share the same port.
- **CSV recovery:** requires `events.jsonl` in the guidance session folder and creates `guidance_recap_recovered.csv`.

Enter the tunnel URL as plain text in the command, without Markdown link syntax.

## Saved data

| Directory | Contents |
|---|---|
| `calibration_data/` | Reusable speaker-calibration settings |
| `recordings/SESSION/` | Stereo audio, live attribution, transcripts, recent dialogue and effective recording settings |
| `guidance_sessions/SESSION/` | Guidance event journal and CSV recap |
| `pilot_runs/SESSION/` | Process logs and launcher metadata, settings and output references |

Live recording produces `stereo.wav`, `attribution.jsonl`, `dialogue.jsonl`, `dialogue.txt`, `recent_dialogue.json` and `settings.json`.

Research data, calibration settings and local configuration are excluded from Git. Back up these files separately. Audio and guidance are logged on separate timelines and are not automatically aligned.

### Tests

Run the automated tests from the project root:

```bash
python -m unittest discover -s tests -v
```

Tests check calibration calculations, configuration loading and command-line overrides, settings passed to component processes, module imports, command help, student-interface access restrictions, and simulated recording and shutdown.

These tests use synthetic audio and simulated devices. They do not assess real microphone performance, Whisper transcription accuracy, tunnel availability, or simultaneous recording and headphone monitoring on your computer. Verify these with a short pilot session.

### Research limitations

- **Speaker attribution:** channel-energy differences are affected by cross-talk, overlapping speech, microphone placement and speaking volume. Speech labelled uncertain is recorded in the original audio but excluded from live transcription.
- **Segmentation:** speech segments are defined by acoustic rules. They should not be treated as validated conversational turns or discourse units.
- **Transcription:** recognition accuracy and processing latency require evaluation. Transcription runs separately from recording, so text may appear with a delay.
- **Synchronization:** audio and guidance use separate timelines and require a synchronization event.
- **Guidance:** interventions are currently human-operated using a Wizard-of-Oz approach. Automated dialogue analysis and AI-generated interventions are planned for a later stage, following proof-of-concept validation. 
