import json
from dataclasses import dataclass, field, fields
from pathlib import Path

PROFILES_DIR = Path(__file__).parent / "profiles"
OVERRIDE_FILE = ".preflight.json"
DEFAULT_PROFILE = "generic"


class RulesError(Exception):
    pass


@dataclass
class Rules:
    name: str = DEFAULT_PROFILE
    kebab_case: bool = False
    forbidden_names: list[str] = field(default_factory=list)
    required_files: list[str] = field(default_factory=list)
    manifest_any_of: list[str] = field(default_factory=list)
    template_markers: list[str] = field(default_factory=list)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RulesError(f"Cannot read rules file {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise RulesError(f"Rules file {path.name} must contain a JSON object.")
    return data


def _build(data: dict, base: Rules | None = None) -> Rules:
    allowed = {item.name for item in fields(Rules)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise RulesError("Unknown rule keys: " + ", ".join(unknown))
    merged = {item.name: getattr(base or Rules(), item.name) for item in fields(Rules)}
    for key, value in data.items():
        expected = type(merged[key])
        if not isinstance(value, expected):
            raise RulesError(f"Rule '{key}' must be of type {expected.__name__}.")
        if expected is list and not all(isinstance(entry, str) for entry in value):
            raise RulesError(f"Rule '{key}' must be a list of strings.")
        merged[key] = value
    return Rules(**merged)


def available_profiles() -> list[str]:
    return sorted(path.stem for path in PROFILES_DIR.glob("*.json"))


def load_profile(name: str) -> Rules:
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        raise RulesError(f"Unknown profile '{name}'. Available: {', '.join(available_profiles())}")
    return _build(_read_json(path))


def load_rules(project_path: str, profile: str | None = None) -> Rules:
    if profile:
        return load_profile(profile)
    base = load_profile(DEFAULT_PROFILE)
    override = Path(project_path) / OVERRIDE_FILE
    if override.is_file():
        data = _read_json(override)
        data.setdefault("name", OVERRIDE_FILE)
        return _build(data, base)
    return base
