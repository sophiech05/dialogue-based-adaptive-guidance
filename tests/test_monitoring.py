import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dbag.audio.monitoring import monitor, resolve_device
from dbag.start_pilot import Launcher


def device(name, inputs=0, outputs=0):
    return dict(name=name, hostapi=0, max_input_channels=inputs,
                max_output_channels=outputs, default_samplerate=48000)


class MonitoringTests(unittest.TestCase):
    def test_exact_identity_rejects_speakers_and_ambiguity(self):
        sd = Mock()
        sd.query_devices.return_value = [device('Speakers', outputs=2)]
        with self.assertRaises(ValueError):
            resolve_device(sd, 'AirPods', 0, 'output')
        sd.query_devices.return_value = [device('AirPods', outputs=2)] * 2
        with self.assertRaises(ValueError):
            resolve_device(sd, 'AirPods', 0, 'output')

    def test_reconnect_resolves_changed_device_number(self):
        source, target = device('RX', inputs=2), device('AirPods', outputs=2)
        devices = [source, target]
        class AudioError(Exception):
            pass
        sd = Mock(PortAudioError=AudioError)
        sd.query_devices.side_effect = lambda index=None, kind=None: devices if index is None else devices[index]
        # First stream stops on disconnect; second simulates user shutdown.
        sd.Stream.side_effect = [contextlib.nullcontext(SimpleNamespace(active=False)), KeyboardInterrupt]
        def refresh():
            devices[:] = [device('Speakers', outputs=2), source, target]
        sd._initialize.side_effect = refresh
        with patch('dbag.audio.monitoring.time.sleep'):
            with self.assertRaises(KeyboardInterrupt):
                monitor(sd, source, target, 1)
        self.assertEqual(sd.Stream.call_args_list[0].kwargs['device'], (0, 1))
        self.assertEqual(sd.Stream.call_args_list[1].kwargs['device'], (1, 2))
        sd._terminate.assert_called_once()

    def test_missing_headphones_wait_without_opening_speakers(self):
        source, target = device('RX', inputs=2), device('AirPods', outputs=2)
        devices = [source, device('Speakers', outputs=2)]
        class AudioError(Exception):
            pass
        sd = Mock(PortAudioError=AudioError)
        sd.query_devices.side_effect = lambda index=None, kind=None: devices if index is None else devices[index]
        sd._initialize.side_effect = lambda: devices.append(target)
        sd.Stream.side_effect = KeyboardInterrupt
        with patch('dbag.audio.monitoring.time.sleep'):
            with self.assertRaises(KeyboardInterrupt):
                monitor(sd, source, target, 1)
        sd.Stream.assert_called_once()
        self.assertEqual(sd.Stream.call_args.kwargs['device'], (0, 2))

    def test_stalled_callbacks_trigger_retry(self):
        source, target = device('RX', inputs=2), device('AirPods', outputs=2)
        class AudioError(Exception):
            pass
        sd = Mock(PortAudioError=AudioError)
        sd.query_devices.side_effect = lambda index=None, kind=None: [source, target] if index is None else [source, target][index]
        sd.Stream.side_effect = [contextlib.nullcontext(SimpleNamespace(active=True)), KeyboardInterrupt]
        with patch('dbag.audio.monitoring.time.sleep'), patch('dbag.audio.monitoring.time.monotonic', side_effect=[0, 4, 5]):
            with self.assertRaises(KeyboardInterrupt):
                monitor(sd, source, target, 1)
        sd._initialize.assert_called_once()

    def test_monitor_exit_is_optional_but_recording_exit_is_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Launcher(Path(directory), Path(directory))
            launcher.children = {'monitor': Mock(), 'recording': Mock(), 'guidance': Mock()}
            launcher.children['monitor'].poll.return_value = 1
            launcher.children['recording'].poll.return_value = None
            launcher.children['guidance'].poll.return_value = None
            launcher.check()
            launcher.check()
            launcher.children['recording'].poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'recording stopped'):
                launcher.check()
