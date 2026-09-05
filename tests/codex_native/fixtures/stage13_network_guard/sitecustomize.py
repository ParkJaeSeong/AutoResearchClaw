"""Test-only child-interpreter network denial for the Stage 13 E2E fixture.

Activated only by ``RESEARCHCLAW_STAGE13_NETWORK_GUARD_LOG``.  Python imports
``sitecustomize`` before the candidate entry point, so the audit hook also
covers calls made by imported provider clients rather than just the parent test
process.  A probe deliberately performs a socket connection to prove the guard
rejects and records it.
"""

import os
from pathlib import Path
import socket
import sys


log_path = os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_LOG")


def _record(event: str) -> None:
    if log_path is not None:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            handle.write(f"{event}\n")


def _deny_network(event: str, _args: object) -> None:
    if event == "socket.connect":
        probe = os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_PROBE", "socket")
        _record(f"{probe}:socket.connect")
        raise RuntimeError("stage13 test guard forbids network or LLM API calls")


if log_path is not None:
    sys.addaudithook(_deny_network)
    if os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_PROBE") is not None:
        try:
            socket.create_connection(("127.0.0.1", 9), timeout=0.01)
        except RuntimeError:
            # Python reports a sitecustomize exception but otherwise continues;
            # explicitly stop this child so an attempted call cannot execute the
            # candidate entry point.
            os._exit(71)
