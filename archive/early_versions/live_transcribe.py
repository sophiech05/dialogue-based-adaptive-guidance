from datetime import datetime
from math import gcd
from pathlib import Path
from queue import Queue, Empty
import time

import mlx_whisper
import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly
from collections import deque
import json

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
chunk_frames = 8 * rate
audio_queue = Queue()

folder = (
    Path(__file__).resolve().parent
    / "recordings"
    / datetime.now().strftime("live_%Y%m%d_%H%M%S_%f")
)
folder.mkdir(parents=True)

def capture(indata, frames, timing, status):
    audio_queue.put((indata.copy(), str(status)))

pending = np.empty((0, 2), dtype=np.float32)
elapsed = 0
history = deque()

with sf.SoundFile(
    folder / "stereo.wav",
    mode="w",
    samplerate=rate,
    channels=2,
    subtype="PCM_24",
) as recording, (folder / "live_channel_1.txt").open(
    "w", encoding="utf-8"
) as transcript:
    try:
        with sd.InputStream(
            device=device,
            samplerate=rate,
            channels=2,
            dtype="float32",
            blocksize=int(rate / 4),
            callback=capture,
        ):
            print("Listening to both microphones.", flush=True)
            print("Press Control+C to stop.", flush=True)
            while True:
                block, status = audio_queue.get()
                recording.write(block)
                if status:
                    print(f"Audio warning: {status}", flush=True)

                pending = np.concatenate((pending, block))
                if len(pending) < chunk_frames:
                    continue

                chunk = pending[:chunk_frames]
                pending = pending[chunk_frames:]
                divisor = gcd(rate, 16000)

                for channel in (1, 2):
                    audio = resample_poly(
                        chunk[:, channel - 1],
                        16000 // divisor,
                        rate // divisor,
                    ).astype(np.float32)

                    started = time.perf_counter()
                    result = mlx_whisper.transcribe(
                        audio,
                        path_or_hf_repo="mlx-community/whisper-small-mlx",
                        language="fr",
                        condition_on_previous_text=False,
                    )
                    duration = time.perf_counter() - started
                    text = result["text"].strip()

                    if text:
                        history.append({
                            "start": elapsed,
                            "end": elapsed + 8,
                            "channel": channel,
                            "text": text,
                        })

                    line = (
                        f"[{elapsed:03d}–{elapsed + 8:03d}s] "
                        f"Channel {channel}: {text}"
                    )
                    print(
                        f"{line} ({duration:.1f}s processing)",
                        flush=True,
                    )
                    transcript.write(line + "\n")
                    transcript.flush()

                elapsed += 8

                # Keep chunks that overlap the latest 60 seconds.
                cutoff = elapsed - 60
                while history and history[0]["end"] <= cutoff:
                    history.popleft()

                (folder / "recent_dialogue.json").write_text(
                    json.dumps(
                        list(history),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                if audio_queue.qsize() > 32:
                    print("Transcription is falling behind recording.", flush=True)

    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        # Preserve audio captured while Whisper was processing.
        while True:
            try:
                block, status = audio_queue.get_nowait()
            except Empty:
                break
            recording.write(block)
            if status:
                print(f"Audio warning: {status}", flush=True)

print(f"Saved session to: {folder}")