import argparse
import json
import mimetypes
import sys
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# On évite les fichiers de cache dans le dossier à remettre
sys.dont_write_bytecode = True
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 ou plus récent est nécessaire pour lancer cette application")

from analyses import execute


ROOT = Path(__file__).resolve().parents[1]
JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)


def update_job(identifier: str, **values: object) -> None:
    """On met à jour l’état du calcul sous verrou pour protéger les données partagées"""
    with LOCK:
        JOBS[identifier].update(values)


def run_job(identifier: str, payload: dict) -> None:
    """On exécute une demande et on publie son résultat ou son erreur dans le suivi"""
    update_job(identifier, state='running', progress='Préparation des paramètres')
    start = time.perf_counter()
    try:
        # On transmet les messages d’avancement au suivi du calcul
        result = execute(payload, lambda message: update_job(identifier, progress=message))
        update_job(identifier, state='done', result=result, elapsed=time.perf_counter() - start)
    except Exception as error:
        update_job(identifier, state='error', error=str(error), elapsed=time.perf_counter() - start)


def enqueue(payload: dict) -> str:
    """On ajoute une demande à la file limitée et on renvoie son identifiant"""
    if not isinstance(payload, dict) or not isinstance(payload.get('request'), dict):
        raise ValueError('Les paramètres du calcul sont absents')
    payload = public_parameters(payload)
    with LOCK:
        if sum(job['state'] in ('queued', 'running') for job in JOBS.values()) >= 3:
            raise ValueError('Trois calculs sont déjà en cours ou en attente')
        finished = [key for key, job in JOBS.items() if job['state'] in ('done', 'error')]
        for key in finished[:-20]:
            del JOBS[key]
        identifier = uuid.uuid4().hex
        JOBS[identifier] = {'id': identifier, 'state': 'queued', 'progress': 'En attente'}
    POOL.submit(run_job, identifier, payload)
    return identifier


def public_parameters(value: object) -> object:
    """On retire les champs internes d’une demande avant de valider ses paramètres"""
    if isinstance(value, dict):
        return {key: public_parameters(item) for key, item in value.items() if not key.startswith('_')}
    if isinstance(value, list):
        return [public_parameters(item) for item in value]
    return value


def engine_status() -> dict:
    """On annonce uniquement les moteurs effectivement disponibles"""
    try:
        from excel_bridge import status
        vba = status()
    except ImportError:
        vba = {'available': False, 'reason': 'Le pont Excel n’est pas encore installé'}
    return {'python': {'available': True}, 'vba': vba}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        """On désactive le journal des requêtes pour garder le terminal lisible"""
        return

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        """On renvoie les octets de la réponse avec son type et ses en-têtes HTTP"""
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; object-src 'none'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value: object, status: int = 200) -> None:
        """On encode le résultat en JSON en refusant les nombres non finis"""
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_bytes(data, 'application/json; charset=utf-8', status)

    def do_GET(self) -> None:
        """On sert l’interface, l’état des moteurs ou le suivi d’un calcul"""
        path = urlsplit(self.path).path
        if path == '/api/status':
            self.send_json(engine_status())
        elif path.startswith('/api/jobs/'):
            with LOCK:
                job = dict(JOBS.get(path.rsplit('/', 1)[-1], {}))
            self.send_json(job or {'error': 'Calcul introuvable'}, 200 if job else 404)
        else:
            self.serve_static(path)

    def serve_static(self, path: str) -> None:
        """On sert uniquement les fichiers de l’interface et l’icône vide autorisés"""
        name = 'index.html' if path == '/' else path.lstrip('/')
        if name == 'favicon.svg':
            self.send_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml')
            return
        allowed = {'index.html', 'app.css', 'app.js', 'charts.js'}
        file = ROOT / 'interface' / name
        if name not in allowed or not file.is_file():
            self.send_json({'error': 'Page introuvable'}, 404)
            return
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        self.send_bytes(file.read_bytes(), content_type + '; charset=utf-8')

    def check_request(self) -> None:
        """On vérifie que la requête JSON provient de l’application locale"""
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in allowed:
            raise ValueError('Le serveur accepte uniquement les requêtes locales')
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + host for host in allowed}:
            raise ValueError('Origine de la requête refusée')
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('Une requête JSON est nécessaire')

    def do_POST(self) -> None:
        """On vérifie le corps reçu avant d’ajouter un calcul à la file"""
        try:
            self.check_request()
            if self.path != '/api/jobs':
                self.send_json({'error': 'Action introuvable'}, 404)
                return
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 1000000:
                raise ValueError('Taille de requête invalide')
            payload = json.loads(self.rfile.read(length))
            self.send_json({'id': enqueue(payload)}, 202)
        except (ValueError, TypeError, KeyError) as error:
            self.send_json({'error': str(error)}, 400)


def serve(port: int = 8765, open_browser: bool = False) -> None:
    """On lance le serveur local et on ouvre le navigateur si demandé"""
    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    except OSError:
        if port == 0:
            raise
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('Pricer : ' + url, flush=True)
    if open_browser:
        # On ouvre le navigateur après le démarrage du serveur
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        POOL.shutdown(wait=True, cancel_futures=True)


def main() -> None:
    """On lit les options de lancement puis on démarre le serveur"""
    parser = argparse.ArgumentParser(description='Lancer le pricer local')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    options = parser.parse_args()
    serve(options.port, not options.no_browser)


if __name__ == '__main__':
    main()
