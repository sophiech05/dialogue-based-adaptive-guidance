# Collaboration MVP

Research prototype for studying spoken collaboration and developing
AI-supported guidance during collaborative inquiry learning.

## Current capabilities

The prototype currently supports:

- Audio recording using separate microphone channels.
- Speech transcription using MLX Whisper.
- Speaker attribution and dialogue logging.
- Live audio monitoring.
- Manual guidance through an operator interface.
- Guidance delivery to a student-facing web interface.
- Session logging and recovery of guidance records.

Automated dialogue analysis and AI-generated guidance are planned
research developments, not yet implemented capabilities.

## Requirements

- macOS with Apple Silicon for MLX Whisper.
- Python 3.11.
- uv for Python dependency management.
- Compatible microphones and audio output devices.
- cloudflared for remote student-facing guidance.

## Installation

Create a virtual environment:

    uv venv --python 3.11

Activate it:

    source .venv/bin/activate

Install Python dependencies:

    uv pip install -r requirements.txt

The Whisper model must also be downloaded and cached before
running the integrated launcher.

## Main pilot workflow

Activate the environment and run:

    python start_pilot.py

The launcher coordinates:

- Live recording, transcription and speaker attribution.
- Local audio monitoring.
- Manual guidance interface.
- Student-facing guidance service and Cloudflare tunnel.
- Session logging.

For additional options:

    python start_pilot.py --help

For a specific headphone output:

    python start_pilot.py --output-name "External Headphones"

Stop using Control+C and allow the launcher to finish saving.

Video recording is separate.

Audio and guidance timestamps are not automatically synchronized.
Retain a synchronization event during experimental sessions.

## Separate recording and transcription workflow

An additional workflow is available:

    python run_session.py

Options:

    python run_session.py --help

This workflow uses record.py and transcribe.py.

## Project components

- start_pilot.py: Integrated pilot launcher.
- live_speakers.py: Live transcription and speaker attribution.
- monitor_audio.py: Audio monitoring.
- messaging_core.py: Guidance messaging backend.
- messaging_online.py: Online guidance interface.
- recover_guidance.py: Recovery of guidance records.
- run_session.py: Separate recording/transcription workflow.
- record.py: Audio recording.
- transcribe.py: Offline transcription.

Additional scripts support audio diagnostics, speaker review,
and experimental transcription methods.

## Data and outputs

Generated data is stored locally:

- recordings/: Audio, transcripts and speaker attribution.
- guidance_sessions/: Guidance events and CSV recaps.
- pilot_runs/: Launcher logs and session metadata.

These directories are excluded from Git version control.

Do not upload participant recordings, transcripts, identifiable
research data or credentials to GitHub.

## Documentation

Detailed manual guidance setup and recovery instructions:

    docs/manual-guidance.md

## Development status

Early research MVP.

Current focus: establishing reliable recording, transcription,
speaker attribution and guidance infrastructure.

Future research may include dialogue-based analysis and
adaptive AI guidance during collaborative inquiry learning.
