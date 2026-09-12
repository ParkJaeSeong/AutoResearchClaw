"""Loopback research viewer with explicit same-origin Atlas input routes."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .discovery_view import build_discovery_view
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view, read_artifact

_STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/atlas.js': ('atlas.js', 'text/javascript; charset=utf-8'),
           '/index.html': ('index.html', 'text/html; charset=utf-8'),
           '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
           '/graph.js': ('graph.js', 'text/javascript; charset=utf-8'),
           '/detail.js': ('detail.js', 'text/javascript; charset=utf-8'),
           '/timeline.js': ('timeline.js', 'text/javascript; charset=utf-8'),
           '/trace.js': ('trace.js', 'text/javascript; charset=utf-8'),
           '/discovery.js': ('discovery.js', 'text/javascript; charset=utf-8'),
           '/live.js': ('live.js', 'text/javascript; charset=utf-8'),
           '/styles.css': ('styles.css', 'text/css; charset=utf-8')}

_STATIC_ROOT = Path(__file__).parent / 'research_ui'


def is_allowed_host(host: str) -> bool:
    return host == '127.0.0.1'


def _make_server(root: Path, *, host: str, port: int, discovery_root: Path | None = None) -> ThreadingHTTPServer:
    if not is_allowed_host(host):
        raise ValueError('research_viewer_host_invalid')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('research_viewer_port_invalid')
    root = store._checked_path(root)
    store.read_head(root)
    if discovery_root is not None:
        discovery_root = store._checked_path(discovery_root)
        build_discovery_view(root, discovery_root)

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
            if (target.scheme or target.netloc or target.fragment
                    or '\\' in path or '\x00' in path or '..' in path.split('/')):
                self._send(400, b'Invalid route.'); return
            try:
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {'head'} or any(len(values) != 1 for values in query.values()):
                    self._send(400, b'Invalid query.'); return
                if path == '/api/discovery' and query:
                    self._send(400, b'Invalid query.'); return
                head_id = query.get('head', [None])[0]
                if query and (not path.startswith('/api/') or not store._is_digest(head_id)):
                    self._send(400, b'Invalid query.'); return
            except ValueError:
                self._send(400, b'Invalid query.'); return
            try:
                if path in _STATIC:
                    name, content_type = _STATIC[path]
                    self._send(200, store._checked_path(_STATIC_ROOT / name).read_bytes(), content_type)
                elif path == '/api/discovery':
                    body = json.dumps(build_discovery_view(root, discovery_root), ensure_ascii=False, allow_nan=False).encode()
                    self._send(200, body, 'application/json; charset=utf-8')
                elif path == '/api/view':
                    body = json.dumps(build_view(root, head_id=head_id), ensure_ascii=False, allow_nan=False).encode()
                    self._send(200, body, 'application/json; charset=utf-8')
                elif path.startswith('/api/artifacts/'):
                    artifact_id = path.removeprefix('/api/artifacts/')
                    if not artifact_id or '/' in artifact_id:
                        self._send(404); return
                    try:
                        data = read_artifact(root, artifact_id=artifact_id, head_id=head_id)
                    except ValueError as error:
                        if str(error) != 'research_view_artifact_unavailable':
                            raise
                        self._send(404, b'Artifact is not public at this snapshot.'); return
                    self._send(200, data)
                else:
                    self._send(404, b'Not found.')
            except (ValueError, OSError):
                self._send(409, b'The registered record could not be verified.')

        def _read_only(self):
            self._send(405, b'Read-only viewer.')

        def do_POST(self):
            from .atlas_http import handle_post
            if not handle_post(self, root):
                self._read_only()

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_HEAD = _read_only

    return ThreadingHTTPServer((host, port), Handler)


def serve_view(root: Path, *, host: str = '127.0.0.1', port: int = 0, discovery_root: Path | None = None) -> None:
    server = _make_server(root, host=host, port=port, discovery_root=discovery_root)
    print(f'http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
