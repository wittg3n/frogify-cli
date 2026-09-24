"""Exercise real frozen command paths without contacting music providers."""

import os
import subprocess
from pathlib import Path

import pytest

EXECUTABLE = os.environ.get("FROGIFY_TEST_EXECUTABLE")
pytestmark = pytest.mark.skipif(not EXECUTABLE, reason="requires Linux standalone executable")


@pytest.fixture
def frozen(tmp_path):
    env = os.environ | {
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "NO_COLOR": "1",
        "COLUMNS": "160",
    }

    def run(*args):
        return subprocess.run(
            [str(Path(EXECUTABLE).resolve()), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=40,
        )

    return run


def test_config_and_sqlite_retry(frozen):
    assert frozen("config", "set", "network.timeout", "5").returncode == 0
    result = frozen("config", "get", "network.timeout")
    assert result.returncode == 0 and "5" in result.stdout
    assert frozen("config").returncode == 0
    result = frozen("retry")
    assert result.returncode == 0 and "Retried 0" in result.stdout


def test_help_and_debug_traceback_rendering(frozen):
    result = frozen("--help")
    assert result.returncode == 0
    assert "Show ranked candidates" in result.stdout
    result = frozen("--debug", "config", "get", "unknown.key")
    assert result.returncode == 1
    assert "ConfigurationError" in result.stdout
    assert "ModuleNotFoundError" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("search", "hello", "--limit", "0"),
        ("batch", "/nonexistent/frogify-fixture.csv"),
        ("retry", "--invalid-option"),
        ("hello", "--invalid-option"),
    ],
)
def test_command_argument_validation(frozen, args):
    result = frozen(*args)
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    assert "Traceback" not in result.stderr
