"""Child-interpreter network denial used only by the Stage 13 E2E fixture.

The guard is activated by ``RESEARCHCLAW_STAGE13_NETWORK_GUARD_LOG`` before a
candidate entry point imports anything. It denies network operations while
leaving local file access and ordinary subprocess execution untouched.
"""

import os
from pathlib import Path
import socket
import sys


log_path = os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_LOG")


def _record(event: str) -> None:
    if log_path is not None:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            probe = os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_PROBE", "run")
            handle.write(f"{probe}:{event}\n")


def _deny(event: str) -> None:
    _record(event)
    raise RuntimeError("stage13 test guard forbids network or LLM API calls")


def _audit(event: str, _args: object) -> None:
    if event in {
        "socket.connect",
        "socket.sendto",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyname_ex",
        "socket.gethostbyaddr",
    }:
        _deny(event)


if log_path is not None:
    sys.addaudithook(_audit)
    original_socket = socket.socket

    class GuardedSocket(original_socket):
        def connect(self, _address):
            _deny("socket.connect")

        def send(self, _data, _flags=0):
            _deny("socket.send")

        def sendall(self, _data, _flags=0):
            _deny("socket.sendall")

        def sendto(self, _data, _address):
            _deny("socket.sendto")

    socket.socket = GuardedSocket

    def blocked_getaddrinfo(*_args, **_kwargs):
        _deny("socket.getaddrinfo")

    def blocked_gethostbyname(*_args, **_kwargs):
        _deny("socket.gethostbyname")

    def blocked_gethostbyname_ex(*_args, **_kwargs):
        _deny("socket.gethostbyname_ex")

    def blocked_gethostbyaddr(*_args, **_kwargs):
        _deny("socket.gethostbyaddr")

    socket.getaddrinfo = blocked_getaddrinfo
    socket.gethostbyname = blocked_gethostbyname
    socket.gethostbyname_ex = blocked_gethostbyname_ex
    socket.gethostbyaddr = blocked_gethostbyaddr

    probe = os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_PROBE")
    if probe is not None:
        try:
            if probe == "tcp":
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                    ("127.0.0.1", 9)
                )
            elif probe == "create_connection":
                socket.create_connection(("127.0.0.1", 9), timeout=0.01)
            elif probe == "udp":
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(
                    b"blocked", ("127.0.0.1", 9)
                )
            elif probe == "send":
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).send(b"blocked")
            elif probe == "sendall":
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).sendall(b"blocked")
            elif probe == "dns":
                socket.getaddrinfo("localhost", 9)
            elif probe == "dns_name":
                socket.gethostbyname("localhost")
            elif probe == "dns_name_ex":
                socket.gethostbyname_ex("localhost")
            elif probe == "dns_addr":
                socket.gethostbyaddr("127.0.0.1")
            elif probe == "provider":
                from researchclaw.llm.client import LLMClient, LLMConfig

                client = LLMClient(
                    LLMConfig(
                        base_url="https://provider.invalid/v1",
                        api_key="test-key",
                        max_retries=1,
                        timeout_sec=1,
                    )
                )
                client.chat([{"role": "user", "content": "network probe"}])
            else:
                raise ValueError(f"unknown Stage 13 guard probe: {probe}")
        except Exception:
            os._exit(71)
