"""Git hook installation. Existing non-sentinel hooks are kept and chained, never removed."""

from __future__ import annotations

import shlex
import stat
import sys
from pathlib import Path

from rce_sentinel import gitio

MARKER = "# managed-by: rce-sentinel"
HOOKS = ("pre-commit", "post-commit", "post-merge")

TEMPLATE = """#!/bin/sh
{marker}
# Bypass once with: git commit --no-verify
if [ -x "$(dirname "$0")/{name}.pre-rce-sentinel" ]; then
  "$(dirname "$0")/{name}.pre-rce-sentinel" "$@" || exit $?
fi
if [ -x {python} ]; then
  exec {python} -m rce_sentinel hook {name}
fi
exec rce-sentinel hook {name}
"""


def install(repo: Path) -> list[str]:
    hooks_dir = gitio.hooks_dir(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    done = []
    for name in HOOKS:
        path = hooks_dir / name
        if path.exists() and MARKER not in path.read_text(errors="replace"):
            backup = hooks_dir / f"{name}.pre-rce-sentinel"
            if backup.exists():
                done.append(f"{name}: skipped; {name} and {backup.name} both exist, "
                            "merge them by hand")
                continue
            path.replace(backup)
            done.append(f"{name}: existing hook kept as {backup.name} and chained")
        path.write_text(TEMPLATE.format(marker=MARKER, name=name,
                                        python=shlex.quote(sys.executable)))
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        done.append(f"{name}: installed at {path}")
    return done
