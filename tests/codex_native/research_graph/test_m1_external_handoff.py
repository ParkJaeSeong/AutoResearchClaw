"""An external chain cannot reuse a complete native corpus as handoff authority."""
import pytest
from tests.codex_native.research_graph.test_m1_review import f, extracted_baseline, collected_baseline, native_baseline
from tests.codex_native.research_graph.test_m1_external_inputs import artifact
from tests.codex_native.research_graph.test_external_evidence import imported, apply, review_payload
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view
from researchclaw.core.research_graph.m1_nodes import current_node, _context
from researchclaw.core.research_graph.m1_review import _prior_issues
from researchclaw.core.research_graph.gates import _status
from researchclaw.core.research_graph.handoffs import _eligibility

def test_external_chain_handoff(f):
    question,ref=current_node(_context(f.snapshot()),'questions')
    imported(f.root)
    evidence=build_view(f.root)['external_evidence'][0]['ref']
    apply(f.root,'external.review.record',review_payload(evidence))
    review=build_view(f.root)['external_reviews'][0]['ref']
    p=dict(question_ref=ref,question_text=question['content']['questions'][0]['question'],review_refs=[review],claims=[dict(claim_id='c1',statement='Compare',evidence_ref=evidence,review_ref=review,basis_kind='pilot_inference',qa_excerpt='First answer',rationale='Scoped',intended_use='hypothesis review',limitations=['Limited'])],coverage=dict(covered='Methods',missing='Measurements',decision_impact='Design'),limitations=['Declared'],previous_ref=None,revision_reason=None,producer_id='coordinator')
    apply(f.root,'m1.evidence_basis.register',p)
    basis=build_view(f.root)['m1_evidence_bases'][0]
    f.head=store.read_head(f.root)
    refs={}
    for node in ('synthesize','hypothesize','review'):
        a=artifact(f,p,basis,node,refs)
        if node=='review':
            inputs=_context(f.snapshot())
            for row in _prior_issues(inputs):
                issue=inputs.state['issues'][row['issue_id']]
                status,event=_status(inputs,issue)
                assert status=='resolved'
                a['content']['prior_issue_dispositions'].append(dict(issue_id=issue['id'],disposition='native_resolved',owner_assignment_id=row['owner_assignment_id'],hypothesis_ids=['h1'],rationale='Native result',verification_refs=event['verification_refs']))
        f.register(a);f.council_prepare();f.complete();refs[node]=f.node_ref()
    before=store.read_head(f.root)['id']
    with pytest.raises(ValueError,match='external_handoff_not_supported'):
        _eligibility(f.snapshot())
    with pytest.raises(ValueError,match='external_handoff_not_supported'):
        f.apply('m1.handoff.issue',dict(publication=f.envelope(),review_ref=refs['review']))
    assert store.read_head(f.root)['id']==before
