#!/usr/bin/env python3
"""Local headphone monitoring only. Does not record, transcribe or upload audio.

Run python -m sounddevice to find device numbers, then:
python monitor_audio.py --input INPUT_NUMBER --output HEADPHONE_NUMBER
Use headphones, not speakers, to avoid feedback. Keep live_speakers.py running
separately for recording. Concurrent access must be tested on your Mac.
"""
import argparse
import time
import numpy as np
from dbag.config import parse_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=int, required=True, help='Receiver device number')
    parser.add_argument('--output', type=int, required=True, help='Headphone output device number')
    parser.add_argument('--samplerate', type=int, help='Default: receiver sample rate')
    args = parse_settings(parser, ('audio',))
    import sounddevice as sd
    args.gain = args.monitor_gain
    if not 0 <= args.gain <= 2:
        parser.error('--gain must be between 0 and 2')
    try:
        source = sd.query_devices(args.input, 'input')
        target = sd.query_devices(args.output, 'output')
        if source['max_input_channels'] < 2:
            parser.error('Choose the two-channel Wireless Mic Rx receiver as input.')
        if source['hostapi'] != target['hostapi']:
            parser.error('Input and output must use the same audio host API.')
        rate = args.samplerate or int(source['default_samplerate'])
        outputs = min(2, target['max_output_channels'])
        sd.check_input_settings(device=args.input, channels=2, dtype='float32', samplerate=rate)
        sd.check_output_settings(device=args.output, channels=outputs, dtype='float32', samplerate=rate)
        warnings = [0]

        def callback(indata, outdata, frames, timing, status):
            if status:
                warnings[0] += 1
            # Listen to both microphones in both ears; saved stereo is unchanged.
            mixed = (indata[:, 0] + indata[:, 1]) * (0.5 * args.gain)
            np.clip(mixed, -1.0, 1.0, out=mixed)
            outdata[:] = mixed[:, None]

        print(f'Input: {source["name"]}', flush=True)
        print(f'Output: {target["name"]}', flush=True)
        print('Start with a low headphone volume. Both microphones play in both ears.', flush=True)
        print('Monitoring only: leave your recording script running separately.', flush=True)
        print('Control+C stops listening only.', flush=True)
        with sd.Stream(device=(args.input, args.output), channels=(2, outputs),
                       samplerate=rate, dtype='float32', latency='low',
                       callback=callback) as stream:
            last_warnings = 0
            while stream.active:
                time.sleep(0.5)
                if warnings[0] != last_warnings:
                    print(f'Audio buffer warnings: {warnings[0]}. Check for listening glitches.', flush=True)
                    last_warnings = warnings[0]
            print('Monitoring stream stopped unexpectedly. Check your devices.', flush=True)
    except KeyboardInterrupt:
        print('\nMonitoring stopped. Your separate recording process is unaffected.', flush=True)
    except (sd.PortAudioError, ValueError) as error:
        parser.exit(1, f'Could not start monitoring: {error}\nRun python -m sounddevice to check current device numbers.\n')


if __name__ == '__main__':
    main()
