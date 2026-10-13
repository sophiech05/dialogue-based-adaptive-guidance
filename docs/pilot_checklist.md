# Short pilot verification

## Before starting

- Open this extracted project, activate its environment, and confirm CLI help works.
- No old calibration folder is required. Prepare two participants for the first-run calibration.
- Check devices with `python -m dbag.tools.list_devices`.
- Ensure the receiver sends separate channels, with person 1 on channel 1 and person 2 on channel 2.
- Check your Whisper model is cached when `offline = true`.
- Check the configured cloudflared path and that the two guidance ports are free.

## Two-minute check

1. Start `python -m dbag.start_pilot`.
2. Follow the first-run calibration cues if prompted. Verify the printed receiver/headphone names and use a low headphone volume.
3. Open the new student link on a second device and send one guidance message.
4. Speak separately into both microphones, leave a short silence, and make a clear synchronization event.
5. Confirm live speaker labels and text appear, and guidance display confirmation appears.
6. Press Control+C once. Leave the terminal open until the path recap appears.

## Inspect results

- Listen to `stereo.wav`: both channels should have the expected speech without gaps or clipping.
- Open `attribution.jsonl`, `dialogue.jsonl` and `dialogue.txt`.
- Check `settings.json` contains your chosen values.
- Check guidance events and CSV include the sent message and display confirmation.
- Open the launcher's `session.json`, verify the settings and saved output paths.
- Do a second run with one harmless override, such as different free guidance ports, and confirm it reaches the relevant child process.

Only after this check should you adopt the new folder for your next pilot. Keep original recordings/calibration backed up separately.
