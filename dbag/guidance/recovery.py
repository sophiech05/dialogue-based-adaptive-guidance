#!/usr/bin/env python3
"""Rebuild a CSV from a session's saved events.jsonl without changing originals."""
import argparse
import json
from pathlib import Path
import threading
from dbag.guidance.core import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session_folder', type=Path)
    args = parser.parse_args()
    journal = args.session_folder / 'events.jsonl'
    lines = journal.read_text(encoding='utf-8').splitlines()
    messages = {}
    session_id = None
    for index, line in enumerate(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                print('Ignoring an incomplete final event after an interrupted write.')
                break
            raise
        session_id = event['session_id']
        if event['event'] == 'guidance_sent':
            messages[event['message_id']] = {
                'id': event['message_id'], 'sent_utc': event['utc'],
                'sent_elapsed_s': event['elapsed_s'], 'text': event['text'],
                'category': event['category'], 'operator_note': event['operator_note'],
                'deliveries': []}
        elif event['event'] == 'guidance_display_confirmed':
            message = messages.get(event['message_id'])
            if message and not any(d['client_id'] == event['client_id'] for d in message['deliveries']):
                message['deliveries'].append({'client_id': event['client_id'],
                    'displayed_utc': event['utc'], 'displayed_elapsed_s': event['elapsed_s']})
    if not session_id:
        parser.error('No valid saved events found.')
    session = Session.__new__(Session)
    session.lock = threading.RLock()
    session.session_id = session_id
    session.messages = list(messages.values())
    output = args.session_folder / 'guidance_recap_recovered.csv'
    output.write_bytes(session.export())
    print(f'Recovered {len(messages)} messages: {output.resolve()}')


if __name__ == '__main__':
    main()
