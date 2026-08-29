"""Passive local hardware facts used by Stage 11 resource planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import shutil


@dataclass(frozen=True)
class HardwareObservation:
    logical_cpu_count: int
    total_memory_bytes: int
    free_disk_bytes: int
    platform: str
    architecture: str
    gpu_available: bool | None
    method: str
    observed_at: str

    def to_dict(self) -> dict[str, object]:
        """Serialize this immutable observation for a durable task packet."""
        return asdict(self)


def _total_memory_bytes() -> int:
    """Return the physical-memory fact available through the Python standard library."""
    try:
        return max(0, os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def observe_local_hardware(root: Path) -> HardwareObservation:
    """Observe local hardware without subprocesses, probes, or generated-code execution."""
    return HardwareObservation(
        logical_cpu_count=max(1, os.cpu_count() or 1),
        total_memory_bytes=_total_memory_bytes(),
        free_disk_bytes=shutil.disk_usage(root).free,
        platform=platform.system(),
        architecture=platform.machine(),
        gpu_available=None,
        method="python_stdlib_passive",
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
