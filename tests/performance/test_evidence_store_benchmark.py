import hashlib
import time
import tracemalloc

import pytest

from researchclaw.core.evidence_store import EvidenceSource, EvidenceStore


@pytest.mark.large_evidence
def test_one_gib_evidence_store_streaming_and_deduplication(tmp_path, capsys):
    root = tmp_path / "one-gib"
    path = root / "data/evidence.bin"
    path.parent.mkdir(parents=True)
    total = 1024 * 1024 * 1024
    block = bytes(range(256)) * 4096
    digest = hashlib.sha256()
    with path.open("wb") as stream:
        remaining = total
        while remaining:
            payload = block[: min(len(block), remaining)]
            stream.write(payload)
            digest.update(payload)
            remaining -= len(payload)
    source = EvidenceSource("input", "data/evidence.bin", digest.hexdigest(), total)
    store = EvidenceStore(root)

    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    started = time.perf_counter()
    first = store.publish(source)
    first_seconds = time.perf_counter() - started
    started = time.perf_counter()
    second = store.publish(source)
    reused_seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    capacity = store.preflight((source,))

    assert first == second
    assert first.sha256 == digest.hexdigest()
    assert capacity.required_new_bytes == 0
    assert capacity.reusable_bytes == total
    assert peak - baseline < 32 * 1024 * 1024
    with capsys.disabled():
        print(
            "evidence benchmark: "
            f"throughput_mib_s={total / (1024 * 1024) / first_seconds:.2f} "
            f"peak_python_mib={(peak - baseline) / (1024 * 1024):.2f} "
            f"first_publication_s={first_seconds:.3f} "
            f"reused_object_s={reused_seconds:.3f} "
            f"deduplicated_bytes={capacity.reusable_bytes}"
        )
