"""Bind a review to an existing work episode; publish observations with graph CAS."""
from copy import deepcopy
from pathlib import Path

from researchclaw.core.research_graph import commands,store


class WorkBinding:
    def __init__(self,root,recipient,materials,packet):
        self.root=Path(root)
        self.recipient=deepcopy(recipient)
        self.materials=deepcopy(materials)
        self.packet=deepcopy(packet)

    def read(self):
        snapshot=store.read_head(self.root)
        episode=snapshot['state'].get('work_episodes',{}).get(self.recipient['work_id'])
        policy=snapshot['state'].get('work_execution_policy',{})
        assignment=snapshot['state'].get('work_execution_assignments',{}).get(self.recipient['work_id'],{})
        assigned=all(assignment.get(k)==v for k,v in self.recipient.items())
        active=bool(episode and episode['execution_status']=='running' and episode['conclusion'] is None
                    and policy.get('status')=='active' and policy.get('milestone')=='M1'
                    and assignment.get('milestone')=='M1' and assignment.get('active') is True and assigned)
        return dict(recipient=deepcopy(self.recipient),active=active,milestone='M1',
                    graph_head=snapshot['id'],project_id=snapshot['state']['project_id'],
                    materials=dict(self.materials,work=deepcopy(episode)),packet=deepcopy(self.packet))

    def publish(self,delivery_id,context,result):
        if not context['active'] or context['recipient']!=self.recipient:
            raise ValueError('review_work_not_active')
        # This records an observation only: it does not adopt a claim or conclude work.
        payload=dict(id=self.recipient['work_id'],kind='output',author=self.recipient['role_id'],
                     text=store._canonical(dict(delivery_id=delivery_id,
                          recipient=self.recipient,review=result['review'],research_adoption=False)).decode())
        receipt=commands.apply_command(self.root,operation='episode.note',payload=payload,
            expected_head=context['graph_head'],command_id='service-review:'+delivery_id)
        return dict(head_id=receipt['id'],work_id=self.recipient['work_id'])
