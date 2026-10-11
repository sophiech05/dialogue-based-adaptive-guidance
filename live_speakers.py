import argparse
from datetime import datetime
import json
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import time

import mlx_whisper
import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

parser = argparse.ArgumentParser()
parser.add_argument("calibration", type=Path)
args = parser.parse_args()

# Load the calibration boundary.
settings = json.loads(
    (args.calibration / "speaker_attribution.json").read_text()
)
threshold = settings["threshold_db"]
margin = settings["margin_db"]

# Determine which side of the boundary belongs to person 1.
calibration, calibration_rate = sf.read(
    args.calibration / "stereo.wav", always_2d=True
)
size = round(calibration_rate * 0.1)
count = len(calibration) // size
frames = calibration[:count * size].reshape(count, size, 2)
levels = 20 * np.log10(
    np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-12
)
times = np.arange(count) * 0.1
mask = (
    (times >= 1)
    & (times < 14)
    & (levels.max(axis=1) > -50)
)
if not np.any(mask):
    raise SystemExit("Calibration contains insufficient speech.")

difference = levels[:, 0] - levels[:, 1]
direction = 1 if np.median(difference[mask]) > threshold else -1

devices = sd.query_devices()
matches = [
    i for i, device in enumerate(devices)
    if "Wireless Mic Rx" in device["name"]
    and device["max_input_channels"] >= 2
]
if len(matches) != 1:
    raise SystemExit("Connect the DJI receiver and try again.")

device = matches[0]
rate = int(devices[device]["default_samplerate"])
divisor = gcd(rate, 16000)

folder = (
    Path(__file__).resolve().parent
    / "recordings"
    / datetime.now().strftime("live_speakers_%Y%m%d_%H%M%S_%f")
)
folder.mkdir(parents=True)

audio_queue = Queue()
turn_queue = Queue()


def capture(indata, frames, timing, status):
    audio_queue.put((indata.copy(), str(status)))


# Whisper runs separately from audio recording.
def transcribe_worker():
    history = []
    with (folder / "dialogue.txt").open(
        "w", encoding="utf-8"
    ) as text_file, (folder / "dialogue.jsonl").open(
        "w", encoding="utf-8"
    ) as log:
        while True:
            turn = turn_queue.get()
            if turn is None:
                break

            channel = 0 if turn["speaker"] == "person_1" else 1
            clip = resample_poly(
                turn.pop("audio")[:, channel],
                16000 // divisor,
                rate // divisor,
            ).astype(np.float32)

            started = time.perf_counter()
            try:
                result = mlx_whisper.transcribe(
                    clip,
                    path_or_hf_repo="mlx-community/whisper-small-mlx",
                    language="fr",
                    task="transcribe",
                    initial_prompt=(
                        "Discussion en français entre élèves sur des mesures "
                        "scientifiques, des données, des capteurs et des hypothèses."
                    ),
                    condition_on_previous_text=False,
                )
                turn["text"] = result["text"].strip()
            except Exception as error:
                turn["text"] = ""
                turn["error"] = str(error)

            turn["processing_seconds"] = round(
                time.perf_counter() - started, 2
            )
            line = (
                f"[{turn['start']:.1f}–{turn['end']:.1f}s] "
                f"{turn['speaker']}: {turn['text']}"
            )
            if "error" in turn:
                line += f" ERROR: {turn['error']}"

            print(line, flush=True)
            text_file.write(line + "\n")
            text_file.flush()
            log.write(json.dumps(turn, ensure_ascii=False) + "\n")
            log.flush()

            history.append(turn)
            history = [
                entry for entry in history
                if entry["end"] > turn["end"] - 60
            ]
            (folder / "recent_dialogue.json").write_text(
                json.dumps(history, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


worker = Thread(target=transcribe_worker, daemon=True)
worker.start()

current = None
pauses = []
pause_seconds = 0.0
sample_count = 0


def finish_turn():
    global current, pauses, pause_seconds
    if current is not None:
        turn_queue.put({
            "speaker": current["speaker"],
            "start": current["start"],
            "end": current["end"],
            "audio": np.concatenate(current["blocks"]),
        })
        if turn_queue.qsize() > 3:
            print("Whisper has several turns waiting.", flush=True)

    current = None
    pauses = []
    pause_seconds = 0.0


def process_block(block, status, recording, attribution_log):
    global current, pauses, pause_seconds, sample_count

    recording.write(block)
    start = sample_count / rate
    sample_count += len(block)
    end = sample_count / rate

    rms = np.sqrt(np.mean(block ** 2, axis=0))
    db = 20 * np.log10(rms + 1e-12)
    distance = direction * (db[0] - db[1] - threshold)

    if status:
        print(f"Audio warning: {status}", flush=True)
        finish_turn()
        label = "uncertain"
    elif db.max() <= -50:
        label = "low_audio"
    elif distance > margin:
        label = "person_1"
    elif distance < -margin:
        label = "person_2"
    else:
        label = "uncertain"

    attribution_log.write(json.dumps({
        "start": round(start, 3),
        "end": round(end, 3),
        "label": label,
        "status": status,
    }) + "\n")

    if label == "low_audio":
        if current is not None:
            pauses.append(block)
            pause_seconds += len(block) / rate
            if pause_seconds >= 0.6:
                finish_turn()
        return

    if label == "uncertain":
        finish_turn()
        return

    if current is not None and current["speaker"] != label:
        finish_turn()

    if current is None:
        current = {
            "speaker": label,
            "start": start,
            "end": end,
            "blocks": [block],
        }
    else:
        current["blocks"].extend(pauses)
        current["blocks"].append(block)
        current["end"] = end

    pauses = []
    pause_seconds = 0.0

    # Limit delay during long uninterrupted turns.
    if current["end"] - current["start"] >= 15:
        finish_turn()


with sf.SoundFile(
    folder / "stereo.wav",
    mode="w",
    samplerate=rate,
    channels=2,
    subtype="PCM_24",
) as recording, (folder / "attribution.jsonl").open(
    "w", encoding="utf-8"
) as attribution_log:
    try:
        with sd.InputStream(
            device=device,
            samplerate=rate,
            channels=2,
            dtype="float32",
            blocksize=round(rate * 0.1),
            callback=capture,
        ):
            print("Listening to both people. Control+C stops.", flush=True)
            while True:
                block, status = audio_queue.get()
                process_block(
                    block, status, recording, attribution_log
                )
    except KeyboardInterrupt:
        print("\nRecording stopped. Finishing queued turns...", flush=True)
    finally:
        while True:
            try:
                block, status = audio_queue.get_nowait()
            except Empty:
                break
            process_block(block, status, recording, attribution_log)

        finish_turn()
        turn_queue.put(None)

worker.join()
print(f"Saved session to: {folder}")