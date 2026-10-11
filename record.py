from datetime import datetime
from pathlib import Path
import argparse
import time

import sounddevice as sd
import soundfile as sf

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=int, default=60)
args = parser.parse_args()

if args.seconds <= 0:
    parser.error("--seconds must be greater than zero")

# Find the receiver, even if its device number changes.
devices = sd.query_devices()
matches = [
    i for i, device in enumerate(devices)
    if "Wireless Mic Rx" in device["name"]
    and device["max_input_channels"] >= 2
]

if len(matches) != 1:
    raise SystemExit(
        "Could not identify one DJI receiver. "
        "Check its connection and run: python -m sounddevice"
    )

device = matches[0]
rate = int(devices[device]["default_samplerate"])

# Create a separate folder for each recording.
folder = Path("recordings") / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
folder.mkdir(parents=True, exist_ok=False)

print("Recording starts in 5 seconds...", flush=True)
time.sleep(5)
print(f"Recording for {args.seconds} seconds...", flush=True)

audio = sd.rec(
    args.seconds * rate,
    samplerate=rate,
    channels=2,
    device=device,
)
first_half = args.seconds // 2

for second in range(args.seconds):
    person = 1 if second < first_half else 2
    remaining = (
        first_half - second
        if person == 1
        else args.seconds - second
    )
    print(
        f"\rPerson {person}: speak now — {remaining:02d}s remaining   ",
        end="",
        flush=True,
    )
    time.sleep(1)

sd.wait()
print("\nRecording finished.")

# Save both channels together and each channel separately.
sf.write(folder / "stereo.wav", audio, rate, subtype="PCM_24")
sf.write(folder / "channel_1.wav", audio[:, 0], rate, subtype="PCM_24")
sf.write(folder / "channel_2.wav", audio[:, 1], rate, subtype="PCM_24")

print(f"Saved recordings to: {folder.resolve()}")
