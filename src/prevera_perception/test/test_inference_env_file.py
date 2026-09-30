"""Reject unsafe credential files before any Docker command, without touching the real device."""
import os
import pwd
import stat
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
UP = REPO / "jetson" / "inference-server-up.sh"
FAKE_KEY = "synthetic-test-key-never-real"


def _executable(path, text):
    path.write_text("#!/bin/sh\n" + text)
    path.chmod(0o700)


def _run(tmp_path, key_file, *, default_path=False, wrong_owner=False):
    """Run the real launcher with only Docker, curl, sleep and the home lookup stubbed."""
    user = pwd.getpwuid(os.getuid()).pw_name
    commands = tmp_path / "commands"
    commands.mkdir()
    docker_calls = tmp_path / "docker-calls"
    _executable(commands / "docker", 'printf "%s\\n" "$*" >> "$DOCKER_CALLS"\n'
                'if [ "$1" = inspect ]; then printf "readonly=true\\n"; fi\n')
    _executable(commands / "curl", "exit 0\n")
    _executable(commands / "sleep", "exit 0\n")
    _executable(commands / "getent", 'printf "%s:x:0:0:test:%s:/bin/sh\\n" "$2" "$TEST_LOGIN_HOME"\n')
    if wrong_owner:
        # Only the metadata read is replaced: no chown, sudo or real ownership changes.
        _executable(commands / "stat", f"printf '{os.getuid() + 1} 600\\n'\n")
    env = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}",
           "SUDO_USER": user, "USER": "not-the-invoking-user", "DOCKER_CALLS": str(docker_calls),
           "TEST_LOGIN_HOME": str(key_file.parent)}
    if default_path:
        env.pop("GUARDIAN_ENV_FILE", None)
    else:
        env["GUARDIAN_ENV_FILE"] = str(key_file)
    proc = subprocess.run(["bash", str(UP)], env=env, capture_output=True, text=True, timeout=10)
    calls = docker_calls.read_text().splitlines() if docker_calls.exists() else []
    assert FAKE_KEY not in proc.stdout + proc.stderr + "\n".join(calls)
    return proc, calls


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_private_file_owned_by_invoking_user_reaches_docker(tmp_path, mode):
    key_file = tmp_path / "credentials.env"
    key_file.write_text(f"ROBOFLOW_API_KEY={FAKE_KEY}\n")
    key_file.chmod(mode)
    proc, calls = _run(tmp_path, key_file)
    assert proc.returncode == 0, proc.stderr
    assert calls[0] == "rm -f inference-server"
    assert any(call.startswith("run ") and f"--env-file {key_file}" in call for call in calls)
    assert stat.S_IMODE(key_file.stat().st_mode) == mode


def test_default_path_uses_sudo_users_home(tmp_path):
    key_file = tmp_path / ".roboflow.env"
    key_file.write_text(f"ROBOFLOW_API_KEY={FAKE_KEY}\n")
    key_file.chmod(0o600)
    proc, calls = _run(tmp_path, key_file, default_path=True)
    assert proc.returncode == 0, proc.stderr
    assert any(f"--env-file {key_file}" in call for call in calls)


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o610, 0o601, 0o000])
def test_unsafe_permissions_fail_before_docker_without_changing_file(tmp_path, mode):
    key_file = tmp_path / "credentials.env"
    key_file.write_text(f"ROBOFLOW_API_KEY={FAKE_KEY}\n")
    key_file.chmod(mode)
    proc, calls = _run(tmp_path, key_file)
    assert proc.returncode != 0
    assert calls == []
    assert "key file" in proc.stdout + proc.stderr
    assert stat.S_IMODE(key_file.stat().st_mode) == mode


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "fifo"])
def test_non_regular_files_fail_before_docker(tmp_path, kind):
    key_file = tmp_path / "credentials.env"
    if kind == "directory":
        key_file.mkdir()
    elif kind == "symlink":
        target = tmp_path / "target.env"
        target.write_text(f"ROBOFLOW_API_KEY={FAKE_KEY}\n")
        target.chmod(0o600)
        key_file.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(key_file, 0o600)
    proc, calls = _run(tmp_path, key_file)
    assert proc.returncode != 0
    assert calls == []
    assert "regular file" in proc.stderr


def test_wrong_owner_fails_before_docker(tmp_path):
    key_file = tmp_path / "credentials.env"
    key_file.write_text(f"ROBOFLOW_API_KEY={FAKE_KEY}\n")
    key_file.chmod(0o600)
    proc, calls = _run(tmp_path, key_file, wrong_owner=True)
    assert proc.returncode != 0
    assert calls == []
    assert "must be owned by" in proc.stderr


@pytest.mark.parametrize("name", [".env", ".env.local", ".roboflow.env", "jetson/local.env"])
def test_local_credential_files_are_ignored(name):
    proc = subprocess.run(["git", "check-ignore", "--no-index", "--quiet", name], cwd=REPO)
    assert proc.returncode == 0


def test_placeholder_example_can_be_committed():
    path = "jetson/roboflow.env.example"
    proc = subprocess.run(["git", "check-ignore", "--no-index", "--quiet", path], cwd=REPO)
    assert proc.returncode == 1
    text = (REPO / path).read_text()
    assert "ROBOFLOW_API_KEY=REPLACE_WITH_YOUR_ROBOFLOW_API_KEY" in text
