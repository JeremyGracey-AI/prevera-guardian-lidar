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
    lines = [l.strip() for l in run.splitlines() if l.strip()]
    assert "sh -n tools/git-hooks/pre-push" in lines, "the #!/bin/sh hook gets its own sh -n line"
    bash_lines = [l for l in lines if "bash -n" in l]
    assert bash_lines and all("pre-push" not in l for l in bash_lines), "the hook is not in any bash -n loop"
