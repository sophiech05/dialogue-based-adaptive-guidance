import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=int, default=60)
parser.add_argument("--language", default="fr")
args = parser.parse_args()

if args.seconds <= 0:
    parser.error("--seconds must be greater than zero")

project = Path(__file__).resolve().parent

# Run the recorder and show its output.
recording_folder = None
process = subprocess.Popen(
    [
        sys.executable,
        str(project / "record.py"),
        "--seconds",
        str(args.seconds),
    ],
    cwd=project,
    stdout=subprocess.PIPE,
    text=True,
)

for line in process.stdout:
    print(line, end="", flush=True)
    if line.startswith("Saved recordings to:"):
        recording_folder = line.split(":", 1)[1].strip()

if process.wait() != 0:
    raise SystemExit("Recording failed.")

if recording_folder is None:
    raise SystemExit("Could not find the saved recording folder.")

# Transcribe the recording using the same Python environment.
subprocess.run(
    [
        sys.executable,
        str(project / "transcribe.py"),
        recording_folder,
        "--language",
        args.language,
    ],
    cwd=project,
    check=True,
)

print("Session complete.")