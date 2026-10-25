"""The shim is transport only, so what it must never do is exit zero on failure:
a silent success would let a `&&` chain proceed as though the command had run."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hypergolic.commands.shim import SHIM_SOURCE, TRANSPORT_FAILURE_EXIT


@pytest.fixture
def shim(tmp_path):
    root = tmp_path / "tools"
    (root / "bin").mkdir(parents=True)
    path = root / "bin" / "probe"
    path.write_text(SHIM_SOURCE)
    path.chmod(0o755)
    return path


def run(shim, env=None, args=()):
    return subprocess.run(
        [sys.executable, str(shim), *args],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **(env or {})},
    )


def serve(frames: list[dict], captured: list[dict]) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            captured.append(
                {
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(self.rfile.read(length)),
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for frame in frames:
                self.wfile.write((json.dumps(frame) + "\n").encode())
                self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    return server, f"127.0.0.1:{server.server_port}"


def test_help_is_read_from_the_generated_readme_without_a_round_trip(shim):
    (shim.parent.parent / "probe").mkdir()
    result = run(shim, args=["--help"])
    # No /tools on this host, so it reports rather than pretending to succeed.
    assert result.returncode == TRANSPORT_FAILURE_EXIT
    assert "no help for probe" in result.stderr


def test_without_a_broker_in_the_environment_it_refuses_loudly(shim):
    result = run(shim)
    assert result.returncode == TRANSPORT_FAILURE_EXIT
    assert "only from a process started by a tool call" in result.stderr


def test_an_unreachable_broker_is_never_mistaken_for_success(shim):
    result = run(shim, env={"HG_BROKER": "127.0.0.1:1", "HG_TOKEN": "t"})
    assert result.returncode == TRANSPORT_FAILURE_EXIT
    assert "broker unreachable" in result.stderr


def test_it_sends_its_own_name_argv_cwd_and_exec_id(shim, tmp_path):
    captured: list[dict] = []
    server, address = serve([{"type": "exit", "code": 0}], captured)
    try:
        result = subprocess.run(
            [sys.executable, str(shim), "pr", "list"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={
                "PATH": os.environ["PATH"],
                "HG_BROKER": address,
                "HG_TOKEN": "tok",
                "HG_EXEC_ID": "exec-1",
            },
        )
    finally:
        server.server_close()
    assert result.returncode == 0
    assert captured[0]["path"] == "/broker/invoke"
    assert captured[0]["auth"] == "Bearer tok"
    assert captured[0]["body"] == {
        "command": "probe",
        "argv": ["pr", "list"],
        "cwd": str(tmp_path),
        "exec_id": "exec-1",
        "stdin": None,
    }


def test_a_stdin_marker_makes_it_read_and_forward_stdin(shim, tmp_path):
    captured: list[dict] = []
    server, address = serve([{"type": "exit", "code": 0}], captured)
    try:
        result = subprocess.run(
            [sys.executable, str(shim), "--dql", "@-"],
            input='fetch logs | filter x == "y\'s"\n',
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={"PATH": os.environ["PATH"], "HG_BROKER": address, "HG_TOKEN": "tok"},
        )
    finally:
        server.server_close()
    assert result.returncode == 0
    body = captured[0]["body"]
    assert body["argv"] == ["--dql", "@-"]
    assert body["stdin"] == 'fetch logs | filter x == "y\'s"\n'


def test_streams_stay_separated_and_the_exit_code_is_the_commands_own(shim):
    frames = [
        {"type": "stdout", "data": "out"},
        {"type": "stderr", "data": "err"},
        {"type": "exit", "code": 3},
    ]
    server, address = serve(frames, [])
    try:
        result = run(shim, env={"HG_BROKER": address, "HG_TOKEN": "t"})
    finally:
        server.server_close()
    assert (result.returncode, result.stdout, result.stderr) == (3, "out", "err")


def test_a_stream_that_ends_without_an_exit_frame_is_a_transport_failure(shim):
    server, address = serve([{"type": "stdout", "data": "partial"}], [])
    try:
        result = run(shim, env={"HG_BROKER": address, "HG_TOKEN": "t"})
    finally:
        server.server_close()
    assert result.returncode == TRANSPORT_FAILURE_EXIT
    assert "without an exit status" in result.stderr
