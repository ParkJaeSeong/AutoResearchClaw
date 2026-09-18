"""Loopback research viewer with explicit same-origin Atlas input routes."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .discovery_view import build_discovery_view
from .project_workspace import Workspace, public_files, public_file
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view, read_artifact

_STATIC = {'/legacy_records.js': ('legacy_records.js', 'text/javascript; charset=utf-8'),'/knowledge_status.js': ('knowledge_status.js', 'text/javascript; charset=utf-8'),'/atlas_service.js': ('atlas_service.js', 'text/javascript; charset=utf-8'),'/': ('index.html', 'text/html; charset=utf-8'),
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

# Explicit static allowlist, including licensed local fonts. No directory exposure.
for _name in ('execution.js', 'shell.js', 'overview.js', 'theme.js', 'episodes.js', 'episode_review.js', 'project.js', 'workspace.js', 'document_handoff.js'):
    _STATIC['/' + _name] = (_name, 'text/javascript; charset=utf-8')
for _name, _type in (('pilot.svg', 'image/svg+xml'), ('krict-logo.png', 'image/png'),
                     ('LICENSE.txt', 'text/plain; charset=utf-8'),
                     ('Pretendard-Regular.woff2', 'font/woff2'),
                     ('Pretendard-SemiBold.woff2', 'font/woff2'),
                     ('Pretendard-Bold.woff2', 'font/woff2')):
    _STATIC['/assets/' + _name] = ('assets/' + _name, _type)

_STATIC_ROOT = Path(__file__).parent / 'research_ui'


def is_allowed_host(host: str) -> bool:
    return host == '127.0.0.1'


def _make_server(root: Path, *, host: str, port: int, discovery_root: Path | None = None, workspace: Path | None = None) -> ThreadingHTTPServer:
    if not is_allowed_host(host):
        raise ValueError('research_viewer_host_invalid')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('research_viewer_port_invalid')
    root = store._checked_path(root)
    initial = store.read_head(root)
    default_id = initial["state"]["project_id"]
    catalog = Workspace(workspace) if workspace is not None else None
    if catalog is not None:
        existing = next((p for p in catalog.read()["projects"] if p["id"] == default_id), None)
        if existing is None:
            catalog.register(root, name=initial["state"]["topic"])
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
                if set(query) - {'head', 'project'} or any(len(values) != 1 for values in query.values()):
                    self._send(400, b'Invalid query.'); return
                if path in ('/api/discovery', '/api/projects', '/api/project-files', '/api/document-handoffs') and 'head' in query:
                    self._send(400, b'Invalid query.'); return
                head_id = query.get('head', [None])[0]
                if ('head' in query and ((not path.startswith('/api/') and path not in ('/', '/index.html')) or not store._is_digest(head_id))) or (query and path not in ('/', '/index.html') and not path.startswith('/api/')):
                    self._send(400, b'Invalid query.'); return
            except ValueError:
                self._send(400, b'Invalid query.'); return
            try:
                selected_id = query.get('project', [None])[0]
                selected_root = self._project_root(selected_id)
                if path in _STATIC:
                    name, content_type = _STATIC[path]
                    self._send(200, store._checked_path(_STATIC_ROOT / name).read_bytes(), content_type)
                elif path == '/api/projects':
                    self._json(200, dict(projects=catalog.read()['projects'] if catalog else [dict(id=default_id, name=initial['state']['topic'], topic=initial['state']['topic'], storage_path=str(root), layout='linked')], default_project_id=default_id, management_enabled=catalog is not None))
                elif path == '/api/project-files':
                    self._json(200, public_files(selected_root, selected_id or default_id))
                elif path.startswith('/api/project-files/'):
                    try:
                        file = public_file(selected_root, path.removeprefix('/api/project-files/'))
                        self._send(200, file.read_bytes(), 'application/octet-stream')
                    except (ValueError, OSError):
                        self._send(404, b'File is not public.')
                elif path == '/api/document-handoffs':
                    from .document_handoff_view import build_handoff_view
                    self._json(200, build_handoff_view(selected_root, selected_id or default_id))
                elif path == '/api/discovery':
                    body = json.dumps(build_discovery_view(selected_root, discovery_root if selected_root == root else None), ensure_ascii=False, allow_nan=False).encode()
                    self._send(200, body, 'application/json; charset=utf-8')
                elif path == '/api/view':
                    body = json.dumps(self._bound_view(selected_root, head_id, selected_id), ensure_ascii=False, allow_nan=False).encode()
                    self._send(200, body, 'application/json; charset=utf-8')
                elif path.startswith('/api/artifacts/'):
                    artifact_id = path.removeprefix('/api/artifacts/')
                    if not artifact_id or '/' in artifact_id:
                        self._send(404); return
                    try:
                        data = read_artifact(selected_root, artifact_id=artifact_id, head_id=head_id)
                    except ValueError as error:
                        if str(error) != 'research_view_artifact_unavailable':
                            raise
                        self._send(404, b'Artifact is not public at this snapshot.'); return
                    self._send(200, data)
                else:
                    self._send(404, b'Not found.')
            except (ValueError, OSError) as error:
                if str(error) == 'workspace_project_unknown':
                    self._send(404, b'Unknown project.'); return
                self._send(409, b'The registered record could not be verified.')

        def _read_only(self):
            self._send(405, b'Read-only viewer.')

        def _project_root(self, project_id):
            if project_id is None:
                return root
            if catalog is None:
                if project_id == default_id: return root
                raise ValueError('workspace_project_unknown')
            return catalog.resolve(project_id)

        def _json(self, status, data):
            self._send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')

        def _bound_view(self, selected_root, head_id, project_id):
            view = build_view(selected_root, head_id=head_id)
            if project_id:
                for artifact in view.get('artifacts', []):
                    url = artifact.get('raw_url')
                    if isinstance(url, str) and url.startswith('/api/artifacts/'):
                        artifact['raw_url'] = url + ('&' if '?' in url else '?') + 'project=' + project_id
            return view

        def do_POST(self):
            from .atlas_http import handle_post
            from .episode_http import handle_post as handle_episode_post
            from .workspace_http import create_project
            if not self._origin_allowed():
                self.close_connection = True
                self._send(403, b'Origin is not allowed.'); return
            target = urlsplit(self.path)
            try:
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True)
                if (target.scheme or target.netloc or target.fragment or set(query) - {'project'}
                        or any(len(v) != 1 for v in query.values())):
                    raise ValueError('workspace_query_invalid')
                selected_root = self._project_root(query.get('project', [None])[0])
                if target.path == '/api/projects':
                    create_project(self, catalog)
                    return
                original_path = self.path
                self.path = target.path
                try:
                    if not handle_episode_post(self, selected_root) and not handle_post(self, selected_root):
                        self._read_only()
                finally:
                    self.path = original_path
            except (ValueError, UnicodeError, RecursionError) as error:
                self.close_connection = True
                code = str(error)
                status = 404 if code == 'workspace_project_unknown' else 409 if 'conflict' in code else 400
                self._json(status, {'error': code if code.startswith('workspace_') else 'workspace_request_invalid'})
            except OSError:
                self.close_connection = True
                self._json(503, {'error': 'workspace_storage_unavailable'})

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_HEAD = _read_only

    return ThreadingHTTPServer((host, port), Handler)


def serve_view(root: Path, *, host: str = '127.0.0.1', port: int = 0, discovery_root: Path | None = None, workspace: Path | None = None) -> None:
    server = _make_server(root, host=host, port=port, discovery_root=discovery_root, workspace=workspace)
    print(f'http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
