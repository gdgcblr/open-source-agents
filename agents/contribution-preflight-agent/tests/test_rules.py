import json

import pytest

from preflight.checks import check_structure
from preflight.rules import RulesError, available_profiles, load_profile, load_rules


def test_profiles_available():
    assert {"generic", "gdgcblr"} <= set(available_profiles())


def test_default_is_generic(tmp_path):
    rules = load_rules(str(tmp_path))
    assert rules.name == "generic"
    assert rules.kebab_case is False
    assert rules.required_files == ["README.md"]


def test_generic_accepts_any_name_and_files(tmp_path):
    root = tmp_path / "Any_Name"
    root.mkdir()
    (root / "README.md").write_text("# Title\n")
    assert check_structure(str(root), load_rules(str(root)))["status"] == "pass"


def test_generic_still_requires_readme(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    result = check_structure(str(root), load_rules(str(root)))
    assert result["status"] == "fail"
    assert any("README.md" in f for f in result["findings"])


def test_override_file_layers_on_generic(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# Title\n")
    (root / ".preflight.json").write_text(json.dumps({"required_files": ["README.md", "LICENSE"]}))
    rules = load_rules(str(root))
    assert rules.name == ".preflight.json"
    result = check_structure(str(root), rules)
    assert any("LICENSE" in f for f in result["findings"])


def test_explicit_profile_wins_over_override(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".preflight.json").write_text(json.dumps({"required_files": ["LICENSE"]}))
    assert load_rules(str(root), "gdgcblr").name == "gdgcblr"


def test_unknown_profile_rejected(tmp_path):
    with pytest.raises(RulesError, match="Unknown profile"):
        load_rules(str(tmp_path), "nope")


def test_unknown_key_rejected(tmp_path):
    (tmp_path / ".preflight.json").write_text(json.dumps({"requird_files": []}))
    with pytest.raises(RulesError, match="Unknown rule keys"):
        load_rules(str(tmp_path))


def test_wrong_type_rejected(tmp_path):
    (tmp_path / ".preflight.json").write_text(json.dumps({"kebab_case": "yes"}))
    with pytest.raises(RulesError, match="kebab_case"):
        load_rules(str(tmp_path))


def test_invalid_json_rejected(tmp_path):
    (tmp_path / ".preflight.json").write_text("{not json")
    with pytest.raises(RulesError, match="Cannot read"):
        load_rules(str(tmp_path))


def test_gdgcblr_profile_loads():
    rules = load_profile("gdgcblr")
    assert rules.kebab_case is True
    assert ".env.example" in rules.required_files
