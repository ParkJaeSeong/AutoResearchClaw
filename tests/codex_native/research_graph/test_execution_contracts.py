import pytest
from researchclaw.core.research_graph import execution_contracts as c


def contract():
    return dict(version=1, step_id='evidence_review', purpose_kind='research', purpose='자료 사용 범위 검토', milestone='M1', required_inputs=['source'], roles=['domain','methodology','critical','coordinator'], output_schema='evidence_review_v1', acceptance_checks=['claims','evidence','review'], dependencies=[], allowed_successors=[])


def packet():
    return {'sources':[{'evidence_ref':'source-1','text':'Synthetic observation','location':'p.1'}], 'metadata':{'content_origin':'synthetic'}}


def result():
    return dict(claims=[dict(text='Synthetic claim',evidence_refs=['source-1'],scope='fixture')], unresolved=[], recommendation='use', rationale='Synthetic review')


def test_empty_contract_rejected():
    with pytest.raises(ValueError, match='execution_contract_invalid'): c.validate_contract({})


def test_required_input_and_output():
    assert c.check_input(contract(), {'sources':[]})['status']=='blocked'
    assert c.check_input(contract(),packet())['status']=='pass'
    assert c.check_output(contract(),packet(),result())['status']=='pass'
    for change in ({'text':''},{'evidence_refs':['unknown']}):
        r=result(); r['claims'][0].update(change)
        assert c.check_output(contract(),packet(),r)['status']=='needs_work'
    r=result();r['recommendation']='hold'
    assert c.check_output(contract(),packet(),r)['status']=='needs_work'


def test_unknown_fields_rejected():
    value=contract();value['accepted']=True
    with pytest.raises(ValueError): c.validate_contract(value)


def test_metadata_and_schema_types_are_bounded():
    p=packet();p['metadata']={'content_origin':'synthetic','token':'abc'}
    assert c.check_input(contract(),p)['status']=='blocked'
    value=contract();value['version']=True
    with pytest.raises(ValueError):c.validate_contract(value)
