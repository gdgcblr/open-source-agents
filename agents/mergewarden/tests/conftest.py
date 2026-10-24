"""Fixtures: a throwaway upstream-like git repo and a helper to add a contribution."""

from __future__ import annotations

import itertools
import shutil
from pathlib import Path

import pytest

import testkit


@pytest.fixture(scope="session")
def _upstream_template(tmp_path_factory) -> Path:
    return testkit.build_upstream(tmp_path_factory.mktemp("upstream") / "repo")


@pytest.fixture
def upstream_repo(_upstream_template, tmp_path) -> Path:
    """A fresh copy of the upstream repo (main = CONTRIBUTING.md, template/, .github/, indexes)."""
    dest = tmp_path / "repo"
    shutil.copytree(_upstream_template, dest)
    return dest


@pytest.fixture
def contrib(upstream_repo, tmp_path):
    """contrib(files, force=(), project=None, body=None) -> (Submission, Policy)."""
    n = itertools.count()

    def _contrib(files, **kw):
        return testkit.contribute(upstream_repo, files, workdir=tmp_path / f"work{next(n)}", **kw)

    return _contrib
