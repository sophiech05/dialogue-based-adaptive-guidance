import argparse
import json
from math import gcd
from pathlib import Path

import mlx_whisper
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
parser.add_argument("--language", default=None)
args = parser.parse_args()

for channel in (1, 2):
    audio_path = args.folder / f"channel_{channel}.wav"
    audio, rate = sf.read(audio_path, dtype="float32")

    if audio.ndim != 1:
        raise SystemExit(f"Expected mono audio: {audio_path}")

    # Whisper expects 16,000 audio samples per second.
    if rate != 16000:
        divisor = gcd(rate, 16000)
        audio = resample_poly(
            audio, 16000 // divisor, rate // divisor
        )
    audio = np.asarray(audio, dtype=np.float32)

    print(f"Transcribing channel {channel}...", flush=True)
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo="mlx-community/whisper-small-mlx",
        language=args.language,
        condition_on_previous_text=False,
    )

    text = result["text"].strip()
    (args.folder / f"channel_{channel}.txt").write_text(
        text, encoding="utf-8"
    )
    (args.folder / f"channel_{channel}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Channel {channel}: {text}\n")

print("Done! Transcripts saved alongside the recordings.")
