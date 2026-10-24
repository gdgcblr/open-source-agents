# d3v-keyguard: Google ADK integration

## Install

```bash
pip install -e "tools/d3v-keyguard[adk]"   # pulls google-adk>=2.13
d3v-keyguard init                          # one-time; the user sets a passphrase
```

## Components of `KeyguardADK`

```python
from d3v_keyguard.adk import KeyguardADK
from d3v_keyguard.policy import Policy

kg = KeyguardADK(
    policy=Policy({"call_api": ["demo_*"], "deploy": ["deploy_token"]}),
    capture={"login": {"session_token": "demo_session"}},
)
```

| Member | Wire to | What it does |
| :--- | :--- | :--- |
| `kg.tools` | `Agent(tools=[..., *kg.tools])` | `vault_status`, `list_secrets`, `store_secret(name, description, overwrite=False)`, `unlock_vault(reason)`, `lock_vault`, `describe_secret(name)` (all async) |
| `kg.before_tool_callback` | `Agent(before_tool_callback=...)` | Finds `keyguard://<name>` handles in tool arguments, runs the before-tool guardrails ADK would skip for this call (see Notes), checks the policy and ADK tool confirmation, unlocks on demand, then **calls the tool itself** with a private copy of the arguments holding the real values, and returns the captured/scrubbed result. ADK's `args` dict keeps the handles. |
| `kg.after_tool_callback` | `Agent(after_tool_callback=...)` | For all other tool calls: seals the configured output fields into the vault and replaces them with handles. Scrubs echoed secret values from results of any type: dataclasses, sets, bytes, pydantic models and other objects are converted to JSON data first (non-dicts come back as `{"result": ...}`). Works on a copy; the tool's own object is never modified. Also scrubs `tool_context.actions.state_delta`. |
| `kg.on_tool_error_callback` | `Agent(on_tool_error_callback=...)` | Replaces an exception whose message contains a known value with a scrubbed error dict |
| `kg.before_model_callback` | `Agent(before_model_callback=...)` | Final redaction pass over the outbound LLM request (contents, function calls/responses, text blobs, code parts, system instruction). Model-authored content is checked, not redacted: the request's `role='model'` parts *and* every agent-authored session event (ADK re-presents other agents' turns as `role='user'` text). A stored value there means a model is guessing, so keyguard locks the vault and answers with a fixed notice instead of calling the model, for that session only (`kg.is_tripped(session_id)`). Tool-call names count as model-authored, and `AgentTool` results are checked the same way in `after_tool_callback`. `callbacks()` and the plugin use `kg.before_model_callback_async`, which runs it in a worker thread. |
| `kg.callbacks()` | `Agent(..., **kg.callbacks())` | All four callbacks above, wired correctly. To add your own `before_tool_callback` guardrail, use the list form `Agent(..., **{**kg.callbacks(), "before_tool_callback": [kg.before_tool_callback, guard]})`; passing a second `before_tool_callback=` next to `**kg.callbacks()` raises `TypeError`. |
| `kg.reset_guard(session_id=None)` | your code, after a human review | Lets a tripped session continue (`None` = all). The content that tripped the guard is replaced by a fixed notice in later requests (never an in-place `[REDACTED]`), so the same history does not trip again. In memory only: a restarted process that resumes the session needs it again. |
| `kg.plugin()` | `App(..., plugins=[kg.plugin(), ...])` | The same logic as a runner-wide ADK plugin. Covers every agent and sub-agent. Register it **first**. |

Wire **all four callbacks** (use `**kg.callbacks()`), or the plugin. Without `before_tool_callback`, your tools receive literal `keyguard://` strings. Without the others, secrets returned by tools can reach the model.

Notes:
- Callbacks only apply to the agent they are set on. For sub-agents, set them on every `LlmAgent`, or use `kg.plugin()`.
- `before_tool_callback` returns the tool's result itself, so ADK skips the remaining before-tool hooks for that call. keyguard therefore runs them itself, on the handle-only arguments, *before* it unlocks or injects: in agent mode the agent callbacks listed after keyguard's (`before_tool_callback=[kg.before_tool_callback, my_guard]`), in plugin mode every later plugin's `before_tool_callback` and all of the agent's `before_tool_callback`s (ADK reaches the agent through `tool_context`). A non-`None` result from one of them answers the call, and nothing is unlocked or injected. Argument guardrails such as URL allow-lists therefore work in both modes.
- Handles are refused for `AgentTool`/`NodeTool` (the value would enter another model's context) and for long-running tools.
- When keyguard changes a result (capture or scrub) it returns a copy, which makes ADK skip the remaining after-tool hooks; keyguard runs them on the scrubbed copy, so later plugins and agent `after_tool_callback`s still see the result. Register `kg.plugin()` before logging/tracing plugins, so captured tokens are replaced before those plugins see the result.
- An exception raised by a tool that received a secret is turned into a scrubbed error result, so `on_tool_error_callback` hooks (for example `ReflectAndRetryToolPlugin`) do not see it. After-tool hooks see the error dict.
- Policy rules match tool names only: any tool with that name in any agent, sub-agent or MCP toolset gets the same secrets. Use distinctive names for tools that receive secrets.
- Dialogs, Argon2id and file I/O run in a worker thread (`asyncio.to_thread`), so `adk web` keeps serving while a dialog is open.

## Full example

```python
import os
from google.adk.agents import Agent
from d3v_keyguard.adk import KeyguardADK
from d3v_keyguard.policy import Policy

API_BASE = "https://api.example.com"   # fixed in code, never chosen by the model

def call_api(path: str, api_key: str) -> dict:
    """Call the demo API at API_BASE. api_key must be a keyguard:// handle."""
    ...  # receives the real key here, after substitution; sends it only to API_BASE + path

def login(username: str, password: str) -> dict:
    """Log in; returns {'session_token': ...}."""
    ...

kg = KeyguardADK(
    policy=Policy({"call_api": ["demo_*"], "login": ["demo_password"]}),
    capture={"login": {"session_token": "demo_session"}},
)

root_agent = Agent(
    name="demo",
    model=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
    instruction=(
        "Credentials are referenced only as keyguard://<name> handles. "
        "Never ask the user to type secrets or passphrases in chat; use store_secret, and just pass handles (the call unlocks on demand)."
    ),
    tools=[call_api, login, *kg.tools],
    **kg.callbacks(),
)
```

If you also use a `call_api` with a `session` argument, allow it: `Policy({"call_api": ["demo_*"]})` already covers `demo_session`.

## Policy

- **Deny by default**: a tool receives a secret only if the tool name maps to a matching pattern. Patterns are glob-style (`prod_*`, `*_token`, exact names).
- Denied substitutions raise a policy error to the model instead of calling the tool with a value.
- Load from a file with `KEYGUARD_POLICY_FILE=/path/policy.json`:
  ```json
  { "call_api": ["prod_*", "demo_*"], "login": ["demo_password"] }
  ```
- The policy is per tool, not per argument. Keep policies narrow, and fix destinations inside the tool (as `API_BASE` above). Do not give generic tools such as `http_get` or `run_shell` any secret, because the model chooses the URL or command, and a prompt injection can redirect it.
- The unlock dialog shows the tool name, the secrets and every (handle-only) argument on its own line, destination-like names (`url`, `host`, `endpoint`, `cmd`, `path`...) first. Long values keep head and tail with a `[... N chars hidden - do not approve unless you expected this ...]` marker; nothing is cut silently. Once the vault is unlocked, later calls do not prompt again.
- `exec:<command>` keys restrict `d3v-keyguard exec` (deny-by-default once any `exec:` key exists), e.g. `{"exec:gh": ["github_token"]}`. A bare-name key only covers programs found on `PATH` (never the current directory); a program run by path needs its full path as the key.

## Capture

`capture={tool_name: {output_field: secret_name}}`

- After `tool_name` returns, the top-level field `output_field` is sealed into the vault as `secret_name` (replacing an earlier capture), and the result the model sees contains `keyguard://secret_name` in its place. Nested fields are not captured; return the token at the top level.
- Captured while unlocked: active immediately. Captured while locked: pending, and shown at the next unlock as "captured from tool '<tool_name>'". A pending capture never disables the active value it would replace.
- Any known secret value echoed elsewhere in a tool result is scrubbed.

## LLM-supplied values

`store_secret` only declares a `value` parameter when `KEYGUARD_ALLOW_LLM_VALUES=1` is set when `KeyguardADK` is created. The value has then passed through the model provider and the transcript, so the tool returns a warning to rotate the secret, and the entry gets the metadata `exposed_to_model: true` (so a later process does not count that value in old history as a guess). Keep this off. With it off, a `value` the model passes anyway is refused in `before_tool_callback` and remembered as exposed, so it is still scrubbed.

## Unlock flow inside ADK

1. A callback needs a secret while the vault is locked (the normal case), or the model calls `unlock_vault(reason="...")` because the user asked to unlock in advance. If the vault cannot be unlocked (no vault, locked out, backoff), no dialog opens and the tool gets the error instead.
2. A masked tkinter passphrase dialog opens in an isolated subprocess (`KEYGUARD_PROMPT=auto|gui|tty`, honoured by the CLI too). The hidden terminal prompt is used only if no GUI is available; clicking Cancel is final. The dialog shows the requester, the secrets and the arguments; an agent-supplied reason is labeled as unverified. After an `unlock_vault` unlock, which shows no tool or arguments, the first secret use opens a confirm dialog with the tool, the secrets and the arguments.
3. Each pending entry is shown with a masked preview, its creation time, its source (marked unverified) and a REPLACES warning that says whether the value differs from the current one; the user approves, rejects or defers each one. Approval endorses only the exact content reviewed (HMAC endorsement tag).
4. If another process runs `change-pin` meanwhile, this process locks itself on its next vault access and the next secret use asks for the new passphrase.
5. Keys stay in the agent process memory until idle timeout (`KEYGUARD_IDLE_TIMEOUT`, 300 s), maximum session length (`KEYGUARD_MAX_SESSION`, 3600 s) or `lock_vault()`. A timer wipes them at the deadline. Redaction knowledge is kept after a lock, so history stays scrubbed.

The dialog runs in a worker thread, so the event loop (and `adk web`) keeps running while it is open.

## Telemetry and logging plugins

ADK passes the same `args` dict to plugins, `on_tool_error` callbacks and the `execute_tool` span (`gcp.vertex.agent.tool_call_args` / `gen_ai.tool.call.arguments` when content capture is on). Because keyguard calls the tool with a private copy, that dict only ever holds handles. Exceptions raised by a tool that received secrets are converted to a scrubbed error dict, so they are not re-raised, recorded on the span or persisted with the value. Plugin after-tool hooks run before agent callbacks: if a logging plugin must see results of capture tools (such as `login`), use `kg.plugin()` registered first.

## Non-ADK Python code

```python
from d3v_keyguard import Vault
from d3v_keyguard.prompt import default_prompt

vault = Vault()
vault.unlock(default_prompt().ask_secret("d3v-keyguard", "Vault passphrase:"))
secret = vault.get("demo_api_key")   # SecretValue
print(secret)                        # masked
requests.get(url, headers={"Authorization": f"Bearer {secret.reveal()}"})
```

Call `.reveal()` only at the point of use, and never log its result.

## Running the demo

```bash
d3v-keyguard add demo_api --description "demo API key"      # any test value
d3v-keyguard add google_api_key --description "Gemini API key"
cd tools/d3v-keyguard/examples
d3v-keyguard exec --env GOOGLE_API_KEY=keyguard://google_api_key -- adk web   # or: ... -- adk run adk_demo_agent
```
(A plaintext `examples/adk_demo_agent/.env` with `GOOGLE_API_KEY=...` and `MODEL_NAME=...` also works.)

Status: the demo has not been live-tested against a model yet. The unit tests (`pytest tests`) cover the callbacks offline with a fake keyring and fake prompts.

## Troubleshooting

| Symptom | Cause / fix |
| :--- | :--- |
| Tool receives the literal `keyguard://x` | `before_tool_callback` is not wired |
| Policy denied | Add a `tool -> pattern` rule for that tool |
| Secret pending | The user approves it at the next unlock (or with `d3v-keyguard approve`) |
| "already exists" from `store_secret` | Ask the user; call again with `overwrite=True` only if they want to replace it |
| Tamper detected / rollback detected | The vault file was edited, replaced by an old copy, or is corrupted. Stop and tell the user. |
| Vault is busy | Another d3v-keyguard process holds the vault lock; retry shortly |
| Locked out | A human runs `d3v-keyguard reset-lockout` at a terminal |
| Insecure keyring backend | Install or enable a real OS keyring (Secret Service on Linux) |
| No dialog appears | tkinter is missing or there is no display; set `KEYGUARD_PROMPT=tty` |
| Tool receives the handle inside an agent tool | Handles are refused for `AgentTool`/`NodeTool` by design |
| "d3v-keyguard stopped this session: the model's own output contained the value of a stored secret" | A model (this agent, a sub-agent or an `AgentTool`) wrote a stored value (guessing / prompt injection). The vault is locked (for the whole process) and every further turn of *that session* is refused; other sessions keep working and ask for the passphrase on their next secret use. Review the conversation, rotate the secret if needed, then start a new session or call `kg.reset_guard(session_id)`. Restarting the process does not help for a persisted session: its history is checked again after the first unlock. Values under 12 characters only match as whole words; a secret whose value is a common word, or a value the user pasted into the chat and the model echoed before it was stored, can still trigger this. |
| "vault keys changed in another process" | Someone ran `change-pin` (or re-created the vault) elsewhere; unlock again with the new passphrase |
