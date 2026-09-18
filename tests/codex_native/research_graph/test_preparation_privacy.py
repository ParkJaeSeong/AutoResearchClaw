"""Encoded captured documents must obey the same phase disclosure boundary."""
import base64
import json
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_preparation import preparation
from tests.codex_native.research_graph.test_m1_external_inputs import external
from tests.codex_native.research_graph.test_m1_evidence_basis import ready
from tests.codex_native.research_graph.test_m1_preparation_verification import ref, verify
from tests.codex_native.research_graph.test_external_evidence import apply


def test_private_bytes_cannot_be_laundered_through_encoded_preparation_source(preparation):
    f, p = preparation
    f.head = store.read_head(f.root)
    f.council_prepare()
    private = f.submit(0, 'initial', rationale='Undisclosed reviewer opinion')
    for item in p['items'].values(): item['owner_id'] = f.author['id']
    raw = ('Synthetic preparation source: explicit fixture conditions and exemption scope. Wrapper ' + private['id']).encode()
    encoded = base64.b64encode(raw).decode()
    captured = apply(f.root, 'm1.preparation.evidence.capture', dict(review_ref=p['review_ref'],
        decision_refs=p['decision_refs'], category='measurement', owner_id=f.author['id'],
        disposition='verified', source_kind='document', source_locator='fixture://wrapped-review',
        source_version='1', content_base64=encoded, sha256=store._hash(raw), producer_id=f.author['actor_id']))
    checked = verify(f, ref(captured, 'm1_preparation_evidence'))
    p['items']['measurement'].update(status='verified', verification_refs=[ref(checked, 'm1_preparation_verifications')])
    apply(f.root, 'm1.preparation.register', p)
    view = build_view(f.root)
    assert encoded not in json.dumps(view)
    assert view['m1_preparation_evidence'] == []
    assert view['m1_preparation_verifications'] == []
    assert view['m1_preparations'] == []
    assert not any(row['ref']['sha256'] == store._hash(raw) for row in view['artifacts'])
