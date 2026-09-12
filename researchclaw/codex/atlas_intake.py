"""Explicit local QA file adapter; linked source paths are never opened."""
import base64
from pathlib import Path

from researchclaw.core.research_graph import commands, store


def read_qa(path: Path) -> bytes:
    from researchclaw.core.research_graph.atlas_format import MAX_QA_BYTES, parse_atlas_qa
    with path.open('rb') as stream:
        data = stream.read(MAX_QA_BYTES + 1)
    parse_atlas_qa(data)
    return data


def import_qa(root: Path, *, data: bytes, filename: str, expected_head: str, command_id: str) -> dict:
    receipt = commands.apply_command(root, operation='external.evidence.import',
        payload=dict(content_base64=base64.b64encode(data).decode('ascii'), sha256=store._hash(data),
                     filename=filename, producer_id='pilot-coordinator'),
        expected_head=expected_head, command_id=command_id)
    return mutation_result(receipt)


def mutation_result(receipt: dict) -> dict:
    return dict(head_id=receipt['id'], record_id=receipt['events'][-1]['payload']['record_id'])
