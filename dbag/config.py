"""Shared defaults, local TOML configuration, validation and CLI overrides.

Precedence: command line > config.local.toml (or --config) > DEFAULTS.
Relative output/calibration paths resolve from the configuration directory,
or the current project directory when no configuration file exists.
"""
import argparse
from pathlib import Path
import math
import tomllib

DEFAULTS = {
    'audio': {'input_name': '', 'output_name': '', 'monitor_gain': 1.0,
              'recordings_dir': 'recordings'},
    'transcription': {'model': 'mlx-community/whisper-small-mlx', 'language': 'fr',
                      'initial_prompt': 'Discussion en français entre élèves sur des mesures scientifiques, des données, des capteurs et des hypothèses.',
                      'offline': True, 'recent_seconds': 60.0, 'context_seconds': 0.15},
    'attribution': {'activity_db': -50.0, 'window_seconds': 0.1,
                    'threshold_db': None, 'margin_db': None, 'pause_seconds': 0.6,
                    'max_turn_seconds': 15.0, 'minimum_gap_db': 6.0,
                    'maximum_margin_db': 3.0},
    'guidance': {'operator_port': 8765, 'student_port': 8766,
                 'guidance_dir': 'guidance_sessions'},
    'pilot': {'calibration': 'calibration_data', 'cloudflared': 'cloudflared',
              'pilot_dir': 'pilot_runs', 'open_browser': True},
}
PATH_KEYS = {'recordings_dir', 'guidance_dir', 'pilot_dir', 'calibration'}
OPTIONAL_FLOATS = {'threshold_db', 'margin_db'}

def parse_settings(parser, groups):
    """Add group options and return validated settings alongside command args."""
    parser.add_argument('--config', type=Path, help='Local TOML file; auto-loads ./config.local.toml')
    probe = argparse.ArgumentParser(add_help=False)
    probe.add_argument('--config', type=Path)
    selected, _ = probe.parse_known_args()
    config = (selected.config or Path.cwd() / 'config.local.toml').expanduser().resolve()
    if selected.config and not config.is_file():
        parser.error(f'Configuration does not exist: {config}')
    values = {group: dict(defaults) for group, defaults in DEFAULTS.items()}
    if config.is_file():
        try:
            loaded = tomllib.loads(config.read_text(encoding='utf-8'))
            for group, entries in loaded.items():
                if group not in values or not isinstance(entries, dict):
                    raise ValueError(f'Unknown configuration section: {group}')
                for key, value in entries.items():
                    if key not in values[group]:
                        raise ValueError(f'Unknown setting: {group}.{key}')
                    default = DEFAULTS[group][key]
                    expected = float if key in OPTIONAL_FLOATS else (str if default is None else type(default))
                    if expected is float:
                        valid = type(value) in (float, int)
                    else:
                        valid = type(value) is expected
                    if not valid:
                        raise ValueError(f'{group}.{key} must be {expected.__name__}')
                    values[group][key] = value
        except (OSError, ValueError) as error:
            parser.error(str(error))
    base = config.parent if config.is_file() else Path.cwd().resolve()
    for group in groups:
        options = parser.add_argument_group(group + ' settings')
        for key, default in values[group].items():
            kind = float if key in OPTIONAL_FLOATS else (str if default is None else type(DEFAULTS[group][key]))
            if key in PATH_KEYS:
                kind = Path
            flags = ['--' + key.replace('_', '-')]
            kwargs = {'default': default, 'type': kind, 'help': f'Config: [{group}] {key}'}
            if kind is bool:
                kwargs.pop('type')
                kwargs['action'] = argparse.BooleanOptionalAction
            options.add_argument(*flags, **kwargs)
    args = parser.parse_args()
    args.project_root = base
    args.config = config if config.is_file() else None
    for key, value in vars(args).items():
        if isinstance(value, float) and not math.isfinite(value):
            parser.error(f'--{key.replace("_", "-")} must be finite')
    for key in PATH_KEYS:
        value = getattr(args, key, None)
        if value is not None:
            path = Path(value).expanduser()
            setattr(args, key, (path if path.is_absolute() else base / path).resolve())
    if hasattr(args, 'cloudflared'):
        value = str(args.cloudflared)
        if '/' in value or value.startswith('~'):
            path = Path(value).expanduser()
            args.cloudflared = str((path if path.is_absolute() else base / path).resolve())
    def invalid(message):
        parser.error(message)
    for key in ('window_seconds', 'pause_seconds', 'max_turn_seconds', 'recent_seconds', 'minimum_gap_db', 'maximum_margin_db'):
        if hasattr(args, key) and getattr(args, key) <= 0:
            invalid(f'--{key.replace("_", "-")} must be positive')
    for key in ('margin_db', 'context_seconds'):
        if getattr(args, key, None) is not None and getattr(args, key) < 0:
            invalid(f'--{key.replace("_", "-")} must be nonnegative')
    if hasattr(args, 'monitor_gain') and not 0 <= args.monitor_gain <= 2:
        invalid('--monitor-gain must be between 0 and 2')
    if hasattr(args, 'operator_port'):
        if not all(1 <= p <= 65535 for p in (args.operator_port, args.student_port)):
            invalid('Ports must be between 1 and 65535')
        if args.operator_port == args.student_port:
            invalid('Operator and student ports must differ')
    return args

def child_options(args, groups):
    """Propagate effective settings, including CLI overrides, to child processes."""
    result = []
    for group in groups:
        for key in DEFAULTS[group]:
            value = getattr(args, key)
            flag = '--' + key.replace('_', '-')
            if isinstance(value, bool):
                result.append(flag if value else '--no-' + key.replace('_', '-'))
            elif value is not None:
                result.extend((flag, str(value)))
    return result
