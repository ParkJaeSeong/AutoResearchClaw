"""Loopback-only, read-only delivery of a single registered M1 project."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from researchclaw.core.m1 import store

_STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/index.html': ('index.html', 'text/html; charset=utf-8'),
           '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
           '/graph.js': ('graph.js', 'text/javascript; charset=utf-8'),
           '/detail.js': ('detail.js', 'text/javascript; charset=utf-8'),
           '/live.js': ('live.js', 'text/javascript; charset=utf-8'),
           '/styles.css': ('styles.css', 'text/css; charset=utf-8')}


def is_allowed_host(host: str) -> bool:
    return host == '127.0.0.1'


def _read_view(root: Path) -> dict:
    from researchclaw.core.m1.views import build_view
    return build_view(root)


def _artifact_bytes(root: Path, view: dict, artifact_id: str) -> bytes | None:
    visible = next((ref for ref in view['artifacts'] if ref.get('id') == artifact_id), None)
    if visible is None:
        return None
    head = store.read_head(root)
    registered = next((ref for ref in head['state'].get('artifacts', [])
                       if ref.get('id') == artifact_id), None)
    if registered is None or any(visible.get(key) != registered.get(key)
                                 for key in ('sha256', 'size', 'logical_path')):
        return None
    digest = registered['sha256']
    if head['objects'].get(digest) != {'sha256': digest, 'size': registered['size']}:
        raise ValueError('m1_viewer_artifact_invalid')
    data = store._read_file(store._store_path(root) / 'objects' / digest)
    if len(data) != registered['size'] or store._hash(data) != digest:
        raise ValueError('m1_viewer_artifact_invalid')
    return data


def _make_server(root: Path, *, host: str, port: int) -> ThreadingHTTPServer:
    if not is_allowed_host(host):
        raise ValueError('m1_viewer_host_invalid')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('m1_viewer_port_invalid')
    root = store._checked_path(root)
    store.read_head(root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body=b'', content_type='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            if status == 405:
                self.send_header('Allow', 'GET')
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _origin_allowed(self):
            authority = f'127.0.0.1:{self.server.server_port}'
            hosts = self.headers.get_all('Host', [])
            origins = self.headers.get_all('Origin', [])
            return (hosts == [authority] and (not origins or origins == [f'http://{authority}'])
                    and self.headers.get('Sec-Fetch-Site', 'none') in ('none', 'same-origin'))

        def do_GET(self):
            if not self._origin_allowed():
                self._send(403, b'Origin is not allowed.'); return
            target = urlsplit(self.path)
            path = unquote(target.path)
            if (target.scheme or target.netloc or target.query or target.fragment
                    or '\\' in path or '\x00' in path or '..' in path.split('/')):
                self._send(400, b'Invalid route.'); return
            try:
                if path in _STATIC:
                    name, content_type = _STATIC[path]
                    self._send(200, (Path(__file__).parent / 'm1_ui' / name).read_bytes(), content_type)
                elif path == '/api/view':
                    body = json.dumps(_read_view(root), ensure_ascii=False, allow_nan=False).encode()
                    self._send(200, body, 'application/json; charset=utf-8')
                elif path.startswith('/api/artifacts/'):
                    artifact_id = path.removeprefix('/api/artifacts/')
                    if not artifact_id or '/' in artifact_id:
                        self._send(404); return
                    data = _artifact_bytes(root, _read_view(root), artifact_id)
                    self._send(404 if data is None else 200, data or b'')
                else:
                    self._send(404, b'Not found.')
            except (ValueError, OSError):
                self._send(409, b'The registered record could not be verified.')

        def _read_only(self):
            self._send(405, b'Read-only viewer.')

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_HEAD = _read_only

    return ThreadingHTTPServer((host, port), Handler)


def serve_view(root: Path, *, host: str = '127.0.0.1', port: int = 0) -> None:
    server = _make_server(root, host=host, port=port)
    print(f'http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
