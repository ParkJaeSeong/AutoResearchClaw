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


_NETWORK_AUDIT_EVENTS = frozenset(
    {
        "socket.bind",
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyaddr",
        "socket.gethostbyname",
        "socket.gethostbyname_ex",
        "socket.getnameinfo",
        "socket.sendto",
    }
)


def _audit(event: str, _args: object) -> None:
    if event in _NETWORK_AUDIT_EVENTS:
        _deny(event)


if log_path is not None:
    sys.addaudithook(_audit)
    original_socket = socket.socket

    class GuardedSocket(original_socket):
        pass

    def blocked_socket_method(method_name):
        def blocked_method(self, *_args, **_kwargs):
            _deny(f"socket.{method_name}")

        return blocked_method

    network_socket_methods = (
        "accept",
        "bind",
        "connect",
        "connect_ex",
        "getpeername",
        "getsockname",
        "listen",
        "recv",
        "recv_into",
        "recvfrom",
        "recvfrom_into",
        "recvmsg",
        "recvmsg_into",
        "send",
        "sendall",
        "sendfile",
        "sendmsg",
        "sendmsg_afalg",
        "sendto",
        "shutdown",
    )
    for method_name in network_socket_methods:
        if hasattr(original_socket, method_name):
            setattr(
                GuardedSocket,
                method_name,
                blocked_socket_method(method_name),
            )

    # CPython keeps SocketType as a separate public alias when socket is rebound.
    socket.socket = GuardedSocket
    socket.SocketType = GuardedSocket

    def blocked_module_function(function_name):
        def blocked_function(*_args, **_kwargs):
            _deny(f"socket.{function_name}")

        return blocked_function

    network_module_functions = (
        "create_connection",
        "create_server",
        "getaddrinfo",
        "getfqdn",
        "gethostbyaddr",
        "gethostbyname",
        "gethostbyname_ex",
        "getnameinfo",
    )
    for function_name in network_module_functions:
        if hasattr(socket, function_name):
            setattr(socket, function_name, blocked_module_function(function_name))

    probe = os.environ.get("RESEARCHCLAW_STAGE13_NETWORK_GUARD_PROBE")
    if probe is not None:
        try:
            if probe == "tcp":
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                    ("127.0.0.1", 9)
                )
            elif probe == "sockettype_sendmsg":
                socket.SocketType(socket.AF_INET, socket.SOCK_DGRAM).sendmsg(
                    [b"blocked"], [], 0, ("127.0.0.1", 9)
                )
            elif probe == "bind":
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).bind(
                    ("127.0.0.1", 0)
                )
            elif probe == "create_server":
                socket.create_server(("127.0.0.1", 0))
            elif probe == "create_connection":
                socket.create_connection(("127.0.0.1", 9), timeout=0.01)
            elif probe == "sendto":
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(
                    b"blocked", ("127.0.0.1", 9)
                )
            elif probe == "sendto_flags":
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(
                    b"blocked", 0, ("127.0.0.1", 9)
                )
            elif probe == "sendmsg":
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendmsg(
                    [b"blocked"], [], 0, ("127.0.0.1", 9)
                )
            elif probe == "send":
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).send(b"blocked")
            elif probe == "sendall":
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).sendall(b"blocked")
            elif probe == "connect_ex":
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
                    ("127.0.0.1", 9)
                )
            elif probe == "sendfile":
                with Path(__file__).open("rb") as source:
                    socket.socket(socket.AF_INET, socket.SOCK_STREAM).sendfile(source)
            elif probe == "getaddrinfo":
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
