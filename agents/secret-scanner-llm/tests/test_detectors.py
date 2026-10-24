import pytest

from secret_scanner.detectors import find_matches, is_high_entropy
from secret_scanner.scanner import scan_text

from . import helpers as H


def rules(line):
    return [m.rule.name for m in find_matches(line)]


@pytest.mark.parametrize("line,rule", [
    (f'key = "{H.aws()}"', "aws_access_key_id"),
    (f"export GH={H.github()}", "github_token"),
    (f"const s = '{H.stripe()}'", "stripe_live_key"),
    (f'k: "{H.google()}"', "google_api_key"),
    (f"SLACK={H.slack()}", "slack_token"),
    (H.pem_header(), "private_key_header"),
])
def test_known_formats_are_high_confidence(line, rule):
    ms = find_matches(line)
    assert ms and ms[0].rule.name == rule
    assert ms[0].rule.high_confidence_format


def test_github_fine_grained_pat():
    assert "github_fine_grained_pat" in rules("t=" + "github" + "_pat_" + "A1b2C3d4E5f6G7h8I9j0K1_" + "x" * 30)


def test_jwt_is_not_high_confidence():
    import base64
    b = lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
    jwt = b('{"alg":"HS256"}') + "." + b('{"sub":"admin","role":"x"}') + "." + "Sg3kLm92QxPz7"
    ms = find_matches(f'token_header = "{jwt}"')
    assert ms[0].rule.name == "jwt" and not ms[0].rule.high_confidence_format


def test_generic_assignments():
    assert rules(f'password = "{H.password()}"') == ["quoted_credential_assignment"]
    assert rules(f'{{"api_key": "{H.password()}"}}') == ["quoted_credential_assignment"]
    assert rules(f"DB_PASSWORD={H.password()}") == ["unquoted_credential_assignment"]
    assert rules(f"# temp admin password: {H.password()}") == ["unquoted_credential_assignment"]


def test_url_and_shell_passwords():
    assert rules(f'DATABASE_URL = "{H.db_url()}"') == ["url_credentials"]
    assert rules("mysqldump -u root -p" + H.password() + " db") == ["mysql_inline_password"]
    assert rules("sshpass -p " + H.password() + " ssh host") == ["sshpass"]
    assert rules("tool --password " + H.password()) == ["shell_password_flag"]
    assert rules("curl -u admin:" + H.password() + " https://x.example") == ["curl_basic_auth"]
    assert rules('curl -H "Authorization: Bearer ' + "Ab3dE6gH9jK2mN5pQ8" + '" x') == ["authorization_header"]


@pytest.mark.parametrize("line", [
    'API_KEY = os.getenv("STRIPE_API_KEY")',
    'password = os.environ["DB_PASSWORD"]',
    "export API_TOKEN=$MY_TOKEN",
    'secret = "{{ vault_secret }}"',
    'curl -u "$USER:$PASS" https://x.example',
    "max_tokens: 1024",
    "token: string",
    'password = ""',
    'request_id = "123e4567-e89b-12d3-a456-426614174000"',
    'curl -H "Authorization: Bearer $TOKEN" x',
    "mysql -u root -p db",
    'url = "https://example.com/path"',
])
def test_not_flagged(line):
    assert find_matches(line) == []


def test_entropy():
    assert is_high_entropy("Qm27xLpZk9vR4tQm27xLpZk9vR4t")
    assert is_high_entropy("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b")  # 40 hex chars
    assert not is_high_entropy("aaaaaaaaaaaaaaaaaaaaaaaa")
    assert not is_high_entropy("some-long-readable-package-name")
    assert not is_high_entropy("123e4567-e89b-12d3-a456-426614174000")
    ms = find_matches('V = "Qm27xLpZk9vR4tQm27xLpZk9vR4t"')
    assert ms[0].rule.name == "high_entropy_string"


def test_known_format_wins_over_generic_on_same_span():
    ms = find_matches(f'github_token = "{H.github()}"')
    assert len(ms) == 1 and ms[0].rule.name == "github_token"


def test_candidate_fields_and_test_path():
    c = scan_text("tests/test_x.py", f'password = "{H.password()}"\n')[0]
    assert c.in_test_path and c.line == 1 and c.kind == "credential_assignment"
    c2 = scan_text("src/x.py", f'k = "{H.aws()}"\n')[0]
    assert not c2.in_test_path and c2.high_confidence_format


def test_placeholder_hints():
    c = scan_text("a.py", 'password = "changeme-please"\n')[0]
    assert any("placeholder" in h for h in c.hints)
    c = scan_text("a.py", 'sha = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b"\n')[0]
    assert any("digest" in h for h in c.hints)


def test_inline_ignore():
    assert scan_text("a.py", f'k = "{H.aws()}"  # secretscan:ignore\n') == []
