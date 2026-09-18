import json
from pathlib import Path
import pytest
from researchclaw.codex.knowledge_package import collect_artifact, validate_manifest

FIXTURE=Path(__file__).parents[1]/'fixtures/atlas-knowledge-v1'

def read(name):return json.loads((FIXTURE/name).read_text())


def test_atlas_synthetic_package_roundtrip():
    ref=read('package-ref.json')
    raw=collect_artifact([read('manifest.chunk.json')],ref)
    assert raw==(FIXTURE/'manifest.raw.json').read_bytes()
    m=validate_manifest(raw,ref,'7443ba03-cc13-4783-afda-701f74256378','knowledge-fixture')
    for item in m['artifacts']:
        raw=collect_artifact([read(item['artifact_id']+'.chunk.json')],item)
        assert raw==(FIXTURE/(item['artifact_id']+'.raw.md')).read_bytes()


@pytest.mark.parametrize('change',[{'offset':1},{'eof':False},{'next_offset':1},{'size':0},{'data':'bad!!'},{'artifact_id':'other'}])
def test_corrupt_chunk_rejected(change):
    chunk=read('manifest.chunk.json');chunk.update(change)
    with pytest.raises(ValueError):collect_artifact([chunk],read('package-ref.json'))


def test_wrong_service_identity_rejected():
    with pytest.raises(ValueError,match='identity'):
        validate_manifest((FIXTURE/'manifest.raw.json').read_bytes(),read('package-ref.json'),'wrong','knowledge-fixture')


def test_truncated_stream_rejected():
    chunk=read('manifest.chunk.json');chunk['eof']=False;chunk['next_offset']=chunk['size']
    with pytest.raises(ValueError):collect_artifact([chunk],read('package-ref.json'))
