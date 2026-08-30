from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import tracemalloc

import pytest

from researchclaw.core import evidence_store
from researchclaw.core.evidence_store import EvidenceSource, EvidenceStore
from researchclaw.core.transactions import project_transaction


def _source(project: Path, relative_path: str, payload: bytes, *, role: str = "result") -> EvidenceSource:
    path = project / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return EvidenceSource(
        role=role,
        path=relative_path,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_size=len(payload),
    )


def _store(tmp_path: Path) -> tuple[Path, EvidenceStore]:
    project = tmp_path / "project"
    project.mkdir()
    return project, EvidenceStore(project)


def test_publish_streams_and_reuses_identical_object(tmp_path):
    """Reopening or duplicating an immutable object would break deduplication."""
    project, store = _store(tmp_path)
    source = _source(project, "data/input.bin", b"research input")

    first = store.publish(source)
    second = store.publish(source)

    assert first == second
    assert first.path == f".researchclaw/evidence/objects/{source.expected_sha256}"
    assert (project / first.path).read_bytes() == b"research input"
    assert [path.name for path in store.objects_root.iterdir()] == [source.expected_sha256]


def test_publish_requires_the_typed_source_contract(tmp_path):
    """A Path-only overload would omit the caller's expected immutable identity."""
    project, store = _store(tmp_path)
    path = project / "result.bin"
    path.write_bytes(b"result")

    with pytest.raises(TypeError):
        store.publish(path)  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_publish_rejects_non_regular_or_symlink_sources(tmp_path, kind):
    """Following an alias or blocking special file would escape the descriptor boundary."""
    project, store = _store(tmp_path)
    target = project / "data/source"
    target.parent.mkdir()
    if kind == "symlink":
        (project / "outside").write_bytes(b"payload")
        target.symlink_to(project / "outside")
    elif kind == "directory":
        target.mkdir()
    else:
        os.mkfifo(target)
    source = EvidenceSource(
        role="result",
        path="data/source",
        expected_sha256=hashlib.sha256(b"payload").hexdigest(),
        expected_size=7,
    )

    with pytest.raises((OSError, ValueError)):
        store.publish(source)


def test_publish_rejects_hash_mismatch_and_removes_temporary_copy(tmp_path):
    """A mismatched caller identity must not leave a publishable or collectible object."""
    project, store = _store(tmp_path)
    source = EvidenceSource(
        role="result",
        path="result.bin",
        expected_sha256=hashlib.sha256(b"other").hexdigest(),
        expected_size=6,
    )
    (project / source.path).write_bytes(b"result")

    with pytest.raises(ValueError, match="identity"):
        store.publish(source)

    assert tuple(store.objects_root.iterdir()) == ()


def test_publish_does_not_replace_a_corrupt_existing_object(tmp_path):
    """Trusting an object name alone would silently reuse attacker-controlled bytes."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"trusted")
    object_path = store.objects_root / source.expected_sha256
    object_path.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="object integrity"):
        store.publish(source)

    assert object_path.read_bytes() == b"corrupt"


def test_publish_cleans_up_an_interrupted_temporary_copy(tmp_path, monkeypatch):
    """An interrupted stream must not expose a partial object or abandoned temporary."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"x" * (2 * 1024 * 1024))
    original = evidence_store._write_all
    writes = 0

    def interrupt(descriptor, chunk):
        nonlocal writes
        writes += 1
        original(descriptor, chunk)
        if writes == 1:
            raise OSError("copy interrupted")

    monkeypatch.setattr(evidence_store, "_write_all", interrupt)

    with pytest.raises(OSError, match="copy interrupted"):
        store.publish(source)

    assert tuple(store.objects_root.iterdir()) == ()


def test_publish_closes_the_source_if_the_store_directory_becomes_unsafe(tmp_path):
    """A failed destination open must not leak the already-held source descriptor."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"result")
    store.objects_root.rmdir()
    store.objects_root.symlink_to(project / "data", target_is_directory=True)
    before = len(tuple(Path("/dev/fd").iterdir()))

    for _ in range(10):
        with pytest.raises(OSError):
            store.publish(source)

    after = len(tuple(Path("/dev/fd").iterdir()))
    assert after == before


def test_publish_detects_source_drift_before_publication(tmp_path, monkeypatch):
    """Changing an open source during copy must invalidate the promised identity."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"before")

    def mutate(_descriptor):
        (project / source.path).write_bytes(b"after!")

    monkeypatch.setattr(evidence_store, "_before_source_recheck", mutate)

    with pytest.raises(ValueError, match="changed while publishing"):
        store.publish(source)

    assert tuple(store.objects_root.iterdir()) == ()


def test_publish_uses_bounded_memory_for_a_32_mib_source(tmp_path):
    """Reading the complete source into memory would violate the streaming boundary."""
    project, store = _store(tmp_path)
    path = project / "large.bin"
    block = b"0123456789abcdef" * 4096
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for _ in range(512):
            handle.write(block)
            digest.update(block)
    source = EvidenceSource("result", "large.bin", digest.hexdigest(), 32 * 1024 * 1024)

    tracemalloc.start()
    stored = store.publish(source)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert stored.size == 32 * 1024 * 1024
    assert peak < 8 * 1024 * 1024


def test_preflight_deduplicates_new_and_verified_reusable_bytes(tmp_path, monkeypatch):
    """Charging duplicate identities twice would overstate required project capacity."""
    project, store = _store(tmp_path)
    reusable = _source(project, "one.bin", b"same", role="result")
    duplicate = _source(project, "two.bin", b"same", role="log")
    new = _source(project, "three.bin", b"new bytes", role="metadata")
    store.publish(reusable)
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(100_000_000, 1, 99_999_999),
    )

    capacity = store.preflight((reusable, duplicate, new))

    assert capacity.required_new_bytes == len(b"new bytes")
    assert capacity.reusable_bytes == len(b"same")
    assert capacity.available_bytes == 99_999_999


def test_preflight_rejects_capacity_without_required_reserve(tmp_path, monkeypatch):
    """Accepting only the payload bytes would leave no crash-safe publication reserve."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"x")
    available = 1 + (16 * 1024 * 1024) - 1
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(available, 0, available),
    )

    with pytest.raises(ValueError, match="capacity"):
        store.preflight((source,))


@pytest.mark.parametrize("path", ["../outside.bin", "/absolute.bin", "data/../input.bin"])
def test_preflight_rejects_non_project_relative_source_paths(tmp_path, path):
    """Capacity approval must not accept a source that publication must later reject."""
    _project, store = _store(tmp_path)
    source = EvidenceSource("result", path, hashlib.sha256(b"x").hexdigest(), 1)

    with pytest.raises(ValueError, match="unsafe artifact path"):
        store.preflight((source,))


def test_write_manifest_is_canonical_exclusive_and_returns_artifact_ref(tmp_path):
    """Rewriting a registration manifest would make prior references mutable."""
    project, store = _store(tmp_path)
    payload = {"z": 2, "a": {"value": 1}}

    artifact = store.write_manifest("registration-1", payload)

    expected = b'{"a":{"value":1},"z":2}'
    assert artifact.path == ".researchclaw/evidence/manifests/registration-1.json"
    assert artifact.size == len(expected)
    assert artifact.sha256 == hashlib.sha256(expected).hexdigest()
    assert (project / artifact.path).read_bytes() == expected
    with pytest.raises(FileExistsError):
        store.write_manifest("registration-1", payload)


def test_write_manifest_rejects_unsafe_id_and_oversized_payload(tmp_path):
    """Traversal or an unbounded manifest would escape or exhaust the evidence store."""
    _project, store = _store(tmp_path)

    with pytest.raises(ValueError):
        store.write_manifest("../outside", {"ok": True})
    with pytest.raises(ValueError, match="byte limit"):
        store.write_manifest("too-large", {"payload": "x" * (1024 * 1024)})


def test_gc_plan_and_collect_remove_only_unreferenced_objects_and_temps(tmp_path):
    """GC must preserve every manifest reference while removing exact dry-run targets."""
    project, store = _store(tmp_path)
    kept = store.publish(_source(project, "kept.bin", b"kept"))
    removed = store.publish(_source(project, "removed.bin", b"removed"))
    store.write_manifest("active", {"objects": [asdict(kept)]})
    temporary = store.objects_root / ".publish-abandoned.tmp"
    temporary.write_bytes(b"partial")

    plan = store.plan_gc()

    assert plan.objects == (removed,)
    assert plan.temporary_paths == (
        ".researchclaw/evidence/objects/.publish-abandoned.tmp",
    )
    assert plan.total_bytes == removed.size + len(b"partial")
    assert len(plan.confirmation_token) == 64
    collected = store.collect(plan, plan.confirmation_token)
    assert collected == (removed,)
    assert (project / kept.path).read_bytes() == b"kept"
    assert not (project / removed.path).exists()
    assert not temporary.exists()


def test_gc_plan_waits_for_an_active_project_mutation(tmp_path):
    """A dry run taken mid-publication could misclassify its live temporary file."""
    project, store = _store(tmp_path)
    finished = threading.Event()

    def plan():
        store.plan_gc()
        finished.set()

    with project_transaction(project):
        worker = threading.Thread(target=plan)
        worker.start()
        assert not finished.wait(0.05)
    worker.join(timeout=2)
    assert finished.is_set()


def test_gc_collect_requires_matching_token_and_unchanged_plan(tmp_path):
    """A stale or unconfirmed dry run must never authorize deletion."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"target"))
    plan = store.plan_gc()

    with pytest.raises(ValueError, match="confirmation"):
        store.collect(plan, "0" * 64)
    store.write_manifest("late", {"object": asdict(target)})
    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)
    assert (project / target.path).exists()


def test_gc_rejects_duplicate_key_and_oversized_manifest_reads(tmp_path):
    """Ambiguous or unbounded manifest input must fail closed before a deletion plan."""
    _project, store = _store(tmp_path)
    duplicate = store.manifests_root / "duplicate.json"
    duplicate.write_bytes(b'{"objects":[],"objects":[]}')

    with pytest.raises(ValueError, match="duplicate"):
        store.plan_gc()

    duplicate.unlink()
    (store.manifests_root / "large.json").write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="byte limit"):
        store.plan_gc()


def test_gc_active_pending_reference_protects_temporary_path(tmp_path):
    """A transaction journal may own a temporary path not yet present in a manifest."""
    project, store = _store(tmp_path)
    temporary = store.objects_root / ".publish-active.tmp"
    temporary.write_bytes(b"in progress")
    pending = project / ".researchclaw/evidence-registration.pending.json"
    pending.write_text(
        json.dumps(
            {
                "path": (
                    ".researchclaw/evidence/objects/.publish-active.tmp"
                )
            }
        ),
        encoding="utf-8",
    )

    plan = store.plan_gc()

    assert plan.temporary_paths == ()
    assert temporary.exists()


def test_gc_rejects_object_replaced_after_dry_run(tmp_path):
    """A same-name replacement is not the exact identity approved by the dry run."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"target"))
    plan = store.plan_gc()
    path = project / target.path
    path.unlink()
    path.write_bytes(b"target")

    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)
    assert path.exists()


def test_gc_rechecks_manifests_immediately_before_removal(tmp_path, monkeypatch):
    """A reference created after the first collect scan must still prevent unlink."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"target"))
    plan = store.plan_gc()

    def add_reference():
        store.write_manifest("just-in-time", {"object": asdict(target)})

    monkeypatch.setattr(evidence_store, "_before_gc_removal", add_reference)

    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)
    assert (project / target.path).exists()


def test_gc_fails_closed_on_a_symlinked_manifest(tmp_path):
    """Following a manifest symlink could hide a reference outside the project."""
    project, store = _store(tmp_path)
    outside = project / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (store.manifests_root / "linked.json").symlink_to(outside)

    with pytest.raises((OSError, ValueError)):
        store.plan_gc()
