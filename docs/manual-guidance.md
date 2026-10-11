# Online manual guidance prototype

Copy messaging_online.py, messaging_core.py and recover_guidance.py into your existing collaboration-mvp folder. Keep them together. Your previous messaging.py stays available. If updating, replace the existing online files after stopping the launcher.

Python standard library only; no additional Python packages.

## First test

1. Stop the old messaging server with Control+C. Leave audio/Whisper separate.
2. Install Cloudflare's connector on your Mac. If Homebrew is already installed: `brew install cloudflared`. Otherwise follow https://developers.cloudflare.com/tunnel/downloads/ .
3. In VS Code terminal A run:

   ```sh
   cloudflared tunnel --url http://127.0.0.1:8766
   ```

   Copy the HTTPS address ending in .trycloudflare.com that it prints. Keep this terminal open. Until step 4, backend connection errors are expected.

4. In a second VS Code terminal, from your project folder, run the following, replacing the example address with the one just printed:

   ```sh
   source .venv/bin/activate
   python messaging_online.py --public-origin https://YOUR-ADDRESS.trycloudflare.com
   ```

5. On your Mac open http://127.0.0.1:8765/operator . Copy the COMPLETE student link shown there, including /student?token=... . Opening the bare tunnel address gives a deliberate denial.
6. On your iPhone turn Wi-Fi off and open that complete link using mobile data. Send a harmless test guidance from the Mac. Confirm it appears on the phone and the operator page reports “Affiché”. Refresh the phone and check the message remains. Private operator notes should never appear on the phone.
7. Stop the Python server with Control+C, then stop the tunnel with Control+C. The local guidance_sessions folder contains events.jsonl and guidance_recap.csv. CSV is also downloadable during a session.

## Automatic saving

There is no End Session button. Stop using Control+C in your launcher terminal and wait for saving to finish.

guidance_recap.csv is created at session start and updated automatically after every sent message and display confirmation, without needing to download it. The operator page displays its full local path and a warning if a CSV update fails. CSV snapshots are written to a temporary file, flushed to disk, and atomically replaced; a failed update does not truncate the previous snapshot.

events.jsonl is a separate incremental journal, flushed to disk for each event. Both files stay in guidance_sessions/SESSION_ID after closing the browser, stopping the server or losing the tunnel connection. Stopping the application does not delete them. These are local copies on the same disk, not protection against disk failure or deletion; copy completed research sessions to your approved backup location.

If the program crashes between writing an event and updating its CSV snapshot, rebuild from the journal:

```sh
python recover_guidance.py guidance_sessions/YOUR_SESSION_FOLDER
```

This creates guidance_recap_recovered.csv without changing the originals. A partially written last event is skipped with a warning; an event that never reached disk cannot be recovered.

## What is shared

The student HTTPS service shares guidance text, message identifiers, send timestamps, session status and session identifier. It receives screen heartbeats and display confirmations. Private notes and categories are served only to the local operator. Cloudflare transports the student traffic; this is no longer an entirely local messaging connection. Audio, video and Whisper transcripts are not connected to this app and stay wherever you record them.

Anyone holding the full student link can view that session's guidance and submit display confirmations. The link is an access secret, not individual identity verification. Use non-sensitive demo messages for this initial test. For the actual student pilot, agree the external service and data handling with your institution and configure appropriate access control.

The tunnel targets only the student listener (8766). The operator listener (8765) stays on localhost. The student listener rejects operator routes even if a proxy forwards localhost headers. Do not tunnel 8765.

## Limits and troubleshooting

Quick Tunnels are temporary test services, with no uptime guarantee. The address changes on restart; restart this application with the new --public-origin and share its new student link. The local session also starts afresh on each Python launch; old sessions remain in files but are not reloaded into the screen.

Both the Mac and the viewing device need Internet, but do not need the same Wi-Fi. Mac sleep or a closed tunnel interrupts delivery. Students keep the latest received message visible; the screen reconnects automatically when the service returns. “Affiché” confirms a visible page rendered the latest message, not that students read it. Messages sent during disconnection remain in history, but do not receive false display confirmations.

The saved time origin is messaging-server start, independent of audio/video. Use a synchronization event when recording the pilot.

If institutional network protection blocks cloudflared, ask IT for an approved connection or test on a permitted network. Do not disable managed security controls.

Official documentation: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
