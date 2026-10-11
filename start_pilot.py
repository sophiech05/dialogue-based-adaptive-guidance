#!/usr/bin/env python3
"""Start manual guidance, tunnel, recording/transcription and local listening.

Place alongside your existing live_speakers.py, monitor_audio.py,
messaging_online.py and messaging_core.py. Activate .venv, then run:
    python start_pilot.py
For another headphone output:
    python start_pilot.py --output-name "External Headphones"
Stop previous copies of all four programs before starting. Press Control+C
once and leave the terminal open until saving finishes. Video is separate.
The launcher does not merge the audio and guidance timelines: retain a sync
event. Logs and a path recap are kept in pilot_runs; original audio and
guidance remain in their existing folders. The launcher requires the cached
Whisper model and prevents its Hugging Face network access for this run.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class Launcher:
    def __init__(self, root, folder):
        self.root = root
        self.folder = folder
        self.children = {}
        self.readers = []
        self.events = queue.Queue(maxsize=2000)
        self.stopping = False
        self.requested_stop = False
        self.manifest = {'started_utc': utc(), 'status': 'starting', 'processes': {}}
        self.save()

    def save(self):
        temporary = self.folder / 'session.tmp'
        temporary.write_text(json.dumps(self.manifest, indent=2), encoding='utf-8')
        temporary.replace(self.folder / 'session.json')

    def spawn(self, name, command, env=None):
        process = subprocess.Popen(command, cwd=self.root, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1, start_new_session=True)
        self.children[name] = process
        self.manifest['processes'][name] = {'pid': process.pid, 'started_utc': utc(),
                                          'log': str(self.folder / (name + '.log'))}
        self.save()

        def reader():
            with (self.folder / (name + '.log')).open('w', encoding='utf-8') as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        self.events.put_nowait((name, line.rstrip()))
                    except queue.Full:
                        pass  # Complete output is still retained in the log file.
            process.stdout.close()

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        self.readers.append(thread)

    def check(self):
        if self.requested_stop:
            raise KeyboardInterrupt
        for name, process in self.children.items():
            code = process.poll()
            if code is not None:
                raise RuntimeError(f'{name} stopped (exit {code}). See {self.folder / (name + ".log")}')

    def next_event(self, timeout=0.2):
        try:
            name, line = self.events.get(timeout=timeout)
        except queue.Empty:
            return None
        if name != 'tunnel':
            print(f'[{name}] {line}', flush=True)
        return name, line

    def wait_line(self, name, pattern, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check()
            event = self.next_event()
            if event and event[0] == name:
                match = re.search(pattern, event[1])
                if match:
                    return match
        raise RuntimeError(f'{name} was not ready after {seconds}s. See its log in {self.folder}')

    def shutdown(self):
        self.stopping = True
        print('\nStopping. Please keep this terminal open while files finish saving.', flush=True)
        # Stop listening and capture promptly; stop guidance and tunnel as well.
        for name in ('monitor', 'recording', 'guidance', 'tunnel'):
            process = self.children.get(name)
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        # Never automatically kill the recording worker while it saves/transcribes.
        for name, process in self.children.items():
            last_notice = time.monotonic()
            while process.poll() is None:
                self.next_event()
                if time.monotonic() - last_notice > 10:
                    print(f'Waiting for {name} to finish. Do not close the terminal.', flush=True)
                    last_notice = time.monotonic()
            self.manifest['processes'][name]['exit_code'] = process.returncode
        for reader in self.readers:
            reader.join(timeout=2)
        while not self.events.empty():
            self.next_event(0)
        self.manifest['stopped_utc'] = utc()
        self.manifest['status'] = 'stopped'
        # These paths are written by the existing children when they save.
        for name, prefix, key in (('recording', 'Saved session to: ', 'audio_folder'),
                                  ('guidance', 'Logs: ', 'guidance_folder')):
            log = self.folder / (name + '.log')
            if log.exists():
                for line in log.read_text(encoding='utf-8').splitlines():
                    if line.startswith(prefix):
                        self.manifest[key] = line[len(prefix):].strip()
        self.save()
        print(f'Launcher recap: {self.folder / "session.json"}', flush=True)
        for key in ('audio_folder', 'guidance_folder'):
            if key in self.manifest:
                print(f'{key}: {self.manifest[key]}', flush=True)
        print('Check the saved stereo.wav before treating the recording as complete.', flush=True)


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration', type=Path, default=Path('recordings/20261008_093805_608310'))
    parser.add_argument('--output-name', default='AirPods', help='Unique headphone device name fragment')
    parser.add_argument('--cloudflared', type=Path, default=Path.home() / 'Tools/cloudflared/cloudflared')
    parser.add_argument('--operator-port', type=int, default=8765)
    parser.add_argument('--student-port', type=int, default=8766)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    calibration = args.calibration if args.calibration.is_absolute() else root / args.calibration
    for filename in ('live_speakers.py', 'monitor_audio.py', 'messaging_online.py', 'messaging_core.py'):
        if not (root / filename).is_file():
            parser.error(f'Place {filename} in the same project folder as this launcher.')
    for filename in ('stereo.wav', 'speaker_attribution.json'):
        if not (calibration / filename).is_file():
            parser.error(f'Missing calibration file: {calibration / filename}')
    if not args.cloudflared.is_file() or not os.access(args.cloudflared, os.X_OK):
        parser.error(f'Cannot run cloudflared: {args.cloudflared}')
    for module in ('sounddevice', 'soundfile', 'numpy', 'scipy', 'mlx_whisper'):
        if importlib.util.find_spec(module) is None:
            parser.error(f'Missing {module}. Activate your project .venv first.')
    import sounddevice as sd
    devices = sd.query_devices()
    inputs = [i for i, device in enumerate(devices)
              if 'Wireless Mic Rx' in device['name'] and device['max_input_channels'] >= 2]
    outputs = [i for i, device in enumerate(devices)
               if args.output_name.casefold() in device['name'].casefold()
               and device['max_output_channels'] >= 2]
    if len(inputs) != 1 or len(outputs) != 1:
        parser.error('Connect the receiver and headphones. For another headset use '
                     '--output-name "its device name". Run python -m sounddevice to list devices.')
    if devices[inputs[0]]['hostapi'] != devices[outputs[0]]['hostapi']:
        parser.error('Receiver and headphones must use the same audio host API.')
    for port in (args.operator_port, args.student_port):
        if not 1 <= port <= 65535:
            parser.error('Ports must be between 1 and 65535.')
    if args.operator_port == args.student_port:
        parser.error('Operator and student ports must differ.')
    # Detect old servers before starting anything.
    import socket
    for port in (args.operator_port, args.student_port):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                parser.error(f'Port {port} is in use. Stop the previous messaging server first.')
    print(f'Receiver: {devices[inputs[0]]["name"]}', flush=True)
    print(f'Headphones: {devices[outputs[0]]["name"]}', flush=True)
    print('Stop any previously running audio scripts first. Start at low headphone volume.', flush=True)
    folder = root / 'pilot_runs' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True)
    launcher = Launcher(root, folder)
    launcher.manifest.update(calibration=str(calibration),
                             input_name=devices[inputs[0]]['name'],
                             output_name=devices[outputs[0]]['name'])

    def stop_requested(signum, frame):
        if launcher.stopping:
            print('Still saving. The launcher will not force-kill the recording.', flush=True)
        else:
            launcher.requested_stop = True

    signal.signal(signal.SIGINT, stop_requested)
    signal.signal(signal.SIGTERM, stop_requested)
    failed = False
    try:
        print('Starting tunnel…', flush=True)
        launcher.spawn('tunnel', [str(args.cloudflared), 'tunnel', '--url',
                                  f'http://127.0.0.1:{args.student_port}'])
        origin = launcher.wait_line('tunnel', r'https://[a-z0-9-]+\.trycloudflare\.com', 90).group(0)
        # Do not publish the student token in launcher output or its manifest.
        launcher.spawn('guidance', [sys.executable, '-u', str(root / 'messaging_online.py'),
                                   '--public-origin', origin,
                                   '--operator-port', str(args.operator_port),
                                   '--student-port', str(args.student_port)])
        launcher.wait_line('guidance', r'^Operator:', 20)
        operator = f'http://127.0.0.1:{args.operator_port}/operator'
        with urllib.request.urlopen(operator, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError('Operator screen is not responding.')
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', PYTHONUNBUFFERED='1')
        launcher.spawn('recording', [sys.executable, '-u', str(root / 'live_speakers.py'), str(calibration)], env)
        launcher.wait_line('recording', r'Listening to both people', 90)
        launcher.spawn('monitor', [sys.executable, '-u', str(root / 'monitor_audio.py'),
                                  '--input', str(inputs[0]), '--output', str(outputs[0])])
        # The existing script announces setup just before opening its stream.
        launcher.wait_line('monitor', r'Control\+C stops listening only', 20)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            launcher.check()
            launcher.next_event()
        launcher.manifest.update(status='running', operator_url=operator,
                                 ready_utc=utc(), public_origin=origin)
        launcher.save()
        if not args.no_browser:
            webbrowser.open(operator)
        print(f'\nAll four programs are running. Operator: {operator}', flush=True)
        print('Copy the NEW student link from the operator screen. Make your synchronization event.', flush=True)
        print('Control+C stops this run and waits for files to finish saving.', flush=True)
        print(f'Logs: {folder}', flush=True)
        while True:
            launcher.check()
            launcher.next_event()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        failed = True
        launcher.manifest['error'] = str(error)
        print(f'\nStartup/run error: {error}', flush=True)
    finally:
        launcher.shutdown()
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
