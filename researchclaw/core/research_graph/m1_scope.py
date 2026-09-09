"""Scope/questions adaptation of native M1 node review, not user approval."""
from .m1_nodes import review_node
from .issues import _require


def prepare_scope_council(snapshot: dict, *, node_id: str) -> dict:
    _require(node_id in ('scope', 'questions'), 'm1_node_invalid')
    return review_node(snapshot, node_id)
