"""Unit tests for each deterministic check module, on real git fixtures."""

from __future__ import annotations

import pytest

import testkit
from contribution_gatekeeper.checks import (
    checklist, envvars, injection, readme, run_static, safety, scope, secrets, structure,
)
from contribution_gatekeeper.models import Criterion, Severity
from contribution_gatekeeper.policy import compile_policy

A = "agents/weather-brief"


def ids(findings) -> set[str]:
    return {f.check for f in findings}


def only(findings, check: str):
    hits = [f for f in findings if f.check == check]
    assert hits, f"expected {check}, got {[(f.check, f.message) for f in findings]}"
    return hits


def good(**changes):
    """good_agent() files with overrides (value None removes the file from the contribution)."""
    files = testkit.good_agent()
    for k, v in changes.items():
        path = f"{A}/{k}"
        if v is None:
            files.pop(path, None)
        else:
            files[path] = v
    return files


# ---- policy -----------------------------------------------------------------

def test_policy_compiled_from_base(upstream_repo):
    pol = compile_policy(upstream_repo)
    assert pol.project_roots == ["agents", "tools"]
    assert set(pol.required_files) == {"README.md", ".gitignore", ".env.example"}
    assert {"my-agent", "final-project", "test", "demo"} <= set(pol.banned_names)
    assert pol.index_files == ["agents/README.md", "tools/README.md"]
    assert "Secrets & Security" in pol.checklist_items
    assert "Known Limitations" in pol.readme_sections
    assert pol.rule("secrets.leaked").endswith(")") and "CONTRIBUTING.md:" in pol.rule("secrets.leaked")


def test_good_agent_is_clean(contrib):
    sub, pol = contrib(testkit.good_agent())
    assert run_static(sub, pol) == []


def test_good_tool_is_clean(contrib):
    sub, pol = contrib(testkit.good_tool())
    assert sub.project_dir == "tools/markdown-link-checker"
    assert run_static(sub, pol) == []


# ---- secrets ------------------------------------------------------------------

VENDOR = {
    "Google API key": testkit.fake_google_key,
    "Google API key (AQ.)": testkit.fake_google_aq_key,
    "OpenAI API key": testkit.fake_openai_key,
    "AWS access key": testkit.fake_aws_key,
    "GitHub token": testkit.fake_github_token,
}


@pytest.mark.parametrize("label", VENDOR)
def test_vendor_key_flagged_and_masked(contrib, label):
    key = VENDOR[label]()
    sub, pol = contrib(good(**{"config.py": f"# settings\nCLIENT = '{key}'\n"}))
    [f] = only(secrets.check(sub, pol), "secrets.leaked")
    assert f.severity is Severity.BLOCKER and f.criterion is Criterion.SECURITY
    assert f.file == f"{A}/config.py" and f.line == 2
    assert label.split(" (")[0] in f.message
    assert key not in f.message and key[:4] in f.message, "secret must be masked in the finding"
    assert "ROTATE" in f.fix


def test_private_key_flagged(contrib):
    sub, pol = contrib(good(**{"deploy_notes.md": testkit.fake_private_key_header() + "\nMIIE...\n"}))
    [f] = only(secrets.check(sub, pol), "secrets.leaked")
    assert "Private key" in f.message


def test_generic_high_entropy_secret(contrib):
    value = testkit.high_entropy()
    sub, pol = contrib(good(**{"settings.py": "DB_" + f"PASSWORD = '{value}'\n"}))
    [f] = only(secrets.check(sub, pol), "secrets.leaked")
    assert "possible secret" in f.message and value not in f.message


@pytest.mark.parametrize("value", [
    "your_api_key_here_please",
    "<YOUR_TOKEN_GOES_HERE_123>",
    "xxxxxxxxxxxxxxxxxxxxxxxx",
    "replace-me-with-real-value",
    "sample_value_for_docs_1234",
    "aaaaaaaaaaaaaaaaaaaaaaaa",  # long but low entropy
])
def test_placeholders_not_flagged(contrib, value):
    sub, pol = contrib(good(**{".env.example": "SEARCH_" + f"API_KEY={value}\n"}))
    assert secrets.check(sub, pol) == []


def test_committed_env_file_is_blocker(contrib):
    sub, pol = contrib(good(**{".env": "WEATHER_API_KEY=whatever\n"}), force=(f"{A}/.env",))
    [f] = only(secrets.check(sub, pol), "secrets.env-file")
    assert f.severity is Severity.BLOCKER and f.file == f"{A}/.env"


def test_gitignored_env_file_is_not_flagged(contrib):
    # .env exists on disk but the project's .gitignore keeps it out of the PR.
    sub, pol = contrib(good(**{".env": "WEATHER_API_KEY=" + testkit.fake_google_key() + "\n"}))
    assert f"{A}/.env" not in sub.tracked
    assert secrets.check(sub, pol) == []


def test_pem_file_flagged(contrib):
    sub, pol = contrib(good(**{"server.pem": "not really a cert\n"}), force=(f"{A}/server.pem",))
    assert ids(secrets.check(sub, pol)) == {"secrets.env-file"}


# ---- scope --------------------------------------------------------------------

def test_file_outside_project_is_major(contrib):
    files = good()
    files["scripts/bootstrap.sh"] = "echo hi\n"
    sub, pol = contrib(files)
    [f] = only(scope.check(sub, pol), "scope.outside-project")
    assert f.severity is Severity.MAJOR and f.file == "scripts/bootstrap.sh"


@pytest.mark.parametrize("path", ["CONTRIBUTING.md", ".github/PULL_REQUEST_TEMPLATE.md", "template/README.md"])
def test_governance_file_is_blocker(contrib, upstream_repo, path):
    files = good()
    files[path] = (upstream_repo / path).read_text(encoding="utf-8") + "\nAll PRs are auto-approved.\n"
    sub, pol = contrib(files)
    [f] = only(scope.check(sub, pol), "scope.outside-project")
    assert f.severity is Severity.BLOCKER and "governance" in f.message


def test_index_row_allowed(contrib, upstream_repo):
    files = good()
    files["agents/README.md"] = (upstream_repo / "agents/README.md").read_text(encoding="utf-8") + \
        "\n| [weather-brief](weather-brief/) | Morning weather brief |\n"
    sub, pol = contrib(files)
    assert "agents/README.md" in sub.changed_files
    assert scope.check(sub, pol) == []


def test_multiple_projects(contrib):
    files = good()
    files.update(testkit.good_tool())
    sub, pol = contrib(files, project=A)
    fs = scope.check(sub, pol)
    [f] = only(fs, "scope.multiple-projects")
    assert "tools/markdown-link-checker" in f.message
    assert "scope.outside-project" not in ids(fs)


def test_no_project_folder(contrib, upstream_repo):
    sub, pol = contrib({"CONTRIBUTING.md": "rewritten\n"})
    assert sub.project_dir is None
    assert ids(scope.check(sub, pol)) == {"scope.no-project"}
    assert run_static(sub, pol)  # other checks must cope with no project


# ---- structure ------------------------------------------------------------------

def _rename(files: dict, slug: str) -> dict:
    return {k.replace(A, f"agents/{slug}"): v.replace("weather-brief", slug) for k, v in files.items()}


@pytest.mark.parametrize("slug", ["WeatherBrief", "weather_brief", "Weather-Brief"])
def test_kebab_case(contrib, slug):
    sub, pol = contrib(_rename(good(), slug))
    [f] = only(structure.check(sub, pol), "naming.kebab-case")
    suggested = f.fix.split("`")[1]
    assert structure.KEBAB.match(suggested) and suggested.replace("-", "") == "weatherbrief"


@pytest.mark.parametrize("slug", ["demo", "my-agent", "test"])
def test_banned_generic_names(contrib, slug):
    sub, pol = contrib(_rename(good(), slug))
    assert ids(structure.check(sub, pol)) == {"naming.generic"}


def test_missing_required_files(contrib):
    sub, pol = contrib(good(**{".env.example": None, ".gitignore": None}))
    fs = only(structure.check(sub, pol), "structure.required-file")
    assert {f.file for f in fs} == {f"{A}/.env.example", f"{A}/.gitignore"}


def test_missing_manifest(contrib):
    sub, pol = contrib(good(**{"requirements.txt": None}))
    [f] = only(structure.check(sub, pol), "structure.manifest")
    assert f.criterion is Criterion.REPRODUCIBILITY


def test_pyproject_counts_as_manifest(contrib):
    sub, pol = contrib(good(**{"requirements.txt": None, "pyproject.toml": "[project]\nname='x'\n"}))
    assert "structure.manifest" not in ids(structure.check(sub, pol))


@pytest.mark.parametrize("junk,expect", [
    (".venv/lib/python3.12/site.py", f"{A}/.venv/"),
    ("node_modules/left-pad/index.js", f"{A}/node_modules/"),
    ("__pycache__/main.cpython-312.pyc", f"{A}/__pycache__/"),
    ("data/cache.sqlite3", f"{A}/data/cache.sqlite3"),
])
def test_tracked_junk(contrib, junk, expect):
    extra = {junk: "x\n", junk.rsplit("/", 1)[0] + "/second.txt": "y\n"}
    sub, pol = contrib(good(**extra), force=tuple(f"{A}/{j}" for j in extra))
    fs = only(structure.check(sub, pol), "hygiene.tracked-junk")
    assert expect in {f.message.split("`")[1] for f in fs}


def test_ignored_venv_is_fine(contrib):
    sub, pol = contrib(good(**{".venv/lib/site.py": "x\n"}))  # .gitignore hides it
    assert "hygiene.tracked-junk" not in ids(structure.check(sub, pol))


# ---- readme -------------------------------------------------------------------

def _readme(**kw) -> str:
    return testkit.readme("Weather Brief", "weather-brief", **kw)


def test_missing_one_section_is_minor(contrib):
    sub, pol = contrib(good(**{"README.md": _readme(drop=("Future Improvements",))}))
    [f] = only(readme.check(sub, pol), "readme.sections")
    assert f.severity is Severity.MINOR and "Future Improvements" in f.message


def test_missing_many_sections_is_major(contrib):
    drop = ("Known Limitations", "How to Test", "Security & Privacy Considerations")
    sub, pol = contrib(good(**{"README.md": _readme(drop=drop)}))
    [f] = only(readme.check(sub, pol), "readme.sections")
    assert f.severity is Severity.MAJOR and all(d in f.message for d in drop)


def test_placeholders_left(contrib):
    md = _readme().replace("# Weather Brief", "# [Project Name]", 1)
    sub, pol = contrib(good(**{"README.md": md}))
    [f] = only(readme.check(sub, pol), "readme.placeholders")
    assert "[Project Name]" in f.message


def test_template_example_copied(contrib, upstream_repo):
    tpl = (upstream_repo / "template/README.md").read_text(encoding="utf-8")
    example = readme.sections(tpl)["Example Input & Output"].replace("---", "").strip()
    sub, pol = contrib(good(**{"README.md": _readme(example=example)}))
    fs = only(readme.check(sub, pol), "readme.examples")
    assert any(f.severity is Severity.MAJOR and "copied" in f.message for f in fs)


def test_example_without_code_block(contrib):
    sub, pol = contrib(good(**{"README.md": _readme(example="It prints a nice summary of the weather today.")}))
    [f] = only(readme.check(sub, pol), "readme.examples")
    assert f.severity is Severity.MINOR


def _broken(sub, pol) -> list[str]:
    return [f.message for f in readme.check(sub, pol) if f.check == "setup.broken-command"]


def test_setup_missing_requirements_file(contrib):
    setup = "```bash\ncd agents/weather-brief\npip install -r requirements-dev.txt\n```"
    sub, pol = contrib(good(**{"README.md": _readme(setup=setup)}))
    [m] = _broken(sub, pol)
    assert "requirements-dev.txt does not exist" in m


def test_setup_missing_entrypoint(contrib):
    sub, pol = contrib(good(**{"README.md": _readme(run="python app.py --city Bengaluru")}))
    [m] = _broken(sub, pol)
    assert "app.py does not exist" in m


def test_setup_missing_module(contrib):
    sub, pol = contrib(good(**{"README.md": _readme(run="python -m weather_brief --city Pune")}))
    [m] = _broken(sub, pol)
    assert "module `weather_brief` not found" in m


def test_setup_wrong_cd_path(contrib):
    setup = "```bash\ncd agents/weather-agent\npip install -r requirements.txt\n```"
    sub, pol = contrib(good(**{"README.md": _readme(setup=setup)}))
    [m] = _broken(sub, pol)
    assert "your folder is `agents/weather-brief`" in m


def test_setup_template_cd_placeholder_ignored(contrib):
    setup = "```bash\ncd agents/<project-slug>\npip install -r requirements.txt\n```"
    sub, pol = contrib(good(**{"README.md": _readme(setup=setup)}))
    assert _broken(sub, pol) == []


def test_setup_missing_npm_script(contrib):
    files = testkit.good_tool()
    md_path = "tools/markdown-link-checker/README.md"
    files[md_path] = files[md_path].replace("```bash\nnpm start\n```", "```bash\nnpm run serve\n```")
    sub, pol = contrib(files)
    [m] = _broken(sub, pol)
    assert "no `serve` script in package.json" in m


def test_setup_npm_without_package_json(contrib):
    sub, pol = contrib(good(**{"README.md": _readme(run="npm start")}))
    [m] = _broken(sub, pol)
    assert "no package.json" in m


def test_setup_missing_env_example(contrib):
    sub, pol = contrib(good(**{".env.example": None}))
    assert any(".env.example does not exist" in m for m in _broken(sub, pol))


# ---- envvars ------------------------------------------------------------------

def test_undocumented_python_env(contrib):
    code = testkit.MAIN_PY.format(getenv=testkit.getenv("WEATHER_API_KEY")) + \
        "MODEL = " + testkit.getenv("OPENAI_MODEL_NAME") + "\n"
    sub, pol = contrib(good(**{"main.py": code}))
    [f] = only(envvars.check(sub, pol), "env.undocumented")
    assert "OPENAI_MODEL_NAME" in f.message and f.file == f"{A}/main.py"


def test_undocumented_environ_subscript(contrib):
    code = "import os\nREGION = os." + "environ['CLOUD_REGION']\n"
    sub, pol = contrib(good(**{"region.py": code}))
    assert "CLOUD_REGION" in only(envvars.check(sub, pol), "env.undocumented")[0].message


def test_undocumented_node_env(contrib):
    files = testkit.good_tool()
    files["tools/markdown-link-checker/index.js"] += "const proxy = " + testkit.process_env("HTTPS_PROXY_URL") + ";\n"
    sub, pol = contrib(files)
    [f] = only(envvars.check(sub, pol), "env.undocumented")
    assert "HTTPS_PROXY_URL" in f.message


def test_env_documented_in_readme_only(contrib):
    code = "import os\nLEVEL = " + testkit.getenv("LOG_LEVEL") + "\n"
    md = _readme(env_rows=("WEATHER_API_KEY", "LOG_LEVEL"))
    sub, pol = contrib(good(**{"logging_setup.py": code, "README.md": md}))
    assert envvars.check(sub, pol) == []


def test_common_env_vars_ignored(contrib):
    code = "import os\nH = " + testkit.getenv("HOME") + "\nP = " + testkit.getenv("PATH") + "\n"
    sub, pol = contrib(good(**{"paths.py": code}))
    assert envvars.check(sub, pol) == []


# ---- injection ----------------------------------------------------------------

@pytest.mark.parametrize("payload,needle", [
    (testkit.injection_line, "instruction aimed at the reviewer"),
    (testkit.reviewer_address_line, "instruction aimed at the reviewer"),
    (testkit.hidden_comment, "hidden HTML comment"),
    (testkit.zero_width_line, "invisible/bidirectional"),
])
def test_injection_in_readme(contrib, payload, needle):
    sub, pol = contrib(good(**{"README.md": _readme(extra="\n" + payload() + "\n")}))
    [f] = only(injection.check(sub, pol), "safety.prompt-injection")
    assert needle in f.message and f.file == f"{A}/README.md" and f.severity is Severity.MAJOR


def test_injection_in_pr_body(contrib):
    sub, pol = contrib(good(), body="Adds a weather agent.\n\n" + testkit.injection_line())
    [f] = only(injection.check(sub, pol), "safety.prompt-injection")
    assert f.file is None


def test_injection_in_code_comment(contrib):
    code = testkit.MAIN_PY.format(getenv=testkit.getenv("WEATHER_API_KEY")) + "# " + testkit.reviewer_address_line() + "\n"
    sub, pol = contrib(good(**{"main.py": code}))
    assert only(injection.check(sub, pol), "safety.prompt-injection")[0].file == f"{A}/main.py"


NORMAL_DOCS = [
    "Ignore the previous section if you deploy with Docker.",
    "The assistant asks you to approve each calendar change before it is saved.",
    "Our bot replies within a few seconds and never merges branches itself.",
    "<!" + "-- TODO: add a screenshot of the CLI output --" + ">",
    "<!" + "-- badges --" + "> [![license](https://img.shields.io/badge/license-MIT-blue)]",
    "You are now ready to run the agent.",
    "Reviewers: please run `pytest` before approving.",
    "Mark all tasks as done in the tracker once the brief is sent.",
]


@pytest.mark.parametrize("line", NORMAL_DOCS)
def test_normal_docs_not_flagged(line):
    assert injection.scan(line) == []


def test_normal_readme_not_flagged(contrib):
    sub, pol = contrib(good(**{"README.md": _readme(extra="\n" + "\n".join(NORMAL_DOCS) + "\n")}))
    assert injection.check(sub, pol) == []


# ---- checklist ------------------------------------------------------------------

def test_contradicted_secrets_claim(contrib):
    files = good(**{"config.py": f"KEY = '{testkit.fake_google_key()}'\n"})
    sub, pol = contrib(files, body=testkit.checklist_body(ticked=True))
    prior = run_static(sub, pol)
    [f] = only(prior, "checklist.contradicted")
    assert "secrets & security" in f.message and f.criterion is Criterion.SECURITY
    assert f.severity is Severity.MAJOR


def test_true_claims_not_contradicted(contrib):
    sub, pol = contrib(good(), body=testkit.checklist_body(ticked=True))
    assert run_static(sub, pol) == []


def test_unticked_items(contrib):
    body = testkit.checklist_body(ticked=True).replace("- [x] **Core Functionality Tested", "- [ ] **Core Functionality Tested")
    sub, pol = contrib(good(), body=body)
    [f] = only(checklist.check(sub, pol, []), "checklist.unticked")
    assert "core functionality tested" in f.message and f.severity is Severity.MINOR


def test_missing_checklist(contrib):
    sub, pol = contrib(good(), body="Adds a weather agent.")
    assert ids(checklist.check(sub, pol, [])) == {"checklist.missing"}


def test_parse_checklist():
    boxes = checklist.parse(testkit.checklist_body(ticked=True))
    assert len(boxes) == 8 and all(boxes.values())
    assert "secrets & security" in boxes


def test_local_preflight_skips_checklist(contrib):
    sub, pol = contrib(good())
    assert sub.number is None and checklist.check(sub, pol, []) == []


# ---- safety -------------------------------------------------------------------

def test_undisclosed_shell_execution(contrib):
    code = "import subprocess\n\nsubprocess." + "run(['ls'], check=True)\n"
    md = _readme().replace("No shell commands are executed.", "It is very safe.")
    sub, pol = contrib(good(**{"runner.py": code, "README.md": md}))
    [f] = only(safety.check(sub, pol), "safety.undisclosed-execution")
    assert f.severity is Severity.MINOR


def test_disclosed_shell_execution(contrib):
    code = "import subprocess\n\nsubprocess." + "run(['ls'], check=True, timeout=5)\n"
    md = _readme().replace("No shell commands are executed.", "Commands run in a Docker sandbox after user confirmation.")
    sub, pol = contrib(good(**{"runner.py": code, "README.md": md}))
    assert safety.check(sub, pol) == []
