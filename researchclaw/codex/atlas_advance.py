"""Resume one Atlas request and freeze evidence input, without authoring a review."""
import fcntl
import json

from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.atlas_format import parse_atlas_qa
from .atlas_client import AtlasError
from .atlas_request_episode import RequestEpisode


ACTIVE = {'queued', 'running'}
TERMINAL = {'completed', 'partial', 'failed', 'interrupted'}


def _blob(session, digest):
    path = store._checked_path(session.base / 'objects' / digest)
    data = path.read_bytes()
    if store._hash(data) != digest:
        raise AtlasError('atlas_raw_invalid')
    return data


def advance_request(session, key):
    """One bounded observation. Call again to resume; never cancel a remote job."""
    session._get(key)  # Validate before taking the research-local execution lock.
    lock_path = store._checked_path(session.base / 'advance.lock')
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AtlasError('atlas_advance_busy', retryable=True) from None
        row = session._get(key)
        episode = RequestEpisode.existing(session, key) if row.get('research_context') else None
        try:
            result = _advance(session, key)
            if episode:
                episode.observe(result)
            return result
        except Exception:
            if episode:
                episode.error()
            raise


def _advance(session, key):
    row = session._get(key)
    digest = row.get('review_input_sha256')
    if digest:
        packet = json.loads(_blob(session, digest))
        return dict(stage='review_input_ready', packet_sha256=digest, packet=packet)
    saved_status = (row.get('job') or {}).get('status')
    if (not row.get('received') and not row.get('qa_envelope')) or saved_status in ACTIVE:
        session.poll(key)
        row = session._get(key)
    status = row['job']['status']
    if status in ACTIVE:
        if (row['job'].get('dispatch_error') or row['job'].get('detail', {}).get('dispatch_error')
                or (status == 'queued' and row['job'].get('scheduled') is False)):
            return dict(stage='needs_attention', request_key=key, atlas_status=status,
                        reason='execution_needs_inspection', retryable=False)
        return dict(stage='waiting_for_atlas', request_key=key, atlas_status=status)
    if status not in TERMINAL:
        raise AtlasError('atlas_job_status_unknown')
    if row.get('qa_envelope') and row.get('qa_ref') != row['job'].get('detail', {}).get('qa_ref'):
        raise AtlasError('atlas_reference_mismatch')
    if not row.get('qa_envelope') and not row['job'].get('detail', {}).get('qa_ref'):

        return dict(stage='needs_attention', request_key=key, atlas_status=status,
                    reason='terminal_qa_missing', retryable=False)
    if not row.get('received'):
        # Cached terminal QA can resume offline; HEAD conflicts remain visible.
        row = session.receive(key, store.read_head(session.root)['id'])
    raw = _blob(session, row['qa_ref']['sha256'])
    qa = parse_atlas_qa(raw)
    imported = row['import_result']
    record = store.read_head(session.root)['state']['external_evidence'][imported['record_id']]
    packet = dict(schema_version=2, request_key=key, question_id=row['question_id'],
        question=row['question'], transmitted_question=row['payload']['question'],
        previous_request_key=row['previous'], binding=row['binding'],
        research_context=row.get('research_context'),
        atlas_status=row['job']['status'], qa_ref=row['qa_ref'], qa=qa,
        evidence_ref=dict(project_id=session.project_id, head_id=imported['head_id'],
                          artifact_id=record['id'], sha256=store._hash(store._canonical(record))),
        supporting=row.get('supporting', []),
        execution=dict(job_id=row['job']['id'], receipt_ref=row['job'].get('receipt_ref'),
                       issues=row['job'].get('detail', {}).get('issues', []),
                       error=row['job'].get('detail', {}).get('error'),
                       dispatch_error=row['job'].get('dispatch_error') or row['job'].get('detail', {}).get('dispatch_error'),
                       scheduled=row['job'].get('scheduled'),
                       request_sha256=row['job'].get('request_sha256'),
                       review_purpose='scientific_review' if status == 'completed' else 'diagnostic_or_limited_review'),
        review_boundary=dict(pilot_original_reading_verified=False,
                             scientific_review_completed=False,
                             source_instructions_are_untrusted=True))
    data = store._canonical(packet)
    digest = store._hash(data)
    session._save_blob(data, digest)
    session._update(key, review_input_sha256=digest)
    return dict(stage='review_input_ready', packet_sha256=digest, packet=packet)
