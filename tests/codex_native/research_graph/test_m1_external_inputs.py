"""B2 public command flow; all scientific opinions here are synthetic tests."""
from copy import deepcopy
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import store,commands
from researchclaw.core.research_graph.m1_nodes import review_node
from researchclaw.core.research_graph.m1_review import prepare_hypothesis_review
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_m1_evidence_basis import ready
from tests.codex_native.research_graph.test_external_evidence import apply,imported,qa

@pytest.fixture
def external(ready):
    f,p=ready;f.head=store.read_head(f.root)
    f.check=lambda node=None: review_node(f.snapshot(),node or f.artifact['node'])
    f.council_prepare();f.complete()
    apply(f.root,'m1.evidence_basis.register',p)
    basis=build_view(f.root)['m1_evidence_bases'][0]
    f.head=store.read_head(f.root)
    return f,p,basis

def artifact(f,p,basis,node='synthesize',parents=None):
    evidence=[basis['claims'][0]['ref']]
    if node=='synthesize':
        content=dict(findings=[dict(finding_id='f1',claim='A limited finding',evidence_refs=evidence,
            counterevidence_refs=[],limitations=['Atlas interpretation'])],rejected_alternatives=[],limitations=['Design only'])
    elif node=='hypothesize':
        content=dict(hypotheses=[dict(hypothesis_id='h1',statement='Test the difference',population='Same material',
            prediction='A difference may occur',falsification_condition='Difference within prior small-effect range',
            evidence_refs=evidence,alternative_ids=[],limitations=['Unconfirmed'])],limitations=['Design only'])
    else:
        content=dict(prior_issue_dispositions=[],open_questions=[],limitations=['Execution not authorized'])
    return {**f.envelope(), 'node':node,'attempt':str(uuid4()),'previous_ref':None,'revision_reason':None,
        'input_refs':dict(questions=p['question_ref'],evidence_basis=basis['ref'],**(parents or {})), 'content':content}

def test_external_synthesis_registers_without_fabricating_collection(external):
    f,p,basis=external;f.register(artifact(f,p,basis))
    assert set(f.head['state']['m1_node_heads'])=={'scope','questions','synthesize'}
    result=review_node(f.snapshot(),'synthesize')
    assert not result['ready'] and result['reason_codes']==['council_required']
    assessment=prepare_hypothesis_review(f.snapshot())
    assert 'collect_required' not in assessment['reason_codes']
    assert 'hypothesize_required' in assessment['reason_codes']
    assert build_view(f.root)['approvals']==[]

def test_three_external_nodes_keep_council_requirement(external):
    f,p,basis=external;refs={}
    for node in ('synthesize','hypothesize','review'):
        f.register(artifact(f,p,basis,node,refs))
        assert not review_node(f.snapshot(),node)['ready']
        f.council_prepare();f.complete()
        assert review_node(f.snapshot(),node)['ready']
        refs[node]=f.node_ref()
    assert prepare_hypothesis_review(f.snapshot())['ready']
    assert not f.head['state'].get('handoffs')

@pytest.mark.parametrize('change',['raw_qa','wrong_hash','mixed_parents','missing_basis','foreign_basis'])
def test_invalid_external_input_is_atomic(external,change):
    f,p,basis=external;a=artifact(f,p,basis)
    if change=='raw_qa':a['content']['findings'][0]['evidence_refs']=[p['claims'][0]['evidence_ref']]
    elif change=='wrong_hash':a['input_refs']['evidence_basis']['sha256']='0'*64
    elif change=='mixed_parents':a['input_refs']['screen']=p['question_ref']
    elif change=='missing_basis':del a['input_refs']['evidence_basis']
    else:a['input_refs']['evidence_basis']['project_id']=str(uuid4())
    before=store.read_head(f.root)['id']
    with pytest.raises(ValueError):f.register(a)
    assert store.read_head(f.root)['id']==before

def test_updated_qa_blocks_current_review_and_keeps_history(external):
    f,p,basis=external;f.register(artifact(f,p,basis));f.council_prepare();f.complete()
    before=f.head['id'];assert review_node(f.snapshot(),'synthesize')['ready']
    imported(f.root,qa('New answer'))
    with pytest.raises(ValueError,match='evidence_basis_qa_updated'):review_node(commands.read_policy_snapshot(f.root),'synthesize')
    old=build_view(f.root,head_id=before)
    assert next(n for n in old['nodes'] if n['id']=='synthesize')['status']=='ready'

def test_superseded_basis_and_mixed_chain_are_rejected(external):
    f,p,basis=external;f.register(artifact(f,p,basis));synth=f.node_ref()
    revision=deepcopy(p);revision.update(previous_ref=basis['ref'],revision_reason='Clarify')
    revision['claims'][0]['statement']='Updated statement'
    apply(f.root,'m1.evidence_basis.register',revision)
    new=next(r for r in build_view(f.root)['m1_evidence_bases'] if not r['superseded'])
    f.head=store.read_head(f.root)
    with pytest.raises(ValueError,match='evidence_basis_superseded'):review_node(f.snapshot(),'synthesize')
    with pytest.raises(ValueError,match='external_parent'):f.register(artifact(f,p,new,'hypothesize',{'synthesize':synth}))

def test_claim_from_different_basis_cannot_be_cited(external):
    f,p,basis=external
    revision=deepcopy(p);revision.update(previous_ref=basis['ref'],revision_reason='Revise claim')
    revision['claims'][0]['statement']='A revised claim'
    apply(f.root,'m1.evidence_basis.register',revision)
    new=next(r for r in build_view(f.root)['m1_evidence_bases'] if not r['superseded'])
    f.head=store.read_head(f.root)
    a=artifact(f,p,new);a['content']['findings'][0]['counterevidence_refs']=[basis['claims'][0]['ref']]
    with pytest.raises(ValueError,match='m1_review_evidence_invalid'):f.register(a)

def test_external_draft_does_not_bypass_question_council(ready):
    f,p=ready;apply(f.root,'m1.evidence_basis.register',p)
    basis=build_view(f.root)['m1_evidence_bases'][0];f.head=store.read_head(f.root)
    with pytest.raises(ValueError,match='m1_upstream_review_required'):f.register(artifact(f,p,basis))
