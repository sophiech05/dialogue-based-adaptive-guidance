#!/usr/bin/env python3
"""Manual guidance: local operator and separate student-only tunnel listener."""
import argparse
from pathlib import Path
import threading
from urllib.parse import urlsplit
import messaging_core as core

core.OPERATOR = core.OPERATOR.replace(
    'Ouvrez ce lien sur le deuxième Mac, connecté au même réseau. Remplacez ADRESSE_DU_MAC par l’adresse réseau de votre Mac.',
    'Ouvrez ce lien sur l’iPhone ou le Mac du groupe. Une connexion Internet suffit. Gardez ce lien privé.')


def public_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.port or parsed.path not in ('', '/') or
            parsed.query or parsed.fragment or not parsed.hostname.endswith('.trycloudflare.com')):
        raise argparse.ArgumentTypeError('Use only the https://NAME.trycloudflare.com address printed by cloudflared.')
    return 'https://' + parsed.hostname


class Session(core.Session):
    def __init__(self, root, student_port, origin):
        self.public_origin = origin
        super().__init__(root, student_port, '127.0.0.1')

    def state(self, operator=False):
        state = super().state(operator)
        if operator:
            state['student_url'] = self.public_origin + '/student?token=' + self.token
        return state


class Handler(core.Handler):
    def is_operator(self):
        # Never trust proxy Host/Origin headers to grant operator access.
        return not self.server.student_only and super().is_operator()

    def valid_origin(self):
        origin = self.headers.get('Origin', '')
        if self.server.student_only:
            return origin in (self.session.public_origin,
                             f'http://127.0.0.1:{self.server.server_port}',
                             f'http://localhost:{self.server.server_port}')
        return self.is_operator() and super().valid_origin()

    def do_GET(self):
        if self.server.student_only and urlsplit(self.path).path not in ('/student', '/api/student'):
            return self.reply(403, {'error': 'Student-only endpoint.'})
        return super().do_GET()

    def do_POST(self):
        if self.server.student_only and urlsplit(self.path).path != '/api/displayed':
            return self.reply(403, {'error': 'Student-only endpoint.'})
        return super().do_POST()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-origin', required=True, type=public_origin)
    parser.add_argument('--operator-port', type=int, default=8765)
    parser.add_argument('--student-port', type=int, default=8766)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / 'guidance_sessions')
    args = parser.parse_args()
    servers = []
    try:
        for port, student_only in ((args.operator_port, False), (args.student_port, True)):
            server = core.ThreadingHTTPServer(('127.0.0.1', port), Handler)
            server.daemon_threads = True
            server.student_only = student_only
            servers.append(server)
    except OSError as error:
        for server in servers:
            server.server_close()
        parser.exit(1, f'Cannot open port: {error}. Stop the previous messaging server with Control+C.\n')
    session = Session(args.data_dir, servers[1].server_port, args.public_origin)
    for server in servers:
        server.session = session
    worker = threading.Thread(target=servers[1].serve_forever, daemon=True)
    worker.start()
    print(f'Operator: http://127.0.0.1:{servers[0].server_port}/operator', flush=True)
    print('Copy the student link from the operator page. Tunnel ONLY port ' + str(servers[1].server_port), flush=True)
    print(f'Logs: {session.folder.resolve()}', flush=True)
    print('Keep this terminal and the cloudflared terminal open. Control+C saves and stops.', flush=True)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servers[1].shutdown()
        worker.join()
        session.end()
        session.persist_recap()
        for server in servers:
            server.server_close()
        print('\nSession saved.', flush=True)


if __name__ == '__main__':
    main()
