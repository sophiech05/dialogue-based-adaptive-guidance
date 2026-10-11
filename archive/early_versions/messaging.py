#!/usr/bin/env python3
"""Local, manual guidance interface. Python standard library only."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import uuid


STYLE = """
:root{font-family:system-ui,-apple-system,sans-serif;color:#18332f;background:#f3f5f2}
*{box-sizing:border-box}body{margin:0}main{max-width:1050px;margin:32px auto;padding:0 24px}
header{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:24px}
h1{font-size:28px;margin:8px 0}h2{font-size:18px}small,.muted{color:#60716c}
.card{background:white;border:1px solid #dce4df;border-radius:16px;padding:24px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:20px}label{display:block;margin:14px 0 7px;font-weight:600}
textarea,input,select{width:100%;font:inherit;border:1px solid #b6c8bf;border-radius:8px;padding:12px}
textarea{resize:vertical;min-height:130px}button,.button{font:inherit;border:0;border-radius:9px;padding:12px 18px;background:#176b55;color:white;cursor:pointer;display:inline-block;text-decoration:none}
button:disabled{opacity:.5;cursor:default}.secondary{background:#e8efe9;color:#18332f}
.badge{border-radius:30px;padding:8px 12px;background:#e8efe9;font-size:14px}.bad{background:#ffeadb;color:#853411}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.message{border-top:1px solid #e0e7e2;padding:16px 0}
.message p{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0}.status{font-size:13px;color:#60716c}
.notice{min-height:24px;margin:12px 0;white-space:pre-wrap}.student{max-width:950px}
.guidance{font-size:clamp(24px,3.2vw,38px);line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere}
.new{animation:highlight 1.5s ease}@keyframes highlight{from{background:#d8f0df}to{background:white}}
code{overflow-wrap:anywhere}details{margin-top:20px}summary{cursor:pointer;padding:10px 0}
@media(max-width:760px){.grid{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}main{padding:0 14px}}
"""

OPERATOR = """<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Guidance — opératrice</title><style>__STYLE__</style><main>
<header><div><small>PROTOTYPE · GUIDANCE MANUELLE</small><h1>Votre poste de guidance</h1><div id="session" class="muted"></div></div><span id="connection" class="badge">Connexion…</span></header>
<div class="card"><strong>Écran du groupe</strong><p class="muted">Ouvrez ce lien sur le deuxième Mac, connecté au même réseau. Remplacez ADRESSE_DU_MAC par l’adresse réseau de votre Mac.</p><code id="link"></code><div class="row" style="margin-top:14px"><button id="copy" class="secondary">Copier le lien</button><button id="preview" class="secondary">Tester sur ce Mac</button></div></div>
<div class="grid"><section class="card"><h2>Composer une guidance</h2>
<form id="compose"><label for="text">Message destiné au groupe</label><textarea id="text" maxlength="2000" required placeholder="Tapez votre guidance ici…"></textarea>
<label for="category">Catégorie de recherche</label><select id="category"><option value="unspecified">Non précisée</option><option value="uncertainty">Clarifier l’incertitude</option><option value="data_quality">Examiner les données</option><option value="alternatives">Explorer les explications</option><option value="next_step">Choisir une prochaine étape</option><option value="other">Autre</option></select>
<label for="note">Pourquoi intervenir ? (facultatif, visible seulement ici)</label><textarea id="note" maxlength="2000" style="min-height:75px"></textarea>
<div class="row" style="margin-top:18px"><button id="send" type="submit">Envoyer au groupe</button><span id="length" class="muted">0 / 2000</span></div><div id="notice" class="notice" role="status"></div></form>
</section><section class="card"><h2>Messages envoyés</h2><div id="history"></div></section></div>
<div class="card row"><a class="button secondary" href="/api/export">Télécharger le récapitulatif CSV</a><button id="finish" class="secondary">Terminer la session de messages</button><span class="muted">Audio et Whisper continuent séparément.</span></div>
<p class="muted">« Affiché » signifie qu’un écran actif a confirmé le rendu du message. Cela ne prouve pas sa lecture. Le chronomètre est celui de cette application de messages.</p>
</main><script>
const $=id=>document.getElementById(id);let currentState=null,pending=null,revision='';
function clock(t){return new Date(t).toLocaleTimeString('fr-CH',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
function duration(t){return Math.floor(t/60).toString().padStart(2,'0')+':'+Math.floor(t%60).toString().padStart(2,'0')}
function renderHistory(messages){$('history').replaceChildren();if(!messages.length){$('history').textContent='Aucune guidance envoyée.';return}for(const m of [...messages].reverse()){const div=document.createElement('div');div.className='message';const small=document.createElement('small');small.textContent=clock(m.sent_utc)+' · '+duration(m.sent_elapsed_s)+' · '+m.category;const p=document.createElement('p');p.textContent=m.text;const status=document.createElement('div');status.className='status';status.textContent=m.deliveries.length?'Affiché à '+clock(m.deliveries[0].displayed_utc):'En attente de confirmation d’affichage';div.append(small,p,status);if(m.operator_note){const note=document.createElement('p');note.className='muted';note.textContent='Votre note : '+m.operator_note;div.append(note)}$('history').append(div)}}
async function poll(){try{const r=await fetch('/api/operator',{cache:'no-store'});if(!r.ok)throw Error('Connexion indisponible');currentState=await r.json();$('session').textContent='Session '+currentState.session_id+' · '+duration(currentState.elapsed_s);$('connection').textContent=currentState.active?'Écrans connectés : '+currentState.online_clients:'Session terminée';$('connection').className='badge'+(currentState.active&&!currentState.online_clients?' bad':'');$('link').textContent=currentState.student_url;$('send').disabled=!currentState.active;$('finish').disabled=!currentState.active;const next=JSON.stringify(currentState.messages);if(next!==revision){renderHistory(currentState.messages);revision=next}}catch(e){$('connection').textContent='Serveur déconnecté';$('connection').className='badge bad'}finally{setTimeout(poll,500)}}
$('text').addEventListener('input',()=>$('length').textContent=$('text').value.length+' / 2000');
$('compose').addEventListener('submit',async event=>{event.preventDefault();if(!pending){if(!$('text').value.trim())return;pending={request_id:crypto.randomUUID(),text:$('text').value.trim(),category:$('category').value,operator_note:$('note').value.trim()}}$('send').disabled=true;$('notice').textContent='Envoi…';try{const r=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});const data=await r.json();if(!r.ok)throw Error(data.error||'Envoi impossible');pending=null;$('text').value='';$('note').value='';$('length').textContent='0 / 2000';$('notice').textContent='Message enregistré et envoyé. Vérifiez la confirmation d’affichage.';$('text').focus()}catch(e){$('notice').textContent=e.message+' — cliquez de nouveau sur Envoyer pour réessayer le même message.'}finally{$('send').disabled=!(currentState&&currentState.active)}});
$('copy').onclick=async()=>{if(!currentState)return;try{await navigator.clipboard.writeText(currentState.student_url);$('notice').textContent='Lien copié.'}catch(e){$('notice').textContent='Sélectionnez et copiez le lien affiché.'}};
$('preview').onclick=()=>{if(currentState)window.open(currentState.preview_url,'_blank')};
$('finish').onclick=async()=>{if(!confirm('Terminer cette session ? Les messages resteront visibles.'))return;try{const r=await fetch('/api/end',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error('Impossible de terminer');$('notice').textContent='Session de messages terminée. Le CSV reste disponible.'}catch(e){$('notice').textContent=e.message}};
poll();
</script></html>"""

STUDENT = """<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Guidance — groupe</title><style>__STYLE__</style><main class="student">
<header><div><small>ESPACE DU GROUPE</small><h1>Guidance pour votre activité</h1></div><span id="connection" class="badge">Connexion…</span></header>
<section id="card" class="card" aria-live="polite"><small id="time">Votre activité peut commencer.</small><p id="latest" class="guidance">Les messages de guidance apparaîtront ici.</p></section>
<details><summary>Messages précédents</summary><div id="history" class="card"></div></details>
</main><script>
const $=id=>document.getElementById(id);const token=new URLSearchParams(location.search).get('token');
let client=sessionStorage.getItem('guidance-client');if(!client){client=crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);sessionStorage.setItem('guidance-client',client)}
let last='',messages=[],active=true;const acknowledged=new Set();
function clock(t){return new Date(t).toLocaleTimeString('fr-CH',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
async function acknowledge(){if(document.visibilityState!=='visible')return;const m=messages.at(-1);if(!m||acknowledged.has(m.id))return;await new Promise(resolve=>requestAnimationFrame(resolve));if(document.visibilityState!=='visible')return;try{const r=await fetch('/api/displayed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,client_id:client,message_id:m.id})});if(r.ok)acknowledged.add(m.id)}catch(e){}}
async function poll(){try{const r=await fetch('/api/student?token='+encodeURIComponent(token)+'&client_id='+encodeURIComponent(client),{cache:'no-store'});if(!r.ok)throw Error('Connexion refusée');const state=await r.json();messages=state.messages;active=state.active;$('connection').textContent=active?'Connecté':'Session terminée';$('connection').className='badge';const newest=messages.at(-1);if(newest&&newest.id!==last){last=newest.id;$('latest').textContent=newest.text;$('time').textContent='Guidance envoyée à '+clock(newest.sent_utc);$('card').classList.remove('new');void $('card').offsetWidth;$('card').classList.add('new');$('history').replaceChildren();for(const m of messages.slice(0,-1).reverse()){const div=document.createElement('div');div.className='message';const small=document.createElement('small');small.textContent=clock(m.sent_utc);const p=document.createElement('p');p.textContent=m.text;div.append(small,p);$('history').append(div)}if(messages.length===1)$('history').textContent='Aucun message précédent.'}await acknowledge()}catch(e){$('connection').textContent='Connexion interrompue';$('connection').className='badge bad'}finally{setTimeout(poll,500)}}
document.addEventListener('visibilitychange',acknowledge);poll();
</script></html>"""


class Session:
    def __init__(self, root, port, advertised_host=None):
        self.lock = threading.RLock()
        self.started = time.monotonic()
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S_') + secrets.token_hex(3)
        self.folder = root / self.session_id
        self.folder.mkdir(parents=True, exist_ok=False)
        self.token = secrets.token_urlsafe(24)
        self.port = port
        self.host = advertised_host or self.local_ip()
        self.active = True
        self.messages = []
        self.requests = {}
        self.clients = {}
        self.log('session_started', {'app_version': '1.0', 'timeline': 'messaging_server'})

    @staticmethod
    def local_ip():
        # UDP connect selects an interface; it sends no application data.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(('192.0.2.1', 9))
                return sock.getsockname()[0]
        except OSError:
            return 'ADRESSE_DU_MAC'

    def stamp(self):
        return {'utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                'elapsed_s': round(time.monotonic() - self.started, 3)}

    def log(self, event, fields):
        record = {'session_id': self.session_id, 'event': event, **self.stamp(), **fields}
        with (self.folder / 'events.jsonl').open('a', encoding='utf-8') as file:
            file.write(json.dumps(record, ensure_ascii=False) + '\n')
            file.flush()
            os.fsync(file.fileno())
        return record

    def end(self):
        with self.lock:
            if self.active:
                self.log('session_ended', {})
                self.active = False

    def state(self, operator=False):
        with self.lock:
            state = {'session_id': self.session_id, 'active': self.active,
                     'elapsed_s': self.stamp()['elapsed_s']}
            if operator:
                state.update(messages=self.messages,
                    online_clients=sum(time.monotonic()-t < 5 for t in self.clients.values()),
                    student_url=f'http://{self.host}:{self.port}/student?token={self.token}',
                    preview_url=f'http://127.0.0.1:{self.port}/student?token={self.token}')
            else:
                state['messages'] = [{k: m[k] for k in ('id', 'text', 'sent_utc', 'sent_elapsed_s')}
                                     for m in self.messages]
            # Take a snapshot before releasing the lock.
            return json.loads(json.dumps(state))

    def export(self):
        with self.lock:
            output = io.StringIO(newline='')
            writer = csv.writer(output)
            writer.writerow(['session_id', 'message_id', 'sent_utc', 'sent_elapsed_s',
                             'text', 'category', 'operator_note', 'first_displayed_utc',
                             'first_displayed_elapsed_s', 'display_confirmations'])
            def cell(value):
                # Prevent spreadsheet formulas if free text begins with a formula character.
                return "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value
            for message in self.messages:
                first = message['deliveries'][0] if message['deliveries'] else {}
                writer.writerow([cell(v) for v in [self.session_id, message['id'],
                    message['sent_utc'], message['sent_elapsed_s'], message['text'],
                    message['category'], message['operator_note'], first.get('displayed_utc', ''),
                    first.get('displayed_elapsed_s', ''), len(message['deliveries'])]])
            return output.getvalue().encode('utf-8-sig')


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalGuidance/1.0'

    def log_message(self, *args):
        pass  # Avoid logging the student access token in request URLs.

    @property
    def session(self):
        return self.server.session

    def reply(self, status, data, mime='application/json; charset=utf-8', attachment=None):
        if not isinstance(data, bytes):
            data = (json.dumps(data, ensure_ascii=False) if mime.startswith('application/json') else data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def is_operator(self):
        return (self.client_address[0] in ('127.0.0.1', '::1') and
                urlsplit('http://' + self.headers.get('Host', '')).hostname in ('127.0.0.1', 'localhost'))

    def valid_token(self, token):
        return isinstance(token, str) and secrets.compare_digest(token, self.session.token)

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path in ('/', '/operator'):
            if not self.is_operator():
                return self.reply(403, {'error': 'Operator page is available only on the server Mac.'})
            return self.reply(200, OPERATOR.replace('__STYLE__', STYLE), 'text/html; charset=utf-8')
        if url.path == '/student':
            if not self.valid_token(query.get('token', [''])[0]):
                return self.reply(403, {'error': 'Use the student link from the operator page.'})
            return self.reply(200, STUDENT.replace('__STYLE__', STYLE), 'text/html; charset=utf-8')
        if url.path in ('/api/operator', '/api/export'):
            if not self.is_operator():
                return self.reply(403, {'error': 'Operator access required.'})
            if url.path == '/api/export':
                return self.reply(200, self.session.export(), 'text/csv; charset=utf-8', 'guidance_recap.csv')
            return self.reply(200, self.session.state(operator=True))
        if url.path == '/api/student':
            if not self.valid_token(query.get('token', [''])[0]):
                return self.reply(403, {'error': 'Student access required.'})
            client = query.get('client_id', [''])[0]
            if not client or len(client) > 100:
                return self.reply(400, {'error': 'Invalid client identifier.'})
            with self.session.lock:
                self.session.clients[client] = time.monotonic()
            return self.reply(200, self.session.state())
        return self.reply(404, {'error': 'Not found.'})

    def do_POST(self):
        # Browser requests must originate from this server, not another website.
        origin = self.headers.get('Origin', '')
        if origin != 'http://' + self.headers.get('Host', ''):
            return self.reply(403, {'error': 'Same-origin browser request required.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 24000:
                raise ValueError('Invalid body size.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected an object.')
        except (ValueError, UnicodeError):
            return self.reply(400, {'error': 'Invalid request.'})
        path = urlsplit(self.path).path
        with self.session.lock:
            if path in ('/api/send', '/api/end'):
                if not self.is_operator():
                    return self.reply(403, {'error': 'Operator access required.'})
                if path == '/api/end':
                    self.session.end()
                    return self.reply(200, {'ok': True})
                request = data.get('request_id', '')
                if not isinstance(request, str) or not 1 <= len(request) <= 100:
                    return self.reply(400, {'error': 'Invalid request identifier.'})
                if request in self.session.requests:
                    return self.reply(200, {'message_id': self.session.requests[request]})
                if not self.session.active:
                    return self.reply(409, {'error': 'Session terminée. Relancez le serveur pour une nouvelle session.'})
                text, note = data.get('text', ''), data.get('operator_note', '')
                category = data.get('category', 'unspecified')
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or not isinstance(note, str) or len(note) > 2000:
                    return self.reply(400, {'error': 'Message ou note invalide.'})
                if category not in ('unspecified', 'uncertainty', 'data_quality', 'alternatives', 'next_step', 'other'):
                    return self.reply(400, {'error': 'Catégorie invalide.'})
                message_id = str(uuid.uuid4())
                event = self.session.log('guidance_sent', {'message_id': message_id,
                    'text': text.strip(), 'category': category, 'operator_note': note.strip()})
                self.session.messages.append({'id': message_id, 'text': text.strip(),
                    'category': category, 'operator_note': note.strip(), 'sent_utc': event['utc'],
                    'sent_elapsed_s': event['elapsed_s'], 'deliveries': []})
                self.session.requests[request] = message_id
                return self.reply(200, {'message_id': message_id})
            if path == '/api/displayed':
                if not self.valid_token(data.get('token')):
                    return self.reply(403, {'error': 'Student access required.'})
                client, message_id = data.get('client_id'), data.get('message_id')
                if not isinstance(client, str) or not 1 <= len(client) <= 100:
                    return self.reply(400, {'error': 'Invalid client identifier.'})
                message = next((m for m in self.session.messages if m['id'] == message_id), None)
                if message is None:
                    return self.reply(404, {'error': 'Unknown message.'})
                if not any(d['client_id'] == client for d in message['deliveries']):
                    event = self.session.log('guidance_display_confirmed', {'message_id': message_id, 'client_id': client})
                    message['deliveries'].append({'client_id': client,
                        'displayed_utc': event['utc'], 'displayed_elapsed_s': event['elapsed_s']})
                return self.reply(200, {'ok': True})
            return self.reply(404, {'error': 'Not found.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--student-host', help='Your Mac network address, if automatic detection is incorrect.')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / 'guidance_sessions')
    args = parser.parse_args()
    # Bind before creating the session, so a port conflict doesn't leave a false start log.
    server = ThreadingHTTPServer(('0.0.0.0', args.port), Handler)
    server.daemon_threads = True
    session = Session(args.data_dir, server.server_port, args.student_host)
    server.session = session
    print(f'Operator page: http://127.0.0.1:{server.server_port}/operator', flush=True)
    print('Student link: open the operator page and copy the link shown there.', flush=True)
    print(f'Logs: {session.folder.resolve()}', flush=True)
    print('Control+C stops the messaging server. Whisper runs separately.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.end()
        (session.folder / 'guidance_recap.csv').write_bytes(session.export())
        server.server_close()
        print('\nSession saved.', flush=True)


if __name__ == '__main__':
    main()
