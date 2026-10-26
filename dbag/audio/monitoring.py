#!/usr/bin/env python3
"""Local headphone monitoring with automatic device reconnection.

Use python -m dbag.tools.list_devices to find initial device numbers, then run
python -m dbag.audio.monitoring --input INPUT_NUMBER --output HEADPHONE_NUMBER.
Recording runs separately and is unaffected by monitoring reconnects.
"""
import argparse
import time
import numpy as np
from dbag.config import parse_settings


def resolve_device(sd, name, hostapi, direction):
    """Resolve an exact device identity again; never fall back to speakers."""
    matches = [i for i, device in enumerate(sd.query_devices())
               if device['name'] == name and device['hostapi'] == hostapi
               and device[f'max_{direction}_channels'] > 0]
    if len(matches) != 1:
        raise ValueError(f'Waiting for a unique {direction} device: {name}')
    return matches[0]


def monitor(sd, source, target, gain, samplerate=None):
    """Retry only this process's audio streams, keeping device names pinned."""
    while True:
        try:
            input_id = resolve_device(sd, source['name'], source['hostapi'], 'input')
            output_id = resolve_device(sd, target['name'], target['hostapi'], 'output')
            current_source = sd.query_devices(input_id, 'input')
            current_target = sd.query_devices(output_id, 'output')
            if current_source['max_input_channels'] < 2:
                raise ValueError('Receiver no longer provides two input channels')
            rate = samplerate or int(current_source['default_samplerate'])
            outputs = min(2, current_target['max_output_channels'])
            last_callback = [time.monotonic()]
            warnings = [0]

            def callback(indata, outdata, frames, timing, status):
                last_callback[0] = time.monotonic()
                if status:
                    warnings[0] += 1
                mixed = (indata[:, 0] + indata[:, 1]) * (0.5 * gain)
                np.clip(mixed, -1.0, 1.0, out=mixed)
                outdata[:] = mixed[:, None]

            with sd.Stream(device=(input_id, output_id), channels=(2, outputs),
                           samplerate=rate, dtype='float32', latency='high',
                           callback=callback) as stream:
                print(f'Monitoring connected: {target["name"]}', flush=True)
                last_warnings = 0
                warning_intervals = 0
                while stream.active:
                    time.sleep(0.5)
                    if time.monotonic() - last_callback[0] > 3:
                        raise ValueError('Monitoring audio callbacks stopped')
                    if resolve_device(sd, target['name'], target['hostapi'], 'output') != output_id:
                        raise ValueError('Headphone device changed')
                    if warnings[0] != last_warnings:
                        print(f'Audio buffer warnings: {warnings[0]}. Check for listening glitches.', flush=True)
                        last_warnings = warnings[0]
                        warning_intervals += 1
                        if warning_intervals >= 1:
                            raise ValueError('Persistent audio buffer problems; reopening headphone stream')
                    else:
                        warning_intervals = 0
                raise ValueError('Monitoring stream stopped')
        except (sd.PortAudioError, ValueError) as error:
            print(f'Monitoring unavailable: {error}. Retrying; recording is unaffected.', flush=True)
            time.sleep(2)
            # PortAudio can cache device enumeration. This dedicated process owns
            # only monitoring streams, now closed; recording uses another process.
            # sounddevice has no public API for refreshing PortAudio devices.
            try:
                sd._terminate()
                sd._initialize()
            except sd.PortAudioError as error:
                print(f'Audio device refresh failed: {error}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=int, required=True, help='Initial receiver device number')
    parser.add_argument('--output', type=int, required=True, help='Initial headphone output device number')
    parser.add_argument('--samplerate', type=int, help='Default: receiver sample rate')
    args = parse_settings(parser, ('audio',))
    import sounddevice as sd
    try:
        source = sd.query_devices(args.input, 'input')
        target = sd.query_devices(args.output, 'output')
        if source['max_input_channels'] < 2:
            parser.error('Choose the two-channel Wireless Mic Rx receiver as input.')
        if source['hostapi'] != target['hostapi']:
            parser.error('Input and output must use the same audio host API.')
        print(f'Input: {source["name"]}', flush=True)
        print(f'Output: {target["name"]}', flush=True)
        print('Start with a low headphone volume. Both microphones play in both ears.', flush=True)
        print('Monitoring only: leave your recording script running separately.', flush=True)
        print('Control+C stops listening only.', flush=True)
        monitor(sd, source, target, args.monitor_gain, args.samplerate)
    except KeyboardInterrupt:
        print('\nMonitoring stopped. Your separate recording process is unaffected.', flush=True)
    except (sd.PortAudioError, ValueError) as error:
        parser.exit(1, f'Could not start monitoring: {error}\nRun python -m sounddevice to check current device numbers.\n')


if __name__ == '__main__':
    main()
