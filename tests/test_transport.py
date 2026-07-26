from __future__ import annotations

import sys

import pytest

from memstrata_client import ProtocolError, RuntimeFailure, RuntimeTimeout
from memstrata_client.transport import SubprocessTransport


def command(code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", code)


def test_transport_accepts_one_json_line() -> None:
    transport = SubprocessTransport(
        command("import sys; sys.stdin.readline(); print('{\"ok\":true}')")
    )
    assert transport.execute({"request": 1}) == {"ok": True}


def test_transport_rejects_multiple_lines() -> None:
    transport = SubprocessTransport(
        command("import sys; sys.stdin.readline(); print('{}'); print('{}')")
    )
    with pytest.raises(ProtocolError, match="exactly one"):
        transport.execute({"request": 1})


def test_transport_rejects_invalid_utf8() -> None:
    code = "import sys; sys.stdin.readline(); sys.stdout.buffer.write(b'\\xff\\n')"
    with pytest.raises(ProtocolError, match="not UTF-8"):
        SubprocessTransport(command(code)).execute({"request": 1})


def test_transport_rejects_oversized_response_without_loading_it() -> None:
    code = "import sys; sys.stdin.readline(); sys.stdout.write('x'*1024+'\\n')"
    with pytest.raises(ProtocolError, match="exceeds"):
        SubprocessTransport(command(code), max_response_bytes=100).execute({"request": 1})


def test_transport_timeout_kills_runtime() -> None:
    code = "import sys,time; sys.stdin.readline(); time.sleep(5)"
    with pytest.raises(RuntimeTimeout):
        SubprocessTransport(command(code), timeout=0.05).execute({"request": 1})


def test_transport_suppresses_runtime_stderr_content() -> None:
    secret = "message-content-must-not-escape"
    code = f"import sys; sys.stdin.readline(); sys.stderr.write('{secret}'); sys.exit(3)"
    with pytest.raises(RuntimeFailure) as caught:
        SubprocessTransport(command(code)).execute({"request": 1})
    assert secret not in str(caught.value)
    assert "diagnostic bytes suppressed" in str(caught.value)
