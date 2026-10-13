"""Compare stereo channels in an explicit calibration or latest recording."""
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf
from dbag.config import parse_settings

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?', type=Path)
    args = parse_settings(parser, ('audio',))
    folder = args.folder
    if folder is None:
        if not args.recordings_dir.is_dir():
            parser.error('No recordings directory. Supply a recording folder.')
        folders = sorted(p for p in args.recordings_dir.iterdir() if p.is_dir()
            and not p.name.startswith('live_') and (p / 'stereo.wav').is_file())
        if not folders:
            parser.error('No calibration recording found. Supply a recording folder.')
        folder = folders[-1]
    audio, rate = sf.read(folder / 'stereo.wav', always_2d=True)
    if audio.shape[1] != 2 or len(audio) < 2:
        parser.error('Expected a nonempty two-channel recording.')
    print(f'Checking: {folder}')
    middle = len(audio) // 2
    for label, section in [('First half: person 1', audio[:middle]), ('Second half: person 2', audio[middle:])]:
        rms = np.sqrt(np.mean(section ** 2, axis=0))
        difference = 20 * np.log10((rms[0] + 1e-12) / (rms[1] + 1e-12))
        print(f'{label}: channel 1 versus channel 2 {difference:+.1f} dB')
    print('Exactly identical:', np.array_equal(audio[:, 0], audio[:, 1]))
    print('Correlation:', float(np.corrcoef(audio[:, 0], audio[:, 1])[0, 1]))
    print('Maximum sample difference:', float(np.max(np.abs(audio[:, 0] - audio[:, 1]))))

if __name__ == '__main__':
    main()
