"""Remediation guidance (static text; contains no scanned data)."""

from __future__ import annotations

COMMON_STEPS = [
    "Rotate/revoke the credential FIRST: assume it is compromised as soon as it was committed or shared.",
    "Move the value to an environment variable or secrets manager and read it at runtime.",
    "Document the variable name (not the value) in `.env.example`.",
    "Add the real `.env` / key files to `.gitignore`.",
    "If it was ever committed, remove it from history with `git filter-repo` "
    "(or BFG), force-push, and ask collaborators to re-clone. Rotation is still required: "
    "history rewrites do not un-leak a secret.",
]

_KIND_NOTES = {
    "aws_access_key": "Deactivate the key in IAM (Users > Security credentials), create a new one, and review CloudTrail for use of the old key. Prefer IAM roles / short-lived credentials.",
    "github_token": "Revoke it at GitHub > Settings > Developer settings > Tokens, issue a new fine-grained token with minimal scopes, and check the audit log.",
    "stripe_key": "Roll the key in the Stripe Dashboard (Developers > API keys), and review recent API activity. Use restricted keys where possible.",
    "google_api_key": "Delete or regenerate the key in Google Cloud Console and add API/application restrictions to the replacement.",
    "slack_token": "Revoke the token in the Slack app admin page (or via auth.revoke) and issue a new one.",
    "private_key": "Treat the key pair as compromised: generate a new pair, replace the public key everywhere it was authorised, and revoke the old one.",
    "jwt": "If the token is long-lived or signed with your production secret, revoke it and rotate the signing secret; prefer short-lived tokens.",
    "url_credentials": "Change the password of the user in the URL, then supply credentials via env vars (e.g. DATABASE_URL) not committed files.",
    "shell_password": "Change the password. Avoid passing secrets on the command line (they leak via shell history and `ps`); use env vars, a credentials file with 0600 perms, or a prompt.",
    "bearer_token": "Revoke the token with the issuing service and send the new one from an env var / secret store.",
    "credential_assignment": "Change the credential if it is real; load it from the environment instead of a literal.",
    "high_entropy_string": "Confirm what this string is. If it is a secret, rotate it and load it from the environment; if it is a hash/ID, add it to .secretscanignore or an inline `secretscan:ignore` comment.",
}


def known_kinds() -> list[str]:
    return sorted(_KIND_NOTES)


def guide_for(kind: str) -> dict:
    k = (kind or "").strip().lower()
    known = k in _KIND_NOTES
    return {
        "finding_kind": k,
        "recognised": known,
        "kind_specific": _KIND_NOTES.get(
            k, "Unrecognised kind: follow the general steps. Known kinds: " + ", ".join(known_kinds()) + "."
        ),
        "steps": list(COMMON_STEPS),
    }


def short_remediation(kind: str) -> str:
    return _KIND_NOTES.get(kind, "Rotate the credential and load it from the environment.")
