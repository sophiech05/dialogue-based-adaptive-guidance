import argparse
import json
from math import gcd
from pathlib import Path

from dbag.config import parse_settings
from dbag.transcription.live import transcribe_clip
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parse_settings(parser, ('transcription', 'attribution'))
    
    folder = args.folder
    attribution = json.loads(
        (folder / "speaker_attribution.json").read_text(
            encoding="utf-8"
        )
    )
    audio, rate = sf.read(
        folder / "stereo.wav", dtype="float32", always_2d=True
    )
    
    # Group the same speaker's speech across brief pauses.
    turns = []
    current = None
    
    for span in attribution["spans"]:
        label = span["label"]
    
        if label == "low_audio":
            continue
    
        if label == "uncertain":
            if current is not None:
                turns.append(current)
                current = None
            continue
    
        if label not in ("person_1", "person_2"):
            continue
    
        if (
            current is not None
            and current["speaker"] == label
            and span["start"] - current["end"] <= args.pause_seconds
        ):
            current["end"] = span["end"]
        else:
            if current is not None:
                turns.append(current)
            current = {
                "speaker": label,
                "start": span["start"],
                "end": span["end"],
            }
    
    if current is not None:
        turns.append(current)
    
    duration = len(audio) / rate
    divisor = gcd(rate, 16000)
    results = []
    
    print(f"Found {len(turns)} speaker turns.", flush=True)
    
    with (folder / "dialogue.txt").open(
        "w", encoding="utf-8"
    ) as transcript:
        for index, turn in enumerate(turns):
            channel = 0 if turn["speaker"] == "person_1" else 1
    
            # Add a little context without crossing neighbouring turns.
            previous_end = turns[index - 1]["end"] if index else 0
            next_start = (
                turns[index + 1]["start"]
                if index + 1 < len(turns)
                else duration
            )
            clip_start = max(previous_end, turn["start"] - args.context_seconds)
            clip_end = min(next_start, turn["end"] + args.context_seconds)
    
            clip = audio[
                round(clip_start * rate):round(clip_end * rate),
                channel,
            ]
            if not len(clip):
                continue
    
            clip = resample_poly(
                clip, 16000 // divisor, rate // divisor
            ).astype(np.float32)
    
            print(
                f"Transcribing turn {index + 1}/{len(turns)}...",
                flush=True,
            )
            result = transcribe_clip(clip, args)
    
            entry = {**turn, "text": result["text"].strip()}
            results.append(entry)
    
            line = (
                f"[{turn['start']:.1f}–{turn['end']:.1f}s] "
                f"{turn['speaker']}: {entry['text']}"
            )
            print(line, flush=True)
            transcript.write(line + "\n")
            transcript.flush()
    
    (folder / "dialogue.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    print("Saved dialogue.txt and dialogue.json.")


if __name__ == "__main__":
    main()
