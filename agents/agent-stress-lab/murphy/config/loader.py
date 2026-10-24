"""Load murphy.yaml: .env, ${ENV} interpolation, persona files, path resolution, readable errors."""

from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from murphy.config.schema import ProjectConfig

ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")
DEFAULT_NAME = "murphy.yaml"


class ConfigError(Exception):
    pass


def find_config(path: str | Path | None) -> Path:
    candidate = Path(path or os.environ.get("MURPHY_CONFIG") or DEFAULT_NAME)
    if candidate.is_dir():
        candidate = candidate / DEFAULT_NAME
    if not candidate.exists():
        raise ConfigError(f"{candidate}: config file not found (run `murphy init` to create one)")
    return candidate.resolve()


def interpolate(value: Any, where: str) -> Any:
    """Substitute ${VAR} / ${VAR:-default} inside string scalars of an already-parsed document.

    Done after YAML parsing so environment values are always plain strings and can never
    change the document's structure (a value containing ':', '#' or a newline stays literal).
    """
    if isinstance(value, dict):
        return {k: interpolate(v, f"{where}.{k}" if where else str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, f"{where}[{i}]") for i, v in enumerate(value)]
    if not isinstance(value, str):
        return value

    def sub(match: re.Match) -> str:
        name, default = match.group(1), match.group(2)
        env = os.environ.get(name)
        if env is not None:
            return env
        if default is not None:
            return default
        raise ConfigError(f"{where}: environment variable {name} is not set and has no default")

    return ENV_REF.sub(sub, value)


def _expand_personas(raw: list, base: Path, source: str) -> list[dict]:
    personas = []
    for i, entry in enumerate(raw or []):
        if isinstance(entry, dict) and set(entry) == {"file"}:
            files = sorted(glob.glob(str(base / entry["file"])))
            if not files:
                raise ConfigError(f"{source}: personas[{i}].file: no files match {entry['file']!r}")
            for f in files:
                personas.append(interpolate(yaml.safe_load(Path(f).read_text()), Path(f).name))
        else:
            personas.append(entry)
    return personas


def _python_executable(command: list[str]) -> list[str]:
    return [sys.executable, *command[1:]] if command and command[0] in ("python", "python3") else command


def _format_errors(exc: ValidationError, source: str) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        lines.append(f"{source}: {loc}: {err['msg']}")
    return "\n".join(lines)


def load_config(path: str | Path | None = None) -> ProjectConfig:
    file = find_config(path)
    base = file.parent
    load_dotenv(base / ".env", override=False)
    source = file.name
    data = yaml.safe_load(file.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: top level must be a mapping")
    data = interpolate(data, source)
    data["personas"] = _expand_personas(data.get("personas"), base, source)
    try:
        cfg = ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_errors(exc, source)) from None

    ids = [p.id for p in cfg.personas]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"{source}: personas: duplicate ids {sorted({i for i in ids if ids.count(i) > 1})}")
    for upstream in cfg.tools:
        upstream.cwd = str((base / (upstream.cwd or ".")).resolve())
        upstream.command = _python_executable(upstream.command)
    cfg.base_dir, cfg.source = base, file
    for entry in cfg.python_path:
        p = str((base / entry).resolve())
        if p not in sys.path:
            sys.path.append(p)  # append: config dirs must never shadow the stdlib or installed packages
    return cfg
