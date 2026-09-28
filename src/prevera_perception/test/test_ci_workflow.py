"""The CI workflow keeps the properties the 2026-09-28 review asked for (M8)."""
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "tests.yml"


def _load():
    # PyYAML reads the bare `on:` key as boolean True; normalise it.
    d = yaml.safe_load(WF.read_text())
    return {("on" if k is True else k): v for k, v in d.items()}


def test_runs_once_per_change_not_twice():
    on = _load()["on"]
    assert on["push"] == {"branches": ["main"]}, "push runs only on main; branches get their run from pull_request"
    assert "pull_request" in on


def test_token_is_read_only():
    assert _load()["permissions"] == {"contents": "read"}


def test_shell_check_uses_sh_for_the_sh_hook():
    run = _load()["jobs"]["pytest"]["steps"][-1]["run"]
    assert "sh -n tools/git-hooks/pre-push" in run
    assert "tools/git-hooks/pre-push" not in run.split("sh -n")[0], "the #!/bin/sh hook is not parsed by bash"
