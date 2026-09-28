"""Structural guards for the Jetson Python floor (plan v4, section 1 "Python floor").

The Jetson runs Python 3.10 with apt numpy 1.x / scikit-learn 0.23.x (jammy). These
tests make the floor a test failure rather than a one-time shell check. No ordering
dependency on the other test files.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import numpy
import pytest
import sklearn

_TEST_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _TEST_DIR.parent / "prevera_perception"
_HARNESS_DIR = _TEST_DIR.parents[2] / "tools" / "bag_analysis"

# Regexes over source text. Written so that this file's own source does not match them.
_TOMLLIB_IMPORT = re.compile(r"^\s*(?:import|from)\s+tomllib\b", re.MULTILINE)
_TYPING_SELF_IMPORT = re.compile(r"^\s*from\s+typing\s+import\b[^\n]*\bSelf\b", re.MULTILINE)
_TYPING_SELF_ATTR = re.compile(r"\btyping\.Self\b")


def test_python_is_310():
    if os.environ.get("PREVERA_ALLOW_OTHER_PY") == "1":
        pytest.skip("PREVERA_ALLOW_OTHER_PY=1")
    assert sys.version_info[:2] == (3, 10), sys.version


def test_numpy_major_version_is_1():
    if os.environ.get("PREVERA_ALLOW_NUMPY2") == "1":
        pytest.skip("PREVERA_ALLOW_NUMPY2=1")
    assert numpy.__version__.split(".")[0] == "1", numpy.__version__


def test_sklearn_version_recorded():
    major_minor = tuple(int(x) for x in sklearn.__version__.split(".")[:2])
    print(
        f"SKLEARN_VERSION={sklearn.__version__} NUMPY_VERSION={numpy.__version__} "
        f"PYTHON={sys.version.split()[0]}"
    )
    assert major_minor >= (0, 23), sklearn.__version__


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in (_PACKAGE_DIR, _TEST_DIR, _HARNESS_DIR):
        assert root.is_dir(), root
        files.extend(sorted(root.rglob("*.py")))
    assert files
    return files


def test_language_floor():
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        # Rejects except*, `type X = ...`, PEP 695 generics; accepts match and walrus.
        ast.parse(source, filename=str(path), feature_version=(3, 10))
        assert not _TOMLLIB_IMPORT.search(source), f"{path}: imports the 3.11+ toml module"
        assert not _TYPING_SELF_IMPORT.search(source), f"{path}: imports Self from typing (3.11+)"
        assert not _TYPING_SELF_ATTR.search(source), f"{path}: uses the Self attribute of typing (3.11+)"
