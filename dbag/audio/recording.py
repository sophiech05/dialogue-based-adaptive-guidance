import argparse
from datetime import datetime
import json
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd
from dbag.config import parse_settings
from dbag.transcription.live import transcribe_clip
from dbag.audio.attribution import classify
from dbag.audio.calibration import ensure_calibration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("calibration", type=Path, nargs="?", default="calibration_data")
    parser.add_argument("--recalibrate", action="store_true")
    args = parse_settings(parser, ('audio', 'transcription', 'attribution'))
    import sounddevice as sd
    
    try:
        settings = ensure_calibration(args.calibration, args, force=args.recalibrate)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        parser.exit(130, '\nCalibration cancelled; recording not started.\n')
    threshold = settings['threshold_db']
    margin = settings['margin_db']
    direction = settings['direction']
    threshold = args.threshold_db if args.threshold_db is not None else threshold
    margin = args.margin_db if args.margin_db is not None else margin
    
    devices = sd.query_devices()
    if not args.input_name:
        parser.error('Set input_name in config.local.toml or use --input-name.')
    matches = [
        i for i, device in enumerate(devices)
        if args.input_name.casefold() in device["name"].casefold()
        and device["max_input_channels"] >= 2
    ]
    if len(matches) != 1:
        raise SystemExit("Select one stereo receiver with --input-name (see tools.list_devices).")
    
    device = matches[0]
    rate = int(devices[device]["default_samplerate"])
    if round(rate * args.window_seconds) < 1:
        parser.error('--window-seconds is shorter than one input sample.')
    divisor = gcd(rate, 16000)
    
    folder = (
        args.recordings_dir
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
                    result = transcribe_clip(clip, args)
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
                    if entry["end"] > turn["end"] - args.recent_seconds
                ]
                (folder / "recent_dialogue.json").write_text(
                    json.dumps(history, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
    
    
    worker = Thread(target=transcribe_worker, daemon=True)
    worker.start()
    (folder / "settings.json").write_text(json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, indent=2), encoding="utf-8")
    
    current = None
    pauses = []
    pause_seconds = 0.0
    sample_count = 0
    
    
    def finish_turn():
        nonlocal current, pauses, pause_seconds
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
        nonlocal current, pauses, pause_seconds, sample_count
    
        recording.write(block)
        start = sample_count / rate
        sample_count += len(block)
        end = sample_count / rate
    
        rms = np.sqrt(np.mean(block ** 2, axis=0))
        db = 20 * np.log10(rms + 1e-12)
    
        if status:
            print(f"Audio warning: {status}", flush=True)
            finish_turn()
            label = "uncertain"
        else:
            label = classify(db, threshold, margin, direction, args.activity_db)
    
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
                if pause_seconds >= args.pause_seconds:
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
        if current["end"] - current["start"] >= args.max_turn_seconds:
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
                blocksize=round(rate * args.window_seconds),
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


if __name__ == "__main__":
    main()
