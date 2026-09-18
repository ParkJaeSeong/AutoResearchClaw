"""Small same-origin JSON adapter for explicit Atlas QA input."""
import base64
import binascii
import json

from researchclaw.core.research_graph import commands, store
from .atlas_intake import mutation_result
from .atlas_service_http import FIELDS as SERVICE_FIELDS, dispatch as service_dispatch

MAX_REQUEST_BYTES = ((10 * 1024 * 1024 + 2) // 3) * 4 + 65536
_FIELDS = {
    'preview': {'content_base64'},
    'import': {'content_base64', 'sha256', 'filename'},
    'review': {'evidence_ref', 'question_ref', 'status', 'allowed_uses', 'held_uses', 'limitations', 'rationale'},
    'decision': {'review_ref', 'title', 'conclusion', 'rationale', 'limitations', 'submission_refs', 'prior_ref'},
    'question': {'decision_ref', 'question', 'missing_evidence', 'decision_impact', 'scope'},
}
_OPERATIONS = {'import': 'external.evidence.import', 'review': 'external.review.record',
               'decision': 'external.decision.record', 'question': 'external.question.record'}


def decode_qa(value):
    if type(value) is not str or len(value) > MAX_REQUEST_BYTES:
        raise ValueError('atlas_bytes_invalid')
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('atlas_bytes_invalid') from None


def dispatch_atlas(root, action, payload):
    """Transport cannot set authorship or submit arbitrary graph operations."""
    if action in SERVICE_FIELDS:
        return service_dispatch(root,action,payload)
    required = _FIELDS[action] | (set() if action == 'preview' else {'expected_head', 'command_id'})
    if type(payload) is not dict or set(payload) != required:
        raise ValueError('atlas_request_invalid')
    if action == 'preview':
        from researchclaw.core.research_graph.atlas_format import parse_atlas_qa
        return parse_atlas_qa(decode_qa(payload['content_base64']))
    receipt = commands.apply_command(root, operation=_OPERATIONS[action],
        payload={**{k: payload[k] for k in _FIELDS[action]}, 'producer_id': 'pilot-coordinator'},
        expected_head=payload['expected_head'], command_id=payload['command_id'])
    return mutation_result(receipt)


def _invalid_constant(value):
    raise ValueError('atlas_json_invalid')


def handle_post(handler, root):
    """Return False for every unrelated route; it remains read-only."""
    action = handler.path.removeprefix('/api/atlas/')
    if handler.path != '/api/atlas/' + action or action not in _FIELDS and action not in SERVICE_FIELDS:
        return False
    if not handler._origin_allowed():
        handler.close_connection = True
        handler._send(403, b'Origin is not allowed.'); return True
    lengths = handler.headers.get_all('Content-Length', [])
    types = handler.headers.get_all('Content-Type', [])
    if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or handler.headers.get('Transfer-Encoding')
            or len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json'):
        handler.close_connection = True
        handler._send(400, b'{"error":"atlas_request_invalid"}', 'application/json'); return True
    if len(lengths[0]) > 9:
        handler.close_connection = True
        handler._send(413, b'{"error":"atlas_file_too_large"}', 'application/json'); return True
    length = int(lengths[0])
    if length > MAX_REQUEST_BYTES:
        handler.close_connection = True
        handler._send(413, b'{"error":"atlas_file_too_large"}', 'application/json'); return True
    try:
        handler.connection.settimeout(10)  # Incomplete HTTP uploads only; never a research execution timeout.
        data = handler.rfile.read(length)
        if len(data) != length:
            raise ValueError('atlas_request_incomplete')
        payload = json.loads(data.decode('utf-8'), object_pairs_hook=store._unique_pairs,
                             parse_constant=_invalid_constant)
        result = dispatch_atlas(root, action, payload)
        handler._send(200, json.dumps(result, ensure_ascii=False, allow_nan=False).encode(),
                      'application/json; charset=utf-8')
    except RecursionError:
        handler.close_connection = True
        handler._send(400, b'{"error":"atlas_json_invalid"}', 'application/json')
    except (ValueError, UnicodeError) as error:
        code = str(error)
        if not code.replace('_', '').isalnum():
            code = 'atlas_request_invalid'
        status = 409 if 'conflict' in code else 400
        handler._send(status, json.dumps({'error': code}).encode(), 'application/json')
    except OSError:
        handler.close_connection = True
        handler._send(409, b'{"error":"atlas_storage_or_transport_error"}', 'application/json')
    return True
