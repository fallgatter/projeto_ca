import argparse
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / 'results_fluxo'

REPLAY = re.compile(r'/(manha|tarde)/\d+/(referencia|otimizado|coordenado|revisado)/\d+\.json')
FORECAST = re.compile(r'/(manha|tarde)/\d+/(otimizado|coordenado|revisado)/forecast\.json')
QUEUES = re.compile(r'/(manha|tarde)/\d+/(referencia|otimizado|coordenado|revisado)/queues\.json')


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, output=OUTPUT, **kwargs):
        self.output = output
        super().__init__(*args, **kwargs)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ('/data/map.json', '/data/report.json', '/data/fourier.json'):
            return self.send_data(self.output/route.rsplit('/', 1)[-1])
        if route.startswith('/data/'):
            replay = route.removeprefix('/data')
            if FORECAST.fullmatch(replay) or QUEUES.fullmatch(replay):
                return self.send_data(self.output/replay.lstrip('/'))
            if REPLAY.fullmatch(replay):
                return self.send_data(self.output/(replay.strip('/')+'.gz'), compressed=True)
            self.send_error(404)
            return
        if route not in ('/', '/index.html', '/dashboard.css', '/dashboard.js'):
            self.send_error(404)
            return
        super().do_GET()

    def send_data(self, path, compressed=False):
        try:
            stream = path.open('rb')
        except FileNotFoundError:
            self.send_error(404, 'Dados de replay pendentes')
            return
        with stream:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(stream.seek(0, 2)))
            stream.seek(0)
            self.send_header('Cache-Control', 'no-store')
            if compressed:
                self.send_header('Content-Encoding', 'gzip')
            self.end_headers()
            try:
                self.copyfile(stream, self.wfile)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    def log_message(self, format, *args):
        if not self.path.startswith('/data/'):
            super().log_message(format, *args)


def serve_dashboard(port, output=OUTPUT):
    handler = partial(DashboardHandler, directory=PROJECT/'web', output=output)
    with ThreadingHTTPServer(('127.0.0.1', port), handler) as server:
        print(f'Painel do Quadrilátero disponível em http://127.0.0.1:{port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description='Painel de trânsito do Quadrilátero de Curitiba')
    parser.add_argument('--port', type=int, default=8077)
    parser.add_argument('--data', type=Path, help='Pasta com os dados do replay')
    args = parser.parse_args()
    candidates = (PROJECT/'results_refinado', PROJECT/'results_municipal', PROJECT/'results_calibrado')
    output = args.data or next((p for p in candidates if (p/'report.json').is_file()), OUTPUT)
    serve_dashboard(args.port, output.resolve())


if __name__ == '__main__':
    main()
