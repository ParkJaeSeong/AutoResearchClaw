from copy import deepcopy
import pytest
from tests.codex_native.test_knowledge_protocol import D,C,INSTANCE,JOB,REQUEST
from researchclaw.codex.knowledge_session import KnowledgeSession


class Transport:
    def __init__(self):self.posts=0;self.current='partial'
    def request(self,method,path,payload=None,params=None):
        if path=='/api/info':return deepcopy(C['info']['body'])
        if path=='/api/knowledge-jobs':self.posts+=1;return deepcopy(C['submit']['body'])
        if path.endswith('/resume'):self.current='persisted';return deepcopy(C['resume']['body'])
        if '/artifacts/' in path:
            identity=path.split('/')[-1]
            chunks=[C['manifest']['body']] if identity=='manifest' else D['artifacts'][identity]
            return deepcopy(next(c for c in chunks if c['offset']==params['offset']))
        return deepcopy(C[self.current]['body'])


def test_submit_partial_resume_and_offline_history(tmp_path):
    transport=Transport();s=KnowledgeSession(tmp_path,transport,INSTANCE,'synthetic-pilot',REQUEST['project_id'])
    s.submit(REQUEST)
    partial=s.observe(REQUEST['request_key'])
    assert partial['knowledge']['status']=='partial'
    s.resume(REQUEST['request_key'],partial['revision'])
    final=s.observe(REQUEST['request_key'])
    assert final['knowledge']['status']=='persisted'
    assert len(s.results(REQUEST['request_key']))==3
    assert transport.posts==1
    offline=KnowledgeSession(tmp_path,None,INSTANCE,'synthetic-pilot',REQUEST['project_id'])
    assert offline.saved(REQUEST['request_key'])==final
    assert len(offline.results(REQUEST['request_key']))==3


def test_conflicting_local_request_never_submits(tmp_path):
    t=Transport();s=KnowledgeSession(tmp_path,t,INSTANCE,'synthetic-pilot',REQUEST['project_id']);s.submit(REQUEST)
    with pytest.raises(ValueError,match='conflict'):s.submit(dict(REQUEST,question='changed'))
    assert t.posts==1
