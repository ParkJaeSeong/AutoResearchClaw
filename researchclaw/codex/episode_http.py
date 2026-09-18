"""Local UI review submission; not a general command or experiment endpoint."""
import json
from researchclaw.core.research_graph import commands, store

_LIMIT = 65536
_FIELDS = {'id', 'decision', 'feedback', 'expected_head', 'command_id'}


def dispatch_review(root, payload):
    if type(payload) is not dict or set(payload) != _FIELDS:
        raise ValueError('episode_payload_invalid')
    receipt = commands.apply_command(root, operation='episode.review', payload=dict(
        id=payload['id'], decision=payload['decision'], feedback=payload['feedback'], reviewer='local-ui-user'),
        expected_head=payload['expected_head'], command_id=payload['command_id'])
    row = receipt['state']['work_episodes'][payload['id']]
    return dict(head_id=receipt['id'], episode_id=row['id'], review_status=row['review_status'], review=row['review'])


def _invalid_constant(value):
    raise ValueError('episode_json_invalid')


def handle_post(handler, root):
    if handler.path != '/api/episodes/review':
        return False

    def reply(status, body):
        if status >= 400:
            handler.close_connection = True
        handler._send(status, json.dumps(body).encode(), 'application/json; charset=utf-8')

    if not handler._origin_allowed():
        reply(403, {'error':'episode_origin_forbidden'}); return True
    lengths = handler.headers.get_all('Content-Length', [])
    types = handler.headers.get_all('Content-Type', [])
    if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
            or handler.headers.get('Transfer-Encoding') or len(types) != 1
            or types[0].split(';')[0].strip().lower() != 'application/json'):
        reply(400, {'error':'episode_request_invalid'}); return True
    if len(lengths[0]) > 9 or int(lengths[0]) > _LIMIT:
        reply(413, {'error':'episode_request_too_large'}); return True
    try:
        handler.connection.settimeout(10)  # Incomplete HTTP body only, never a research deadline.
        data = handler.rfile.read(int(lengths[0]))
        if len(data) != int(lengths[0]):
            raise ValueError('episode_request_incomplete')
        payload = json.loads(data.decode('utf-8'), parse_constant=_invalid_constant, object_pairs_hook=store._unique_pairs)
        reply(200, dispatch_review(root, payload))
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        reply(400, {'error':'episode_json_invalid'})
    except ValueError as exc:
        code = str(exc)
        conflicts = {'research_graph_head_conflict','research_graph_command_conflict','episode_review_exists',
                     'episode_review_before_conclusion','episode_review_not_required'}
        allowed = conflicts | {'episode_payload_invalid','episode_missing','episode_json_invalid','episode_request_incomplete','research_graph_record_invalid'}
        reply(409 if code in conflicts else 400, {'error':code if code in allowed else 'episode_request_invalid'})
    except OSError:
        # A write may already be durable; client must replay its original key.
        reply(503, {'error':'episode_storage_unavailable'})
    return True
