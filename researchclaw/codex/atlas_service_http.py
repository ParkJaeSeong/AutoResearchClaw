"""Same-origin UI actions; the connection file is operator configuration only."""
import os
from .atlas_client import AtlasClient, AtlasError
from .atlas_session import AtlasSession

FIELDS={'service-connect':set(),'service-status':set(),'service-bind':{'project','reason'},
        'service-ask':{'key','question','question_id','previous'},'service-poll':{'key'},'service-supporting':{'key'},
        'service-receive':{'key','expected_head'}}


def configured_session(root):
    path=os.environ.get('PILOT_ATLAS_CONNECTION_FILE')
    if not path:raise AtlasError('atlas_not_configured')
    return AtlasSession(root,AtlasClient(path))


def dispatch(root,action,payload):
    if type(payload) is not dict or set(payload)!=FIELDS[action]:raise ValueError('atlas_request_invalid')
    if action=='service-status' and not os.environ.get('PILOT_ATLAS_CONNECTION_FILE'):
        from .knowledge_view import knowledge_status
        return dict(binding=None,requests=[],knowledge_jobs=knowledge_status(root.resolve()))
    session=configured_session(root)
    if action=='service-connect':return session.connect()
    if action=='service-status':
        from .knowledge_view import knowledge_status
        return dict(session.status(),knowledge_jobs=knowledge_status(root.resolve()))
    if action=='service-bind':return session.bind(**payload)
    if action=='service-ask':return session.ask(**payload)
    if action=='service-poll':return session.poll(**payload)
    if action=='service-supporting':return session.refresh_supporting(**payload)
    if action=='service-receive':return session.receive(**payload)
