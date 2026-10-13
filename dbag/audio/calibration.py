"""Create and reuse a self-contained speaker calibration."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
from dbag.config import parse_settings

def read_boundary(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    for key in ('threshold_db', 'margin_db', 'direction'):
        value = data.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'Invalid calibration field: {key}. Run with --recalibrate.')
    if data['direction'] not in (-1, 1) or data['margin_db'] < 0:
        raise ValueError('Invalid calibration direction/margin. Run with --recalibrate.')
    return data

def capture_boundary(settings):
    """Record the fixed 30s protocol, calculate settings, discard temporary audio."""
    import sounddevice as sd
    import soundfile as sf
    from dbag.audio.attribution import calibrate
    if not settings.input_name:
        raise ValueError('Set input_name in config.local.toml or pass --input-name.')
    devices = sd.query_devices()
    matches = [i for i, device in enumerate(devices)
               if settings.input_name.casefold() in device['name'].casefold()
               and device['max_input_channels'] >= 2]
    if len(matches) != 1:
        raise ValueError('Select exactly one stereo receiver with --input-name.')
    device = matches[0]
    rate = int(devices[device]['default_samplerate'])
    print('\nCalibration: keep each microphone in its normal position.')
    print('Person 1 uses channel 1; person 2 uses channel 2.')
    print('Person 1 speaks for 15 seconds, then person 2 for 15 seconds. Only one speaks at a time.')
    input('Press Enter when both people are ready (Ctrl+C cancels): ')
    print('PERSON 1: speak now. Person 2 stays silent.', flush=True)
    try:
        audio = sd.rec(rate * 30, samplerate=rate, channels=2,
                       dtype='float32', device=device)
        for second in range(30):
            sd.sleep(1000)
            if second == 14:
                print('PERSON 2: speak now. Person 1 stays silent.', flush=True)
        status = sd.wait()
        if status:
            raise ValueError(f'Calibration audio warning: {status}. Please retry.')
    finally:
        sd.stop()
    with tempfile.TemporaryDirectory(prefix='collaboration-calibration-') as directory:
        folder = Path(directory)
        sf.write(folder / 'stereo.wav', audio, rate, subtype='FLOAT')
        boundary = calibrate(folder, settings)
    return {**boundary, 'input_name': devices[device]['name'],
            'activity_db': settings.activity_db, 'window_seconds': settings.window_seconds,
            'created_utc': datetime.now(timezone.utc).isoformat(), 'schema_version': 1}

def ensure_calibration(folder, settings, force=False):
    """Load settings, migrate a legacy boundary once, or interactively create it.

    Failed or cancelled recalibration never overwrites a working boundary.
    Subsequent runs need only speaker_attribution.json, not stereo.wav.
    """
    folder = Path(folder)
    path = folder / 'speaker_attribution.json'
    if path.is_file() and not force:
        data = json.loads(path.read_text(encoding='utf-8'))
        if 'direction' in data:
            return read_boundary(path)
        if (folder / 'stereo.wav').is_file():
            from dbag.audio.attribution import calibration_direction
            data['direction'] = calibration_direction(folder, data['threshold_db'],
                settings.window_seconds, settings.activity_db)
        else:
            print('Saved calibration has no speaker direction. Creating a new calibration.')
            data = capture_boundary(settings)
    else:
        data = capture_boundary(settings)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    read_boundary(temporary)
    temporary.replace(path)
    print(f'Calibration saved: {path.resolve()}', flush=True)
    return data

def main():
    parser = argparse.ArgumentParser(description='Record a fresh 30-second speaker calibration.')
    args = parse_settings(parser, ('audio', 'attribution', 'pilot'))
    try:
        ensure_calibration(args.calibration, args, force=True)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        parser.exit(130, '\nCalibration cancelled; previous settings preserved.\n')

if __name__ == '__main__':
    main()
