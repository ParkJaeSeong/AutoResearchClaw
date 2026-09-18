"""Bounded, deterministic structural checks; these do not certify science."""
from copy import deepcopy

ROLES = ['domain', 'methodology', 'critical', 'coordinator']
PHASES = ['initial', 'response', 'final']


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 50000


def validate_contract(contract):
    keys = {'version','step_id','purpose_kind','purpose','milestone','required_inputs','roles','output_schema','acceptance_checks','dependencies','allowed_successors'}
    if (type(contract) is not dict or set(contract) != keys or type(contract['version']) is not int or contract['version'] != 1
            or contract['step_id'] != 'evidence_review' or contract['purpose_kind'] != 'research'
            or contract['milestone'] != 'M1' or not _text(contract['purpose'])
            or contract['required_inputs'] != ['source'] or contract['roles'] != ROLES
            or contract['output_schema'] != 'evidence_review_v1'
            or contract['acceptance_checks'] != ['claims','evidence','review']
            or contract['dependencies'] != [] or contract['allowed_successors'] != []):
        raise ValueError('execution_contract_invalid')
    return deepcopy(contract)


def _report(check_id, ok, reason, status='needs_work'):
    return {'status':'pass' if ok else status, 'checks':[{'check_id':check_id,
        'checker_version':'1','status':'pass' if ok else status,'evidence_refs':[],
        'reason':reason,'affected_judgments':['source_use'],'next_action':'' if ok else 'revise_input_or_result'}]}


def check_input(contract, packet):
    validate_contract(contract)
    ok = type(packet) is dict and not(set(packet)-{'sources','metadata'}) and type(packet.get('sources')) is list and 0 < len(packet['sources']) <= 100
    refs=[]
    if ok and 'metadata' in packet:
        metadata=packet['metadata']
        ok=type(metadata) is dict and set(metadata)=={'content_origin'} and metadata['content_origin'] in ('synthetic','real','mixed')
    if ok:
        for source in packet['sources']:
            if type(source) is not dict or set(source)!={'evidence_ref','text','location'} or not all(_text(v) for v in source.values()):
                ok=False;break
            refs.append(source['evidence_ref'])
        ok = ok and len(refs)==len(set(refs))
    return _report('required_input', bool(ok), 'input_available' if ok else 'source_missing', 'blocked')


def check_output(contract, packet, result):
    if check_input(contract,packet)['status']!='pass':
        return _report('required_input',False,'source_missing','blocked')
    keys={'claims','unresolved','recommendation','rationale'}
    if type(result) is not dict or set(result)!=keys or result.get('recommendation') not in ('use','limited','hold') or not _text(result.get('rationale')) or type(result.get('claims')) is not list or type(result.get('unresolved')) is not list:
        return _report('output_schema',False,'output_invalid')
    known={s['evidence_ref'] for s in packet['sources']}
    for claim in result['claims']:
        if type(claim) is not dict or set(claim)!={'text','evidence_refs','scope'} or not _text(claim['text']) or not _text(claim['scope']):
            return _report('claims',False,'claim_invalid')
        refs=claim['evidence_refs']
        if type(refs) is not list or not refs or any(not isinstance(r,str) or r not in known for r in refs):
            return _report('evidence',False,'evidence_ref_unknown')
    for issue in result['unresolved']:
        if type(issue) is not dict or set(issue)!={'question','impact','next_action'} or not all(_text(v) for v in issue.values()):
            return _report('output_schema',False,'unresolved_invalid')
    if not result['claims'] or result['recommendation']=='hold':
        return _report('source_use',False,'source_on_hold')
    return _report('structural_output',True,'structure_valid')
