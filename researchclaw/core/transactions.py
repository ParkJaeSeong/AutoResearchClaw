"""Common project mutation transactions shared by state, artifacts, and events."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
from functools import wraps
import os
from pathlib import Path
import threading


_LOCK_NAME = "project-transaction.lock"
_REGISTRATION_PENDING_NAMES = (
    "research-result-registration.pending.json",
    "evidence/pending-registration.json",
)


def _registration_pending(metadata_root: Path) -> bool:
    return any(
        os.path.lexists(metadata_root / name) for name in _REGISTRATION_PENDING_NAMES
    )


_locks_guard = threading.Lock()
_process_locks: dict[str, threading.RLock] = {}
_thread_state = threading.local()


def _process_lock(key: str) -> threading.RLock:
    with _locks_guard:
        return _process_locks.setdefault(key, threading.RLock())


def _contexts() -> dict[str, dict[str, object]]:
    contexts = getattr(_thread_state, "contexts", None)
    if contexts is None:
        contexts = {}
        _thread_state.contexts = contexts
    return contexts


@contextmanager
def project_transaction(root: Path, *, allow_pending: bool = False):
    """Serialize every project mutation and reject unrelated pending work."""
    project_root = Path(root).resolve(strict=True)
    metadata_root = project_root / ".researchclaw"
    key = str(project_root)
    process_lock = _process_lock(key)
    with process_lock:
        contexts = _contexts()
        existing = contexts.get(key)
        if existing is not None:
            existing["depth"] = int(existing["depth"]) + 1
            prior_allow = bool(existing["allow_pending"])
            existing["allow_pending"] = prior_allow or allow_pending
            try:
                if not bool(existing["allow_pending"]) and _registration_pending(
                    metadata_root
                ):
                    raise ValueError("project_transaction_pending")
                yield
            finally:
                existing["allow_pending"] = prior_allow
                existing["depth"] = int(existing["depth"]) - 1
            return

        descriptor = os.open(
            metadata_root / _LOCK_NAME,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            contexts[key] = {
                "depth": 1,
                "allow_pending": allow_pending,
                "descriptor": descriptor,
            }
            if not allow_pending and _registration_pending(metadata_root):
                raise ValueError("project_transaction_pending")
            yield
        finally:
            contexts.pop(key, None)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def project_mutation(function):
    """Decorate a project-first operation so all of its writes share one lock."""

    @wraps(function)
    def locked(project, *args, **kwargs):
        with project_transaction(project.root):
            return function(project, *args, **kwargs)

    return locked
