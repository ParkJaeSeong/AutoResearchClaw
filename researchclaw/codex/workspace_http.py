"""Bounded JSON input for explicit project creation."""
import json
from researchclaw.core.research_graph import store


def create_project(handler, catalog):
    if catalog is None:
        handler.close_connection = True
        handler._send(405, b'Workspace is not enabled.'); return
    lengths = handler.headers.get_all('Content-Length', [])
    types = handler.headers.get_all('Content-Type', [])
    if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
            or handler.headers.get('Transfer-Encoding') or len(types) != 1
            or types[0].split(';')[0].strip().lower() != 'application/json'):
        raise ValueError('workspace_request_invalid')
    if len(lengths[0]) > 9 or int(lengths[0]) > 65536:
        handler.close_connection = True
        handler._send(413, b'Request too large.'); return
    handler.connection.settimeout(10)
    body = handler.rfile.read(int(lengths[0]))
    if len(body) != int(lengths[0]): raise ValueError('workspace_request_incomplete')
    def invalid_constant(value): raise ValueError('workspace_json_invalid')
    payload = json.loads(body.decode(), object_pairs_hook=store._unique_pairs, parse_constant=invalid_constant)
    handler._json(200, {'project': catalog.create(payload)})
