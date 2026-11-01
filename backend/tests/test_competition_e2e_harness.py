"""Safety of the explicit live integration runner, without calling any model."""
import subprocess
import sys
from pathlib import Path

from scripts.run_competition_e2e import _create_env, _free


def test_e2e_runner_requires_explicit_live_flag():
    runner = Path(__file__).resolve().parents[1] / "scripts" / "run_competition_e2e.py"
    result = subprocess.run([sys.executable, str(runner)],
                            capture_output=True, text=True, timeout=8)
    assert result.returncode != 0
    assert "--live" in result.stderr
    assert "PASS" not in result.stdout


def test_runner_uses_synthetic_database_and_local_proxy(tmp_path):
    target = tmp_path / "synthetic.sqlite"
    env = _create_env(target)
    assert env["DATABASE_URL"] == "sqlite:///" + target.as_posix()
    assert env["VITE_API_PROXY_TARGET"] == "http://127.0.0.1:8022"
    assert env["DEMO_USERNAME"] == "demo"
    assert env["DATA_ENCRYPTION_KEY"] and env["DATA_HMAC_KEY"]
    assert not target.exists()  # This function must not touch any database


def test_occupied_local_port_does_not_appear_free():
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert not _free(port)
