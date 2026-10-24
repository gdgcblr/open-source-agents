from dead_code_reaper.ai import Anthropic, OpenAICompatible, annotate, detect_provider, parse_response
from dead_code_reaper.analyzer import scan


def test_parse_response_tolerates_fences_and_prose():
    text = 'Sure:\n```json\n[{"number": 1, "note": "old helper", "risk": null},' \
           ' {"number": 2, "note": "hook", "risk": "pytest calls it by name"}]\n```'
    assert parse_response(text) == {1: ("old helper", None), 2: ("hook", "pytest calls it by name")}
    assert parse_response("no json here") == {}


def test_detect_provider_order_and_opt_out():
    assert detect_provider({}) is None
    g = detect_provider({"GEMINI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"})
    assert isinstance(g, OpenAICompatible) and g.name == "gemini"
    a = detect_provider({"GEMINI_API_KEY": "x", "ANTHROPIC_API_KEY": "y", "REAPER_AI_PROVIDER": "anthropic"})
    assert isinstance(a, Anthropic)
    o = detect_provider({"OPENAI_BASE_URL": "http://localhost:11434/v1", "REAPER_MODEL": "llama3"})
    assert o.name == "openai" and o.model == "llama3"


class StubProvider:
    name, model = "stub", "stub-1"

    def __init__(self):
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        return '[{"number": 1, "note": "unused helper", "risk": null},' \
               ' {"number": 2, "note": "pytest hook", "risk": "loaded by pytest by name"}]'


def test_annotate_sets_notes_and_risk(make_project):
    root = make_project({"mod.py": "def old():\n    pass\n\n\ndef pytest_configure(config):\n    pass\n"})
    s = scan(root)
    for i, r in enumerate(s.removals, 1):
        r.number, r.status = i, "verified"
    stub = StubProvider()
    assert annotate(s.removals, s, stub, log=lambda m: None) == 2
    assert "def old" in stub.prompts[0]
    hook = next(r for r in s.removals if "pytest_configure" in r.name)
    assert hook.risk and hook.default_keep
