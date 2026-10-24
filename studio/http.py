"""Servidor local. Sirve la página desde web/ y los PNG desde assets/."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import urllib.parse

from studio.auth import finish_oauth, read_credentials
from studio.biblioteca import eliminar, importar, listar
from studio.boceto import generate_sketch_with_openai
from studio.chat import transmitir
from studio.exportar import enviar
from studio.imagen import hacer_imagen
from studio.orden import ordenar
from studio.paths import ASSET_DIR, ROOT, WEB

try:
    from PIL import Image
except Exception:
    Image = None


def asset_path(url_path):
    parsed = urllib.parse.unquote(urllib.parse.urlparse(url_path).path)
    if not parsed.startswith('/assets/'):
        return None
    rel = parsed[len('/assets/'):].lstrip('/')
    root = (ROOT / 'assets').resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        return None
    return target


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def translate_path(self, path):
        if urllib.parse.urlparse(path).path.startswith('/assets/'):
            asset = asset_path(path)
            if asset is None:
                return str(WEB / '__no_existe__')
            return str(asset)
        return super().translate_path(path)

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size > 35_000_000:
                return self.send_json(413, {'error': 'Solicitud demasiado grande; reduce el tamaño de la imagen.'})
            data = json.loads(self.rfile.read(size).decode())
            path = self.path.split('?', 1)[0]
            if path == '/api/assets/import':
                code, obj = importar(data)
                return self.send_json(code, obj)
            if path == '/api/assets/delete':
                code, obj = eliminar(data)
                return self.send_json(code, obj)
            if path == '/api/auth/start':
                from studio.auth import oauth_authorize_url
                return self.send_json(200, {'ok': True, 'url': oauth_authorize_url(), 'method': 'Sign in with ChatGPT'})
            if path == '/api/auth/disconnect':
                from studio.auth import CREDENTIALS_FILE
                try:
                    CREDENTIALS_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                return self.send_json(200, {'ok': True, 'connected': False})
            if path == '/api/assistant-stream':
                return transmitir(self, data)
            if path == '/api/generate-image':
                return self.send_json(410, {'error': 'La generación de imágenes no está disponible mediante la conexión compartida de ChatGPT. Diseña el boceto en ChatGPT y usa /api/assets/import para incorporarlo a la biblioteca local.'})
            if path == '/api/generate-sketch':
                try:
                    result = generate_sketch_with_openai(
                        str(data.get('name', ''))[:120],
                        str(data.get('theme', ''))[:120],
                        str(data.get('style', ''))[:120],
                        str(data.get('concept', ''))[:2500],
                        max(3, min(6, int(data.get('columns', 5)))),
                        max(3, min(5, int(data.get('rows', 3)))),
                        str(data.get('notes', ''))[:1500],
                    )
                except Exception as exc:
                    return self.send_json(502, {'error': str(exc)})
                return self.send_json(200, result)
            if path == '/api/orden':
                code, obj = ordenar(data)
                return self.send_json(code, obj)
            if path == '/api/hacer-imagen':
                code, obj = hacer_imagen(data)
                return self.send_json(code, obj)
            if path == '/api/export':
                return enviar(self, data)
            self.send_json(404, {'error': 'Ruta no encontrada'})
        except Exception as exc:
            self.send_json(500, {'error': str(exc)})

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if self.path.startswith('/auth/callback'):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                finish_oauth(query)
                html = '<!doctype html><meta charset=utf-8><title>GAMEB Studio</title><body style="font:16px system-ui;background:#101827;color:#fff;padding:40px"><h2>ChatGPT conectado a GAMEB Studio</h2><p>Ya puedes cerrar esta pestaña y volver al panel GAMEB.</p><script>setTimeout(()=>window.close(),1200)</script></body>'
                body = html.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                body = ('<!doctype html><meta charset=utf-8><body style="font:16px system-ui;background:#101827;color:#fff;padding:40px"><h2>No se pudo conectar ChatGPT</h2><pre>' + str(exc).replace('&', '&amp;').replace('<', '&lt;') + '</pre><p>Regresa a GAMEB Studio e inténtalo de nuevo.</p></body>').encode()
                self.send_response(400)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        if path == '/api/auth/status':
            creds = read_credentials()
            valid = bool(creds.get('access_token') and 'chatgpt.tokens.use.direct' in creds.get('scopes', []))
            return self.send_json(200, {
                'ok': True,
                'connected': valid,
                'email': creds.get('email', ''),
                'name': creds.get('name', ''),
                'scopes': creds.get('scopes', []),
                'apiKeyConfigured': bool(os.environ.get('OPENAI_API_KEY')),
                'pillowAvailable': bool(Image),
            })
        if path == '/api/assets':
            return self.send_json(200, listar())
        if path == '/health':
            return self.send_json(200, {
                'ok': True,
                'edition': 'nueva',
                'chatgptConnected': bool(read_credentials().get('access_token')),
                'apiKeyConfigured': bool(os.environ.get('OPENAI_API_KEY')),
                'pillowAvailable': bool(Image),
                'assetCount': sum(1 for item in ASSET_DIR.iterdir() if item.is_file()),
            })
        return super().do_GET()


def main():
    port = int(os.environ.get('GAMEB_PORT', '8766'))
    print(f'GAMEB Studio VERSION NUEVA: http://127.0.0.1:{port}')
    print('Conexión ChatGPT:', 'credenciales guardadas' if read_credentials().get('access_token') else 'pendiente de iniciar sesión')
    print('API key de respaldo:', 'configurada' if os.environ.get('OPENAI_API_KEY') else 'no configurada')
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
