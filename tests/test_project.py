import argparse
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import numpy as np
import soundfile as sf
from dbag.config import DEFAULTS, parse_settings, child_options
from dbag.audio.attribution import calibrate, classify
from dbag.guidance import server

class ConfigurationTests(unittest.TestCase):
    def test_cli_overrides_file_and_reaches_children(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'settings.toml'
            config.write_text('[audio]\ninput_name="receiver"\n[guidance]\noperator_port=9001\nstudent_port=9002\n[transcription]\noffline=false\n')
            argv = ['test', '--config', str(config), '--operator-port', '9010', '--model', 'custom-model']
            with patch.object(sys, 'argv', argv):
                args = parse_settings(argparse.ArgumentParser(), tuple(DEFAULTS))
            self.assertEqual(args.operator_port, 9010)
            self.assertEqual(
                args.recordings_dir,
                (Path(directory) / 'recordings').resolve(),
            )       
            command = child_options(args, ('audio', 'guidance', 'transcription'))
            with patch.object(sys, 'argv', ['test'] + command):
                child = parse_settings(argparse.ArgumentParser(), ('audio', 'guidance', 'transcription'))
            self.assertEqual(child.operator_port, 9010)
            self.assertEqual(child.model, 'custom-model')
            self.assertFalse(child.offline)
            self.assertEqual(child.input_name, 'receiver')

    def test_invalid_ports_and_unknown_configuration_fail(self):
        with patch.object(sys, 'argv', ['test', '--operator-port', '8766']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_settings(argparse.ArgumentParser(), ('guidance',))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.toml'
            path.write_text('[audio]\ninput_nam="typo"\n')
            with patch.object(sys, 'argv', ['test', '--config', str(path)]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parse_settings(argparse.ArgumentParser(), ('audio',))

class AttributionTests(unittest.TestCase):
    def test_calibration_and_reverse_orientation(self):
        settings = SimpleNamespace(**DEFAULTS['attribution'])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            rate = 16000
            wave = np.sin(2 * np.pi * 440 * np.arange(rate * 30) / rate)
            gains = np.tile([0.3, 0.03], (len(wave), 1))
            gains[rate * 15:] = [0.03, 0.3]
            audio = wave[:, None] * gains
            sf.write(folder / 'stereo.wav', audio, rate, subtype='FLOAT')
            result = calibrate(folder, settings)
            self.assertEqual(result['direction'], 1)
            self.assertAlmostEqual(result['threshold_db'], 0, places=4)
            self.assertEqual(classify(np.array([-10, -30]), 0, 3, 1, -50), 'person_1')
            self.assertEqual(classify(np.array([-30, -10]), 0, 3, 1, -50), 'person_2')
            self.assertEqual(classify(np.array([-60, -60]), 0, 3, 1, -50), 'low_audio')
            self.assertEqual(classify(np.array([-20, -21]), 0, 3, 1, -50), 'uncertain')
            sf.write(folder / 'stereo.wav', audio[:, ::-1], rate, subtype='FLOAT')
            reverse = calibrate(folder, settings)
            self.assertEqual(reverse['direction'], -1)
            self.assertEqual(classify(np.array([-30, -10]), 0, 3, -1, -50), 'person_1')
            sf.write(folder / 'stereo.wav', np.column_stack([wave, wave]), rate, subtype='FLOAT')
            with self.assertRaises(ValueError):
                calibrate(folder, settings)

    def test_offline_command_writes_correct_spans(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            rate = 1600
            sample = np.sin(np.arange(rate * 30) * 0.7)
            audio = np.column_stack([sample * 0.3, sample * 0.03])
            audio[rate * 15:] = audio[rate * 15:, ::-1]
            sf.write(folder / 'stereo.wav', audio, rate, subtype='FLOAT')
            process = subprocess.run([sys.executable, '-m', 'dbag.audio.attribution', str(folder)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            data = json.loads((folder / 'speaker_attribution.json').read_text())
            self.assertEqual([s['label'] for s in data['spans']], ['person_1', 'person_2'])
            self.assertEqual(data['spans'][-1]['end'], 30.0)

class GuidanceTests(unittest.TestCase):
    def test_student_listener_cannot_access_operator_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            http = server.core.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            http.student_only = True
            session = server.Session(Path(directory), http.server_port, 'https://test.trycloudflare.com')
            http.session = session
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                for route in ('/operator', '/api/operator', '/api/export'):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(base + route)
                    self.assertEqual(error.exception.code, 403)
                with urllib.request.urlopen(base + '/student?token=' + session.token) as response:
                    self.assertEqual(response.status, 200)
                session.end()
                self.assertTrue((session.folder / 'guidance_recap.csv').is_file())
            finally:
                http.shutdown()
                thread.join()
                http.server_close()

class RecordingTests(unittest.TestCase):
    def test_capture_shutdown_flushes_audio_and_transcription(self):
        from dbag.audio import recording
        # Stream fake drives the real capture queue, segmentation and worker.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calibration = root / 'calibration'
            calibration.mkdir()
            rate = 16000
            signal = np.sin(np.arange(rate * 30) * 0.7)
            audio = np.column_stack([signal * 0.3, signal * 0.03])
            audio[rate * 15:] = audio[rate * 15:, ::-1]
            sf.write(calibration / 'stereo.wav', audio, rate, subtype='FLOAT')
            (calibration / 'speaker_attribution.json').write_text('{"threshold_db":0,"margin_db":3}')
            class FakeStream:
                def __init__(self, **kwargs):
                    self.callback = kwargs['callback']
                def __enter__(self):
                    for block in (audio[:1600], audio[rate * 15:rate * 15+1600]):
                        self.callback(block.astype(np.float32), len(block), None, '')
                    # Simulate Ctrl+C after stream capture; finally drains queue.
                    raise KeyboardInterrupt
                def __exit__(self, *args):
                    return False
            fake_device = SimpleNamespace(InputStream=FakeStream, query_devices=lambda: [
                {'name':'Fake Receiver', 'max_input_channels':2, 'default_samplerate':rate}])
            argv = ['test', str(calibration), '--input-name', 'Fake Receiver',
                    '--recordings-dir', str(root / 'outputs'), '--model', 'fake-model']
            with patch.object(sys, 'argv', argv), patch.dict(sys.modules, {'sounddevice': fake_device}), \
                 patch.object(recording, 'transcribe_clip', return_value={'text':'synthetic transcript'}) as whisper, \
                 contextlib.redirect_stdout(io.StringIO()):
                recording.main()
            folder = next((root / 'outputs').iterdir())
            saved, actual_rate = sf.read(folder / 'stereo.wav', always_2d=True)
            self.assertEqual(saved.shape, (3200, 2))
            self.assertEqual(actual_rate, rate)
            turns = [json.loads(line) for line in (folder / 'dialogue.jsonl').read_text().splitlines()]
            self.assertEqual([turn['speaker'] for turn in turns], ['person_1', 'person_2'])
            self.assertEqual(whisper.call_count, 2)
            self.assertEqual(json.loads((folder / 'settings.json').read_text())['model'], 'fake-model')

class CalibrationSetupTests(unittest.TestCase):
    def test_guided_capture_computes_boundary_and_uses_selected_device(self):
        from dbag.audio.calibration import capture_boundary
        settings = SimpleNamespace(**DEFAULTS['attribution'], input_name='Receiver')
        rate = 1600
        wave = np.sin(np.arange(rate * 30) * 0.7)
        audio = np.column_stack([wave * 0.3, wave * 0.03]).astype(np.float32)
        audio[rate * 15:] = audio[rate * 15:, ::-1]
        from unittest.mock import Mock
        device = SimpleNamespace(query_devices=lambda: [{'name':'Receiver',
            'max_input_channels':2, 'default_samplerate':rate}],
            rec=Mock(return_value=audio), sleep=Mock(), wait=Mock(return_value=None), stop=Mock())
        with patch.dict(sys.modules, {'sounddevice': device}), patch('builtins.input', return_value=''), contextlib.redirect_stdout(io.StringIO()) as output:
            result = capture_boundary(settings)
        self.assertEqual(result['direction'], 1)
        self.assertEqual(result['input_name'], 'Receiver')
        self.assertAlmostEqual(result['threshold_db'], 0, places=4)
        self.assertEqual(device.sleep.call_count, 30)
        self.assertEqual(device.rec.call_args.kwargs['device'], 0)
        self.assertIn('PERSON 2', output.getvalue())
        device.stop.assert_called_once()

    def test_first_run_saves_direction_and_reuses_without_audio(self):
        from dbag.audio.calibration import ensure_calibration
        settings = SimpleNamespace(**DEFAULTS['attribution'])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'new-calibration'
            boundary = {'threshold_db': 2.0, 'margin_db': 3.0, 'direction': -1}
            with patch('dbag.audio.calibration.capture_boundary', return_value=boundary) as capture:
                self.assertEqual(ensure_calibration(folder, settings), boundary)
                self.assertEqual(ensure_calibration(folder, settings), boundary)
                self.assertEqual(capture.call_count, 1)
                self.assertFalse((folder / 'stereo.wav').exists())

    def test_cancelled_recalibration_preserves_previous_settings(self):
        from dbag.audio.calibration import ensure_calibration
        settings = SimpleNamespace(**DEFAULTS['attribution'])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / 'speaker_attribution.json'
            original = '{"threshold_db":0,"margin_db":3,"direction":1}'
            path.write_text(original)
            with patch('dbag.audio.calibration.capture_boundary', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    ensure_calibration(folder, settings, force=True)
            self.assertEqual(path.read_text(), original)

class CommandTests(unittest.TestCase):
    def test_imports_have_no_runtime_actions_and_help_works(self):
        modules = ['start_pilot', 'audio.recording', 'audio.calibration', 'audio.monitoring', 'audio.attribution',
                   'transcription.live', 'transcription.turns', 'guidance.core',
                   'guidance.server', 'guidance.recovery', 'tools.check_channels',
                   'tools.review_speakers', 'tools.list_devices']
        for module in modules:
            with self.subTest(module=module):
                with patch.object(sys, 'argv', ['test', '--invalid-import-argument']):
                    importlib.import_module('dbag.' + module)
                if module != 'transcription.live':
                    result = subprocess.run([sys.executable, '-m', 'dbag.' + module, '--help'], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__':
    unittest.main()
