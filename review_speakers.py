import argparse
import json
import time

import sounddevice as sd
import soundfile as sf

parser = argparse.ArgumentParser()
parser.add_argument("folder")
args = parser.parse_args()

from pathlib import Path
folder = Path(args.folder)

data = json.loads(
    (folder / "speaker_attribution.json").read_text()
)
audio, rate = sf.read(folder / "stereo.wav")

try:
    sd.play(audio, rate)
    started = time.monotonic()

    for span in data["spans"]:
        delay = span["start"] - (time.monotonic() - started)
        if delay > 0:
            time.sleep(delay)

        print(
            f"\r{span['start']:05.1f}–{span['end']:05.1f}s: "
            f"{span['label']:<15}",
            end="",
            flush=True,
        )

    sd.wait()
finally:
    sd.stop()
    print()
