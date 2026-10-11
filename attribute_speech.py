import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

parser = argparse.ArgumentParser()
parser.add_argument("calibration", type=Path)
parser.add_argument("--recording", type=Path)
args = parser.parse_args()

# This initial activity threshold is a heuristic, not a validated VAD.
ACTIVITY_DB = -50
WINDOW_SECONDS = 0.1


def measure(path):
    audio, rate = sf.read(path, always_2d=True)
    if audio.shape[1] != 2:
        raise SystemExit("Expected a two-channel recording.")

    size = round(rate * WINDOW_SECONDS)
    count = len(audio) // size
    frames = audio[:count * size].reshape(count, size, 2)

    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    levels = 20 * np.log10(rms + 1e-12)
    differences = levels[:, 0] - levels[:, 1]
    active = levels.max(axis=1) > ACTIVITY_DB
    times = np.arange(count) * WINDOW_SECONDS

    return times, differences, active, len(audio) / rate


times, differences, active, duration = measure(
    args.calibration / "stereo.wav"
)

if not 29 <= duration <= 31:
    raise SystemExit("Calibration must be a 30-second recording.")

# Exclude the start, transition and end of the speaking periods.
person_1 = differences[
    active & (times >= 1) & (times < 14)
]
person_2 = differences[
    active & (times >= 16) & (times < 29)
]

if len(person_1) < 20 or len(person_2) < 20:
    raise SystemExit("Not enough audible speech in both periods.")

centre_1 = float(np.median(person_1))
centre_2 = float(np.median(person_2))
gap = abs(centre_1 - centre_2)

if gap < 6:
    raise SystemExit(
        f"Calibration centres are only {gap:.1f} dB apart. "
        "This simple method cannot reliably distinguish them."
    )

threshold = (centre_1 + centre_2) / 2
margin = min(3.0, gap / 4)
person_1_is_higher = centre_1 > centre_2

print(f"Person 1 calibration: {centre_1:+.1f} dB")
print(f"Person 2 calibration: {centre_2:+.1f} dB")
print(f"Decision boundary: {threshold:+.1f} dB")
print(f"Uncertain zone: boundary ±{margin:.1f} dB")

target = args.recording or args.calibration
times, differences, active, duration = measure(
    target / "stereo.wav"
)

# Compare short windows with the calibrated decision boundary.
distance = differences - threshold
if not person_1_is_higher:
    distance = -distance

labels = np.full(len(times), "uncertain", dtype=object)
labels[~active] = "low_audio"
labels[active & (distance > margin)] = "person_1"
labels[active & (distance < -margin)] = "person_2"

# Combine consecutive windows with the same tentative label.
spans = []
for index, label in enumerate(labels):
    start = round(float(times[index]), 2)
    end = round(start + WINDOW_SECONDS, 2)
    if spans and spans[-1]["label"] == label:
        spans[-1]["end"] = end
    else:
        spans.append({"start": start, "end": end, "label": label})

output = target / "speaker_attribution.json"
output.write_text(
    json.dumps(
        {
            "method": "experimental_channel_energy",
            "calibration": str(args.calibration),
            "threshold_db": threshold,
            "margin_db": margin,
            "spans": spans,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

for label in ("person_1", "person_2", "uncertain", "low_audio"):
    seconds = float(np.sum(labels == label)) * WINDOW_SECONDS
    print(f"{label}: {seconds:.1f} seconds")

print(f"Saved: {output}")
