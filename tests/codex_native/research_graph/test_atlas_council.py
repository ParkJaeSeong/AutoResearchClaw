from researchclaw.core.research_graph import store
from tests.codex_native.research_graph.test_atlas_question import prepared


def council_episodes(root):
    return {key: row for key, row in store.read_head(root)['state'].get('work_episodes', {}).items()
            if key.startswith('atlas-council-')}


def test_council_round_barriers_and_resume_use_native_submissions(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    from researchclaw.codex.atlas_advance import advance_request
    from researchclaw.codex.atlas_council import run_council
    s,c,q=prepared(tmp_path);ask_research_question(s,'k',q);advance_request(s,'k')
    seen=[]
    def reviewer(role,phase,packet,materials,run):
        if phase=='initial':
            assert not packet['disclosed_initials'] and not packet['disclosed_responses']
        if phase=='response': assert len(packet['disclosed_initials'])==3
        if phase=='final': assert len(packet['disclosed_responses'])==3
        seen.append((role,phase))
        return dict(answer=dict(rationale='Evidence is incomplete; retain the question.',recommendation='ready_with_limits' if phase=='final' else None),host_id='synthetic-test',model_id='synthetic')
    result=run_council(s,'k',reviewer)
    assert len(seen)==9
    assert len(result['submission_refs'])==3
    assert len(store.read_head(tmp_path)['state']['council_submissions'])==9
    before=store.read_head(tmp_path)['id']
    assert run_council(s,'k',lambda *a: (_ for _ in ()).throw(AssertionError('No repeated reviews'))) == result
    assert store.read_head(tmp_path)['id']==before


def test_partial_round_resume_does_not_rerun_completed_roles(tmp_path):
    import pytest
    from researchclaw.codex.atlas_question import ask_research_question
    from researchclaw.codex.atlas_advance import advance_request
    from researchclaw.codex.atlas_council import run_council
    s,c,q=prepared(tmp_path);ask_research_question(s,'k',q);advance_request(s,'k')
    calls=[]
    def reviewer(role,phase,packet,materials,run):
        calls.append((role,phase))
        if role=='critical' and phase=='initial':raise ValueError('host interrupted')
        return dict(answer=dict(rationale='Limited evidence',recommendation=None),host_id='test',model_id='synthetic')
    with pytest.raises(ValueError,match='host interrupted'):run_council(s,'k',reviewer)
    assert not store.read_head(tmp_path)['state'].get('council_submissions')
    episode=next(iter(council_episodes(tmp_path).values()))
    assert not any(n['kind']=='dialogue' for n in episode['notes'])
    def resume(role,phase,packet,materials,run):
        if phase=='initial':assert role=='critical'
        return dict(answer=dict(rationale='Limited evidence',recommendation='defer' if phase=='final' else None),host_id='test',model_id='synthetic')
    result=run_council(s,'k',resume)
    assert len(result['submission_refs'])==3
    rows=council_episodes(tmp_path)
    assert len(rows)==1
    assert len([n for n in next(iter(rows.values()))['notes'] if n['kind']=='dialogue'])==9


def test_council_automatically_records_public_episode_and_keeps_review_pending(tmp_path):
    from researchclaw.codex.atlas_question import ask_research_question
    from researchclaw.codex.atlas_council import run_council
    s,c,q=prepared(tmp_path);ask_research_question(s,'k',q)
    def reviewer(role,phase,packet,materials,run):
        rows=council_episodes(tmp_path)
        assert len(rows)==1
        episode=next(iter(rows.values()))
        # Current phase must remain undisclosed while reviewers are executing.
        assert not any(n['kind']=='dialogue' and {'initial':'독립 검토','response':'상호 검토','final':'최종 의견'}[phase] in n['author'] for n in episode['notes'])
        return dict(answer=dict(rationale=f'{role}/{phase} original',recommendation='defer' if phase=='final' else None),host_id='test',model_id='synthetic')
    result=run_council(s,'k',reviewer)
    episode=next(iter(council_episodes(tmp_path).values()))
    assert episode['execution_status']=='finished'
    assert episode['review_status']=='pending' and episode['review'] is None
    dialogue=[n for n in episode['notes'] if n['kind']=='dialogue']
    assert len(dialogue)==9
    assert [n['text'] for n in dialogue]==[f'{role}/{phase} original' for phase in ('initial','response','final') for role in ('domain','methodology','critical')]
    assert result['council_id'] in next(n['text'] for n in episode['notes'] if n['kind']=='output')
    assert '판단 보류 의견 3명' == episode['conclusion']['judgment']
    before=store.read_head(tmp_path)['id']
    run_council(s,'k',lambda *a: (_ for _ in ()).throw(AssertionError('Repeated host')))
    assert store.read_head(tmp_path)['id']==before


def test_episode_commit_without_local_receipt_replays_without_duplicate_dialogue(tmp_path, monkeypatch):
    import pytest
    from researchclaw.codex import atlas_council
    from researchclaw.codex.atlas_question import ask_research_question
    s,c,q=prepared(tmp_path);ask_research_question(s,'k',q)
    original=atlas_council.commands.apply_command
    interrupted=False
    calls=[]
    def apply(*args,**kwargs):
        nonlocal interrupted
        receipt=original(*args,**kwargs)
        if kwargs['operation']=='episode.note' and kwargs['payload']['kind']=='dialogue' and not interrupted:
            interrupted=True
            raise RuntimeError('receipt interrupted after commit')
        return receipt
    monkeypatch.setattr(atlas_council.commands,'apply_command',apply)
    def reviewer(role,phase,*args):
        calls.append((role,phase))
        return dict(answer=dict(rationale=f'{role} {phase}',recommendation='defer' if phase=='final' else None),host_id='synthetic-test',model_id='synthetic')
    with pytest.raises(RuntimeError,match='receipt interrupted'):
        atlas_council.run_council(s,'k',reviewer)
    atlas_council.run_council(s,'k',reviewer)
    assert len(calls)==9 and len(set(calls))==9
    episode=next(iter(council_episodes(tmp_path).values()))
    assert len([n for n in episode['notes'] if n['kind']=='dialogue'])==9
    assert episode['review_status']=='pending'


def test_legacy_completed_result_does_not_backfill_episode(tmp_path):
    import json
    from researchclaw.codex.atlas_council import run_council
    from researchclaw.codex.atlas_question import ask_research_question
    s,c,q=prepared(tmp_path);ask_research_question(s,'k',q)
    base=s.base/('council-'+store._hash(b'k'));base.mkdir()
    result={'stage':'council_complete','legacy_fixture':True}
    (base/'result.json').write_text(json.dumps(result))
    before=store.read_head(tmp_path)
    assert run_council(s,'k',lambda *args: None)==result
    assert store.read_head(tmp_path)==before
    assert not council_episodes(tmp_path)
