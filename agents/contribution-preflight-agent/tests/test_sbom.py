import json
from datetime import datetime, timezone

from preflight.sbom import build_cyclonedx, collect_components, parse_python_requirement, purl_for


def by_name(components: list[dict]) -> dict:
    return {item["name"]: item for item in components}


def test_pinned_requirement():
    component = parse_python_requirement("requests==2.32.3", "requirements.txt")
    assert component["pinned"] is True
    assert component["version"] == "2.32.3"
    assert component["purl"] == "pkg:pypi/requests@2.32.3"


def test_unpinned_requirement_variants():
    for line in ("flask>=3.0", "numpy", "pandas~=2.1", "django==4.*"):
        component = parse_python_requirement(line, "requirements.txt")
        assert component["pinned"] is False, line
        assert component["version"] == ""


def test_extras_markers_and_comments():
    component = parse_python_requirement("uvicorn[standard]==0.30.0 ; python_version >= '3.9'  # server", "requirements.txt")
    assert component["name"] == "uvicorn"
    assert component["version"] == "0.30.0"


def test_ignored_lines():
    for line in ("", "# comment", "-r other.txt", "--index-url https://example.org/simple", "pkg @ https://example.org/pkg.whl"):
        assert parse_python_requirement(line, "requirements.txt") is None, line


def test_requirements_file(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\nflask>=3\n# note\n")
    found = by_name(collect_components(str(tmp_path)))
    assert found["requests"]["pinned"] is True
    assert found["flask"]["pinned"] is False


def test_pyproject_dependencies(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["httpx==0.27.0", "rich>=13"]\n')
    found = by_name(collect_components(str(tmp_path)))
    assert found["httpx"]["version"] == "0.27.0"
    assert found["rich"]["pinned"] is False


def test_package_json_scopes_and_pinning(tmp_path):
    manifest = {"dependencies": {"left-pad": "1.3.0", "@scope/pkg": "^2.0.0"}, "devDependencies": {"jest": "29.7.0"}}
    (tmp_path / "package.json").write_text(json.dumps(manifest))
    found = by_name(collect_components(str(tmp_path)))
    assert found["left-pad"]["pinned"] is True
    assert found["@scope/pkg"]["pinned"] is False
    assert found["@scope/pkg"]["purl"] == "pkg:npm/%40scope/pkg"
    assert found["jest"]["scope"] == "optional"


def test_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.org/app\n\ngo 1.22\n\nrequire (\n\tgithub.com/pkg/errors v0.9.1\n)\n\nrequire golang.org/x/text v0.14.0\n"
    )
    found = by_name(collect_components(str(tmp_path)))
    assert found["github.com/pkg/errors"]["version"] == "v0.9.1"
    assert found["golang.org/x/text"]["ecosystem"] == "Go"


def test_invalid_manifests_do_not_crash(tmp_path):
    (tmp_path / "package.json").write_text("{broken")
    (tmp_path / "pyproject.toml").write_text("not = [valid")
    assert collect_components(str(tmp_path)) == []


def test_duplicates_collapsed(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["Requests>=2"]\n')
    assert len(collect_components(str(tmp_path))) == 1


def test_purl_underscore_and_case():
    assert purl_for("My_Pkg", "1.0", "PyPI") == "pkg:pypi/my-pkg@1.0"


def test_cyclonedx_structure(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\nflask>=3\n")
    components = collect_components(str(tmp_path))
    generated = datetime(2026, 10, 24, 8, 0, 0, tzinfo=timezone.utc)
    bom = build_cyclonedx("demo", generated, components, [{"id": "OSV-1", "ref": components[0]["purl"]}])
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["metadata"]["timestamp"] == "2026-10-24T08:00:00Z"
    assert bom["metadata"]["component"]["name"] == "demo"
    assert bom["serialNumber"].startswith("urn:uuid:")
    unpinned = next(item for item in bom["components"] if item["name"] == "flask")
    assert "version" not in unpinned
    assert unpinned["properties"][0]["value"] == ">=3"
    assert bom["vulnerabilities"][0]["affects"][0]["ref"] == components[0]["purl"]
    json.dumps(bom)
