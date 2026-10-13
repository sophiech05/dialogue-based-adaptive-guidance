"""List input/output devices without starting an audio stream."""
import argparse

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    import sounddevice as sd
    print(sd.query_devices())

if __name__ == '__main__':
    main()
