# Dialogue-Based Adaptive Guidance

**Research prototype for investigating dialogue-informed guidance during collaborative scientific inquiry.**

This repository contains an early-stage research prototype for capturing spoken collaboration between two participants and delivering human-operated guidance through a web-based interface.

The longer-term research objective is to investigate how dialogue-informed guidance might support collaborative inquiry, particularly when learners encounter uncertainty while interpreting complex scientific data.

**Development status:** Experimental prototype. The system is not yet validated for research data collection or autonomous adaptive guidance.

## Current capabilities

The prototype currently supports:

- **Stereo audio recording:** continuous capture from two microphone channels, intended for participants wearing individual microphones.
- **Energy-based speaker attribution:** heuristic identification of speakers through calibrated differences in channel loudness.
- **Acoustic speech segmentation:** grouping of audio into speaker-attributed speech segments using speaker changes, silence thresholds, uncertain attribution, and maximum segment duration.
- **Asynchronous speech transcription:** French speech recognition using MLX Whisper Small on Apple Silicon.
- **Live audio monitoring:** local listening through a selected audio output device.
- **Human-operated guidance:** an operator interface for delivering messages to a student-facing web interface.
- **Session logging:** preservation of audio, attribution decisions, transcripts, guidance records, and launcher metadata.

The system does not currently perform automated collaborative discourse analysis, infer learners' regulatory states, or generate AI-based interventions.

## System overview

The integrated pilot is coordinated by `start_pilot.py`, which launches four separate processes:

| Component | Responsibility |
|---|---|
| `live_speakers.py` | Audio capture, speaker attribution, acoustic segmentation, and asynchronous transcription |
| `monitor_audio.py` | Local audio monitoring |
| `messaging_online.py` | Guidance web service and operator/student interfaces |
| `cloudflared` | Temporary remote access to the student-facing interface |

The launcher manages startup checks, process monitoring, shutdown, and session metadata.

Audio processing and guidance delivery currently operate as separate subsystems. Their timelines are not automatically aligned.

## Requirements

- macOS with Apple Silicon for MLX Whisper.
- Python 3.11.
- `uv` for Python dependency management.
- Compatible stereo microphone receiver, currently configured for the DJI Wireless Mic receiver.
- Compatible audio output device.
- `cloudflared` for remote student-facing guidance.
- A locally cached Whisper model for the integrated workflow.
- Existing calibration data containing `stereo.wav` and `speaker_attribution.json`.

Some hardware names, calibration paths, and executable locations are currently specific to the development environment.

## Installation

Create a virtual environment:

```bash
uv venv --python 3.11
```

Activate it:

```bash
source .venv/bin/activate
```

Install Python dependencies:

```bash
uv pip install -r requirements.txt
```

The MLX Whisper model (`mlx-community/whisper-small-mlx`) must be downloaded and cached before running the integrated launcher, which disables Hugging Face network access during transcription.

## Integrated pilot workflow

Activate the virtual environment and run:

```bash
python start_pilot.py
```

The launcher checks the required devices, dependencies, calibration files, and network ports before starting the recording and guidance services.

For available options:

```bash
python start_pilot.py --help
```

To select another headphone output:

```bash
python start_pilot.py --output-name "External Headphones"
```

The operator interface is opened locally by default. The student-facing interface is made accessible through a temporary Cloudflare tunnel.

Create and retain a synchronization event during experimental sessions.

To stop, press **Control+C** and leave the terminal open until the recording and transcription processes have finished saving their outputs.

Video recording, when used, is managed separately.

## Separate recording and transcription workflow

An additional workflow is available:

```bash
python run_session.py
```

For its options:

```bash
python run_session.py --help
```

This workflow uses `record.py` and `transcribe.py` rather than the integrated live transcription and guidance launcher.

## Project components

| Script | Purpose |
|---|---|
| `start_pilot.py` | Integrated pilot launcher and process management |
| `live_speakers.py` | Stereo recording, energy-based attribution, segmentation, and transcription |
| `monitor_audio.py` | Local audio monitoring |
| `messaging_core.py` | Guidance messaging backend |
| `messaging_online.py` | Web-based guidance service |
| `recover_guidance.py` | Guidance record recovery |
| `run_session.py` | Separate recording/transcription workflow |
| `record.py` | Audio recording |
| `transcribe.py` | Offline transcription |

Additional scripts support audio diagnostics, speaker-attribution review, and experimental transcription methods.

## Data and outputs

Generated data is stored locally and excluded from Git version control.

| Directory | Contents |
|---|---|
| `recordings/` | Original audio, speaker-attribution records, speech-segment transcripts |
| `guidance_sessions/` | Guidance records and CSV summaries |
| `pilot_runs/` | Launcher logs, session metadata, and output-path references |

The live transcription pipeline produces:

- `stereo.wav`: original two-channel audio.
- `attribution.jsonl`: acoustic speaker-attribution labels for successive audio blocks.
- `dialogue.jsonl`: timestamped speaker-attributed speech segments and transcription results.
- `dialogue.txt`: human-readable transcript.
- `recent_dialogue.json`: a rolling record of recently processed segments.

**Terminology:** Speech segments are defined through acoustic and computational rules. They should not be equated with theoretically defined conversational turns or discourse units.

Do not upload participant recordings, transcripts, identifiable research data, or credentials to GitHub. Research data collection and external services must comply with applicable institutional and ethical requirements.

## Known limitations

The current implementation has not yet undergone systematic validation.

**Speaker attribution:** Channel-energy comparison can be affected by cross-talk, overlapping speech, microphone placement, and changes in speaking volume.

**Speech segmentation:** Heuristic boundaries can split meaningful contributions, combine separate contributions, or omit speech classified as uncertain.

**Transcription accuracy:** Recognition quality has not been quantified against manually verified reference transcripts. Short segments, overlap, and domain-specific vocabulary may reduce accuracy.

**Processing latency:** Transcription runs asynchronously, but end-to-end latency—including queueing delay—has not yet been systematically measured.

**Temporal synchronization:** Audio and guidance records are saved separately. The launcher does not automatically merge or align their timelines.

**Guidance automation:** Guidance is currently human-operated. Automated dialogue interpretation and AI-generated guidance are not implemented.

These limitations should be addressed or explicitly accounted for before drawing research conclusions from the system's automated outputs.

## Research and development priorities

Near-term priorities are to:

1. Evaluate speaker-attribution reliability and transcription accuracy.
2. Improve speech segmentation and handling of overlapping speech.
3. Measure end-to-end transcription latency.
4. Establish reliable temporal alignment between dialogue and guidance events.
5. Develop reproducible procedures for recording, testing, and analyzing pilot sessions.

Longer-term research may investigate computational dialogue analysis, guidance timing and formulation, and adaptive support for productive uncertainty regulation during collaborative scientific inquiry.

## Documentation

Additional operational instructions:

- `docs/manual-guidance.md` — manual guidance setup, operation, and recovery.

Further technical documentation of the architecture, audio-processing pipeline, and experimental procedures is under development.

## Project status

**Early-stage research prototype — under active development.**

The repository provides initial infrastructure for exploring dialogue-informed guidance. It does not yet constitute a validated measurement instrument or an autonomous AI facilitation system.