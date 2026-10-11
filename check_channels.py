from pathlib import Path
import numpy as np
import soundfile as sf

# Find the newest recording made by record.py.
folders = sorted(
    folder for folder in Path("recordings").iterdir()
    if folder.is_dir()
    and not folder.name.startswith("live_")
    and (folder / "stereo.wav").exists()
)
if not folders:
    raise SystemExit("No recording found.")

folder = folders[-1]
audio, rate = sf.read(folder / "stereo.wav")
print(f"Checking: {folder}")

# Compare the channels in each half of the recording.
middle = len(audio) // 2

for label, section in [
    ("First half: person 1 speaking", audio[:middle]),
    ("Second half: person 2 speaking", audio[middle:]),
]:
    rms = np.sqrt(np.mean(section ** 2, axis=0))
    difference = 20 * np.log10(
        (rms[0] + 1e-12) / (rms[1] + 1e-12)
    )
    print(f"\n{label}")
    print(f"Channel 1 versus channel 2: {difference:+.1f} dB")

print("\nChannel comparison:")
print("Exactly identical:", np.array_equal(audio[:, 0], audio[:, 1]))
print(
    "Correlation:",
    round(float(np.corrcoef(audio[:, 0], audio[:, 1])[0, 1]), 4),
)
print(
    "Maximum sample difference:",
    float(np.max(np.abs(audio[:, 0] - audio[:, 1]))),
)