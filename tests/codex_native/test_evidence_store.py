from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import threading
import tracemalloc
from types import SimpleNamespace

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


def _write_quarantine_record(
    store: EvidenceStore,
    *,
    token: str,
    original_name: str,
    payload: bytes = b"recovery payload",
) -> tuple[Path, Path]:
    """Create an untrusted recovery record without production encoding helpers."""
    data = store.quarantine_root / f".gc-{token}.data"
    metadata = store.quarantine_root / f".gc-{token}.json"
    data.write_bytes(payload)
    observed = data.stat()
    metadata.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "original_name": original_name,
                "snapshot": {
                    "name": original_name,
                    "path": f".researchclaw/evidence/objects/{original_name}",
                    "device": observed.st_dev,
                    "inode": observed.st_ino,
                    "mode": observed.st_mode,
                    "nlink": observed.st_nlink,
                    "size": len(payload),
                    "mtime_ns": observed.st_mtime_ns,
                    "ctime_ns": observed.st_ctime_ns,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return metadata, data


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

    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        store.publish(source)

    assert object_path.read_bytes() == b"corrupt"


def test_reuse_rejects_an_object_with_an_external_hardlink(tmp_path):
    """A second link would allow bytes to mutate outside the immutable object path."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"trusted")
    stored = store.publish(source)
    external_link = project / "external-object-link"
    os.link(project / stored.path, external_link)

    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        store.preflight((source,))
    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        store.publish(source)

    external_link.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="evidence_object_integrity_failure"):
        store.publish(source)


def test_publish_verifies_final_object_only_after_temporary_link_cleanup(
    tmp_path, monkeypatch
):
    """Reporting success while temp and final are hardlinked would accept nlink two."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"trusted")
    observed_link_counts = []
    original = store._verify_object

    def observe(directory_descriptor, digest, expected_size):
        observed_link_counts.append(
            os.stat(
                digest,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            ).st_nlink
        )
        return original(directory_descriptor, digest, expected_size)

    monkeypatch.setattr(store, "_verify_object", observe)

    store.publish(source)

    assert observed_link_counts == [1]
    assert (project / f".researchclaw/evidence/objects/{source.expected_sha256}").stat().st_nlink == 1


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


@pytest.mark.parametrize("fault_point", ["unlink", "directory_fsync", "verify"])
def test_publish_closes_all_descriptors_when_publication_cleanup_fails(
    tmp_path, monkeypatch, fault_point
):
    """Cleanup faults must not bypass closing the source, temp, or object directory."""
    project, store = _store(tmp_path)
    source = _source(project, "result.bin", b"result")
    before = len(tuple(Path("/dev/fd").iterdir()))

    if fault_point == "unlink":
        original_unlink = evidence_store.os.unlink

        def fail_unlink(path, *args, **kwargs):
            if str(path).startswith(".publish-"):
                raise OSError("injected unlink failure")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(evidence_store.os, "unlink", fail_unlink)
    elif fault_point == "directory_fsync":
        original_fsync = evidence_store.os.fsync

        def fail_directory_fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError("injected fsync failure")
            return original_fsync(descriptor)

        monkeypatch.setattr(evidence_store.os, "fsync", fail_directory_fsync)
    else:
        monkeypatch.setattr(
            store,
            "_verify_object",
            lambda *_args: (_ for _ in ()).throw(OSError("injected verify failure")),
        )

    with pytest.raises(OSError, match="injected .* failure"):
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
        evidence_store.os,
        "fstatvfs",
        lambda _descriptor: SimpleNamespace(f_bavail=99_999_999, f_frsize=1),
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
        evidence_store.os,
        "fstatvfs",
        lambda _descriptor: SimpleNamespace(f_bavail=available, f_frsize=1),
    )

    with pytest.raises(ValueError, match="capacity"):
        store.preflight((source,))


def test_preflight_measures_the_open_destination_not_a_replaced_pathname(
    tmp_path, monkeypatch
):
    """Capacity must remain bound to the verified destination directory descriptor."""
    project, store = _store(tmp_path)
    source = _source(project, "data/result.bin", b"result")
    held_objects = store.evidence_root / "objects-held"
    measured_descriptors = []

    def replace_path(_descriptor):
        store.objects_root.rename(held_objects)
        store.objects_root.symlink_to(project / "data", target_is_directory=True)

    def measured(descriptor):
        measured_descriptors.append(descriptor)
        assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
        return SimpleNamespace(f_bavail=99_999_999, f_frsize=1)

    monkeypatch.setattr(
        evidence_store, "_before_capacity_measure", replace_path, raising=False
    )
    monkeypatch.setattr(evidence_store.os, "fstatvfs", measured)
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(AssertionError("pathname disk usage")),
    )

    capacity = store.preflight((source,))

    assert capacity.available_bytes == 99_999_999
    assert len(measured_descriptors) == 1


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


@pytest.mark.parametrize(
    "original_name",
    [
        "../outside",
        "/absolute",
        r"..\outside",
        ".publish-../outside.tmp",
        ".publish-..\\outside.tmp",
        ".publish-\x00outside.tmp",
        ".publish-\u2044outside.tmp",
        ".publish-\u2215outside.tmp",
        ".publish-\uff0foutside.tmp",
    ],
)
def test_gc_recovery_rejects_untrusted_original_names_before_dirfd_use(
    tmp_path, monkeypatch, original_name
):
    """Journal-controlled separators or dot segments must never reach renameat."""
    project, store = _store(tmp_path)
    outside = project / "outside"
    outside.write_bytes(b"unrelated")
    _write_quarantine_record(
        store,
        token="1" * 32,
        original_name=original_name,
    )

    monkeypatch.setattr(
        evidence_store,
        "_native_rename_noreplace",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unsafe rename input")),
        raising=False,
    )

    with pytest.raises(ValueError, match="original name"):
        store.plan_gc()

    assert outside.read_bytes() == b"unrelated"


def test_native_rename_noreplace_preserves_an_existing_destination(tmp_path):
    """The quarantine primitive must never overwrite a destination on collision."""
    source_directory = tmp_path / "source"
    destination_directory = tmp_path / "destination"
    source_directory.mkdir()
    destination_directory.mkdir()
    (source_directory / "candidate").write_bytes(b"candidate")
    (destination_directory / "occupied").write_bytes(b"occupied")
    source_descriptor = os.open(source_directory, os.O_RDONLY)
    destination_descriptor = os.open(destination_directory, os.O_RDONLY)
    try:
        with pytest.raises(FileExistsError):
            evidence_store._native_rename_noreplace(
                source_descriptor,
                "candidate",
                destination_descriptor,
                "occupied",
            )
    finally:
        os.close(destination_descriptor)
        os.close(source_descriptor)

    assert (source_directory / "candidate").read_bytes() == b"candidate"
    assert (destination_directory / "occupied").read_bytes() == b"occupied"


def test_gc_fails_safely_when_native_noreplace_rename_is_unavailable(
    tmp_path, monkeypatch
):
    """GC cannot emulate no-replace with a racy existence check and plain rename."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    monkeypatch.setattr(
        evidence_store, "_NATIVE_RENAME_NOREPLACE", None, raising=False
    )

    with pytest.raises(ValueError, match="native no-replace rename unavailable"):
        store.collect(plan, plan.confirmation_token)

    assert (project / target.path).read_bytes() == b"approved"


def test_gc_native_destination_collision_preserves_both_files(
    tmp_path, monkeypatch
):
    """A destination created at the rename boundary must not be overwritten."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    original_rename = evidence_store._native_rename_noreplace
    collision_payload = b"existing quarantine data"

    def collide(source_fd, source_name, destination_fd, destination_name):
        descriptor = os.open(
            destination_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=destination_fd,
        )
        try:
            os.write(descriptor, collision_payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return original_rename(
            source_fd, source_name, destination_fd, destination_name
        )

    monkeypatch.setattr(evidence_store, "_native_rename_noreplace", collide)

    with pytest.raises(FileExistsError):
        store.collect(plan, plan.confirmation_token)

    assert (project / target.path).read_bytes() == b"approved"
    assert any(
        path.read_bytes() == collision_payload
        for path in store.quarantine_root.glob("*.data")
    )


def test_gc_fsyncs_quarantine_before_source_and_recovers_that_crash(
    tmp_path, monkeypatch
):
    """A crash after durable destination creation must remain safely recoverable."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path
    fsync_order = []
    moved = False
    original_rename = evidence_store._native_rename_noreplace
    original_fsync = evidence_store.os.fsync

    def observe_rename(source_fd, source_name, destination_fd, destination_name):
        nonlocal moved
        result = original_rename(
            source_fd, source_name, destination_fd, destination_name
        )
        moved = True
        return result

    def observe_fsync(descriptor):
        if moved and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_stat = os.fstat(descriptor)
            if directory_stat.st_ino == store.quarantine_root.stat().st_ino:
                fsync_order.append("quarantine")
            elif directory_stat.st_ino == store.objects_root.stat().st_ino:
                fsync_order.append("objects")
        return original_fsync(descriptor)

    monkeypatch.setattr(evidence_store, "_native_rename_noreplace", observe_rename)
    monkeypatch.setattr(evidence_store.os, "fsync", observe_fsync)
    monkeypatch.setattr(
        evidence_store,
        "_after_gc_quarantine_destination_fsync",
        lambda *_args: (_ for _ in ()).throw(OSError("destination durable crash")),
        raising=False,
    )

    with pytest.raises(OSError, match="destination durable crash"):
        store.collect(plan, plan.confirmation_token)

    assert fsync_order == ["quarantine"]
    assert not path.exists()
    assert any(path.read_bytes() == b"approved" for path in store.quarantine_root.glob("*.data"))

    monkeypatch.setattr(
        evidence_store,
        "_after_gc_quarantine_destination_fsync",
        lambda *_args: None,
        raising=False,
    )
    retry = store.plan_gc()
    assert path.read_bytes() == b"approved"
    assert retry.objects == (target,)
    assert store.plan_gc().objects == (target,)


def test_gc_truncates_only_the_held_verified_inode_on_path_substitution(
    tmp_path, monkeypatch
):
    """A replacement at the quarantine pathname must never be deleted or truncated."""
    project, store = _store(tmp_path)
    store.publish(_source(project, "target.bin", b"approved bytes"))
    plan = store.plan_gc()
    replacement = b"unrelated replacement"
    moved_approved: Path | None = None

    def substitute(_snapshot, quarantine_name):
        nonlocal moved_approved
        quarantine_path = store.quarantine_root / quarantine_name
        moved_approved = store.quarantine_root / f"{quarantine_name}.substituted"
        quarantine_path.rename(moved_approved)
        quarantine_path.write_bytes(replacement)

    original_unlink = evidence_store.os.unlink

    def forbid_quarantine_unlink(name, *args, **kwargs):
        if str(name).startswith(".gc-"):
            raise AssertionError("quarantine pathname unlink")
        return original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(
        evidence_store, "_before_gc_quarantine_delete", substitute
    )
    monkeypatch.setattr(evidence_store.os, "unlink", forbid_quarantine_unlink)

    with pytest.raises(ValueError, match="quarantine.*changed"):
        store.collect(plan, plan.confirmation_token)

    assert moved_approved is not None
    assert moved_approved.read_bytes() == b""
    assert any(
        path.read_bytes() == replacement
        for path in store.quarantine_root.glob("*.data")
    )


def test_gc_reclaims_approved_bytes_but_keeps_repeatable_tombstones(tmp_path):
    """Successful GC reclaims content through the FD while retaining bounded recovery state."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"x" * (1024 * 1024)))
    plan = store.plan_gc()

    assert store.collect(plan, plan.confirmation_token) == (target,)

    data_entries = tuple(store.quarantine_root.glob("*.data"))
    metadata_entries = tuple(store.quarantine_root.glob("*.json"))
    assert len(data_entries) == 1
    assert data_entries[0].stat().st_size == 0
    assert len(metadata_entries) == 1
    assert store.plan_gc().objects == ()
    assert store.plan_gc().objects == ()
    assert data_entries[0].stat().st_size == 0


def test_gc_recovers_repeatedly_after_a_crash_after_truncate(
    tmp_path, monkeypatch
):
    """A durable zero-byte tombstone must not be restored as an active object."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    monkeypatch.setattr(
        evidence_store,
        "_after_gc_quarantine_truncate",
        lambda *_args: (_ for _ in ()).throw(OSError("post-truncate crash")),
        raising=False,
    )

    with pytest.raises(OSError, match="post-truncate crash"):
        store.collect(plan, plan.confirmation_token)

    data_entries = tuple(store.quarantine_root.glob("*.data"))
    assert len(data_entries) == 1
    assert data_entries[0].stat().st_size == 0
    assert not (project / target.path).exists()

    monkeypatch.setattr(
        evidence_store,
        "_after_gc_quarantine_truncate",
        lambda *_args: None,
        raising=False,
    )
    assert store.plan_gc().objects == ()
    assert store.plan_gc().objects == ()
    assert data_entries[0].stat().st_size == 0


def test_gc_temp_plan_hash_rejects_same_inode_same_size_restored_mtime_mutation(
    tmp_path, monkeypatch
):
    """Temporary candidates require content identity, not only inode/size/mtime."""
    _project, store = _store(tmp_path)
    temporary = store.objects_root / ".publish-abandoned.tmp"
    temporary.write_bytes(b"AAAA")
    plan = store.plan_gc()

    def mutate(snapshot):
        with temporary.open("r+b") as handle:
            handle.write(b"BBBB")
            handle.flush()
            os.fsync(handle.fileno())
        os.utime(
            temporary,
            ns=(snapshot.mtime_ns, snapshot.mtime_ns),
            follow_symlinks=False,
        )

    monkeypatch.setattr(
        evidence_store, "_before_gc_candidate_quarantine", mutate
    )

    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)

    assert temporary.read_bytes() == b"BBBB"


def test_gc_quarantine_does_not_delete_a_replacement_after_final_scan(
    tmp_path, monkeypatch
):
    """A candidate swapped after revalidation must be restored, never pathname-unlinked."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path
    approved_backup = store.objects_root / ".approved-backup"

    def replace(_snapshot):
        path.rename(approved_backup)
        path.write_bytes(b"unapproved")

    monkeypatch.setattr(
        evidence_store, "_before_gc_candidate_quarantine", replace, raising=False
    )

    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)

    assert path.read_bytes() == b"unapproved"
    assert approved_backup.read_bytes() == b"approved"
    assert tuple(store.quarantine_root.glob("*.data")) == ()
    assert len(tuple(store.quarantine_root.glob("*.json"))) == 1


def test_gc_preserves_mismatched_quarantine_when_original_name_is_occupied(
    tmp_path, monkeypatch
):
    """Unsafe restoration must preserve both unapproved files instead of deleting either."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path
    approved_backup = store.objects_root / ".approved-backup"

    def replace(_snapshot):
        path.rename(approved_backup)
        path.write_bytes(b"unapproved-one")

    def occupy(_snapshot, _quarantine_name):
        path.write_bytes(b"unapproved-two")

    monkeypatch.setattr(
        evidence_store, "_before_gc_candidate_quarantine", replace, raising=False
    )
    monkeypatch.setattr(
        evidence_store, "_before_gc_quarantine_verify", occupy, raising=False
    )

    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)

    assert path.read_bytes() == b"unapproved-two"
    quarantined = tuple(store.quarantine_root.glob("*.data"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"unapproved-one"
    assert len(tuple(store.quarantine_root.glob("*.json"))) == 1


def test_gc_quarantine_rejects_a_hardlink_added_after_final_scan(
    tmp_path, monkeypatch
):
    """A new external link changes the approved topology and must prevent deletion."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path
    external_link = project / "external-gc-link"

    def add_hardlink(_snapshot):
        os.link(path, external_link)

    monkeypatch.setattr(
        evidence_store, "_before_gc_candidate_quarantine", add_hardlink
    )

    with pytest.raises(ValueError, match="stale"):
        store.collect(plan, plan.confirmation_token)

    assert path.read_bytes() == b"approved"
    assert external_link.read_bytes() == b"approved"


def test_gc_quarantine_never_overwrites_an_existing_private_entry(
    tmp_path, monkeypatch
):
    """A quarantine-name collision must preserve both the candidate and recovery data."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    token = "0" * 32
    monkeypatch.setattr(evidence_store.secrets, "token_hex", lambda _size: token)
    collision_name = store._quarantine_name(target.sha256)
    collision = store.quarantine_root / collision_name

    def occupy_quarantine(_snapshot):
        collision.write_bytes(b"existing recovery")

    monkeypatch.setattr(
        evidence_store, "_before_gc_candidate_quarantine", occupy_quarantine
    )

    with pytest.raises(FileExistsError):
        store.collect(plan, plan.confirmation_token)

    assert (project / target.path).read_bytes() == b"approved"
    assert collision.read_bytes() == b"existing recovery"


def test_gc_restores_regular_quarantine_when_verification_errors(
    tmp_path, monkeypatch
):
    """A moved regular inode remains safely restorable when its stream check errors."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path

    def arm_failure(_snapshot, _quarantine_name):
        monkeypatch.setattr(
            evidence_store,
            "_descriptor_digest",
            lambda _descriptor: (_ for _ in ()).throw(
                ValueError("injected quarantine verification error")
            ),
        )

    monkeypatch.setattr(
        evidence_store, "_before_gc_quarantine_verify", arm_failure
    )

    with pytest.raises(ValueError, match="injected quarantine verification error"):
        store.collect(plan, plan.confirmation_token)

    assert path.read_bytes() == b"approved"
    assert tuple(store.quarantine_root.glob("*.data")) == ()
    assert len(tuple(store.quarantine_root.glob("*.json"))) == 1


def test_gc_recovers_a_crash_quarantine_before_retry(tmp_path, monkeypatch):
    """A crash after verified rename must leave recoverable evidence, not data loss."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path

    def crash(_snapshot, _quarantine_name):
        raise OSError("simulated quarantine crash")

    monkeypatch.setattr(
        evidence_store, "_before_gc_quarantine_delete", crash, raising=False
    )
    with pytest.raises(OSError, match="simulated quarantine crash"):
        store.collect(plan, plan.confirmation_token)

    assert not path.exists()
    assert len(tuple(store.quarantine_root.glob("*.data"))) == 1
    assert len(tuple(store.quarantine_root.glob("*.json"))) == 1

    monkeypatch.setattr(
        evidence_store,
        "_before_gc_quarantine_delete",
        lambda _snapshot, _name: None,
        raising=False,
    )
    retry = store.plan_gc()
    assert path.read_bytes() == b"approved"
    assert tuple(store.quarantine_root.glob("*.data")) == ()
    assert len(tuple(store.quarantine_root.glob("*.json"))) == 1
    assert retry.objects == (target,)


def test_gc_recovery_never_pathname_unlinks_quarantine_records(
    tmp_path, monkeypatch
):
    """Recovery moves full data atomically and leaves journal tombstones in place."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"approved"))
    plan = store.plan_gc()
    path = project / target.path

    monkeypatch.setattr(
        evidence_store,
        "_before_gc_quarantine_delete",
        lambda _snapshot, _name: (_ for _ in ()).throw(OSError("first crash")),
    )
    with pytest.raises(OSError, match="first crash"):
        store.collect(plan, plan.confirmation_token)
    original_unlink = evidence_store.os.unlink

    def forbid_quarantine_unlink(name, *args, **kwargs):
        if str(name).startswith(".gc-"):
            raise AssertionError("quarantine pathname unlink")
        return original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(evidence_store.os, "unlink", forbid_quarantine_unlink)
    retry = store.plan_gc()
    assert path.read_bytes() == b"approved"
    assert tuple(store.quarantine_root.glob("*.data")) == ()
    assert len(tuple(store.quarantine_root.glob("*.json"))) == 1
    assert retry.objects == (target,)


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


def test_gc_retains_only_candidate_intersections_from_many_manifest_references(
    tmp_path
):
    """Unique irrelevant references must not grow the retained GC reference set."""
    project, store = _store(tmp_path)
    target = store.publish(_source(project, "target.bin", b"target"))
    unrelated = [
        f".researchclaw/evidence/objects/{hashlib.sha256(str(index).encode()).hexdigest()}"
        for index in range(5000)
    ]
    store.write_manifest("many-references", {"paths": [*unrelated, target.path]})

    tracemalloc.start()
    references, _identities = store._context_references({target.path})
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert references == {target.path}
    assert peak < 8 * 1024 * 1024


def test_gc_enforces_object_entry_cap_without_materializing_listdir(
    tmp_path, monkeypatch
):
    """The 4097th directory entry must stop iteration before an unbounded list exists."""
    _project, store = _store(tmp_path)
    for index in range(4097):
        (store.objects_root / f"unknown-{index:04d}").touch()
    monkeypatch.setattr(
        evidence_store.os,
        "listdir",
        lambda _descriptor: (_ for _ in ()).throw(AssertionError("used os.listdir")),
    )

    with pytest.raises(ValueError, match="entry limit"):
        store.plan_gc()


def test_gc_enforces_context_entry_cap_during_iteration(tmp_path, monkeypatch):
    """Manifest names must be capped while scanning, not after list allocation."""
    _project, store = _store(tmp_path)
    for index in range(4097):
        (store.manifests_root / f"manifest-{index:04d}.json").write_text(
            "{}", encoding="utf-8"
        )
    monkeypatch.setattr(
        evidence_store.os,
        "listdir",
        lambda _descriptor: (_ for _ in ()).throw(AssertionError("used os.listdir")),
    )

    with pytest.raises(ValueError, match="context file limit"):
        store.plan_gc()


def test_gc_allows_exact_context_file_limit_with_unrelated_metadata(tmp_path):
    """Non-context metadata entries must not consume the 4096 context-file budget."""
    _project, store = _store(tmp_path)
    for index in range(4096):
        (store.manifests_root / f"manifest-{index:04d}.json").write_text(
            "{}", encoding="utf-8"
        )

    plan = store.plan_gc()

    assert plan.objects == ()


def test_gc_quarantine_is_private_and_bounded(tmp_path):
    """Recovery state must remain mode 0700 and stop at the 4097th entry."""
    project = tmp_path / "project"
    quarantine = project / ".researchclaw/evidence/gc-quarantine"
    quarantine.mkdir(parents=True, mode=0o777)
    quarantine.chmod(0o777)
    store = EvidenceStore(project)

    assert stat.S_IMODE(store.quarantine_root.stat().st_mode) == 0o700
    for _index in range(4097):
        name = store._quarantine_name(".publish-abandoned.tmp")
        (store.quarantine_root / name).touch()

    with pytest.raises(ValueError, match="quarantine .*entry limit"):
        store.plan_gc()


def test_gc_rejects_quarantine_directory_that_loses_private_mode(tmp_path):
    """GC must not trust recovery files after the quarantine becomes group-readable."""
    _project, store = _store(tmp_path)
    store.quarantine_root.chmod(0o755)

    with pytest.raises(ValueError, match="quarantine.*private"):
        store.plan_gc()
