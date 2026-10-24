"""Reporters. All of them render the same ReportData built from a matrix directory."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from murphy.report import model
from murphy.report.junit import junit
from murphy.report.text import markdown, terminal

OUTPUTS = ("report.html", "results.json", "report.md", "junit.xml")


def html(data: dict) -> str:
    template = resources.files("murphy.report").joinpath("template.html").read_text()
    # "</" must not appear inside the <script> block, or trace text could close it (XSS).
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    return template.replace("__MURPHY_DATA__", payload)


def write_all(matrix_dir: Path) -> dict:
    data = model.build(matrix_dir)
    (matrix_dir / "report.html").write_text(html(data))
    (matrix_dir / "results.json").write_text(json.dumps(
        {k: v for k, v in data.items() if k != "runs"} | {"runs": [{"cell": r["cell"], **r["result"]} for r in data["runs"]]},
        indent=2, default=str))
    (matrix_dir / "report.md").write_text(markdown(data))
    (matrix_dir / "junit.xml").write_text(junit(data))
    return data


__all__ = ["OUTPUTS", "html", "markdown", "terminal", "junit", "write_all", "model"]
