"""Experimental stereo channel-energy attribution and calibration command."""
import argparse
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from dbag.config import parse_settings

def measure(path, window_seconds=0.1, activity_db=-50.0):
    audio, rate = sf.read(path, always_2d=True)
    if audio.shape[1] != 2:
        raise ValueError('Expected a two-channel recording.')
    size = round(rate * window_seconds)
    if size < 1:
        raise ValueError('Window is shorter than one audio sample.')
    count = len(audio) // size
    if not count:
        raise ValueError('Recording is shorter than one window.')
    frames = audio[:count * size].reshape(count, size, 2)
    levels = 20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-12)
    times = np.arange(count) * size / rate
    return times, levels[:, 0] - levels[:, 1], levels.max(axis=1) > activity_db, len(audio) / rate

def classify(levels, threshold, margin, direction, activity_db):
    if np.max(levels) <= activity_db:
        return 'low_audio'
    distance = direction * (levels[0] - levels[1] - threshold)
    return 'person_1' if distance > margin else ('person_2' if distance < -margin else 'uncertain')

def calibration_direction(folder, threshold, window_seconds, activity_db):
    times, differences, active, _ = measure(folder / 'stereo.wav', window_seconds, activity_db)
    mask = active & (times >= 1) & (times < 14)
    if not np.any(mask):
        raise ValueError('Calibration contains insufficient speech.')
    return 1 if np.median(differences[mask]) > threshold else -1

def calibrate(folder, settings):
    times, differences, active, duration = measure(folder / 'stereo.wav', settings.window_seconds, settings.activity_db)
    if not 29 <= duration <= 31:
        raise ValueError('Calibration must be 30 seconds: person 1 first, then person 2 at 15s.')
    one = differences[active & (times >= 1) & (times < 14)]
    two = differences[active & (times >= 16) & (times < 29)]
    # Require at least two seconds of audible speech in each period.
    if min(len(one), len(two)) * settings.window_seconds < 2:
        raise ValueError('Not enough audible speech in both calibration periods.')
    centres = float(np.median(one)), float(np.median(two))
    gap = abs(centres[0] - centres[1])
    if gap < settings.minimum_gap_db:
        raise ValueError(f'Calibration centres are only {gap:.1f} dB apart.')
    return {'threshold_db': sum(centres) / 2,
            'margin_db': min(settings.maximum_margin_db, gap / 4),
            'direction': 1 if centres[0] > centres[1] else -1,
            'centres_db': centres}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('calibration', type=Path)
    parser.add_argument('--recording', type=Path)
    args = parse_settings(parser, ('attribution',))
    try:
        boundary = calibrate(args.calibration, args)
        threshold = args.threshold_db if args.threshold_db is not None else boundary['threshold_db']
        margin = args.margin_db if args.margin_db is not None else boundary['margin_db']
        target = args.recording or args.calibration
        times, differences, active, duration = measure(target / 'stereo.wav', args.window_seconds, args.activity_db)
        distance = boundary['direction'] * (differences - threshold)
        labels = np.full(len(times), 'uncertain', dtype=object)
        labels[~active] = 'low_audio'
        labels[active & (distance > margin)] = 'person_1'
        labels[active & (distance < -margin)] = 'person_2'
        spans = []
        step = float(times[1] - times[0]) if len(times) > 1 else args.window_seconds
        for index, label in enumerate(labels):
            start = round(float(times[index]), 6)
            end = min(duration, round(float(times[index]) + step, 6))
            if spans and spans[-1]['label'] == label:
                spans[-1]['end'] = end
            else:
                spans.append({'start': start, 'end': end, 'label': label})
        output = target / 'speaker_attribution.json'
        output.write_text(json.dumps({'method': 'experimental_channel_energy',
            'calibration': str(args.calibration), **boundary, 'threshold_db': threshold,
            'margin_db': margin, 'activity_db': args.activity_db,
            'window_seconds': args.window_seconds, 'spans': spans}, indent=2), encoding='utf-8')
        for label in ('person_1', 'person_2', 'uncertain', 'low_audio'):
            print(f'{label}: {np.sum(labels == label) * step:.1f} seconds')
        print(f'Saved: {output}')
    except (ValueError, OSError) as error:
        parser.error(str(error))

if __name__ == '__main__':
    main()
