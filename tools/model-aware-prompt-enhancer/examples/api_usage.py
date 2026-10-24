"""Use the toolkit as a library. Run from the project folder after `pip install -e .`:

    python examples/api_usage.py
"""

from prompt_enhancer import analyze, enhance, enhance_messages

prompt = "Extract the company names and funding rounds from the article and return JSON.\n<article>Acme raised $5M in March 2026.</article>"

# 1. Diagnose without changing anything.
report = analyze(prompt, model="gemini-3-pro")
print(f"task={report.task_type} profile={report.model_profile} v{report.profile_version}")
for d in report.diagnostics:
    print(f"  {d.severity:<7} {d.rule_id}: {d.message}")

# 2. Enhance: automatic patches only (structure + restated constraints).
result = enhance(prompt, model="gemini-3-pro")
print("\nstatus:", result.status, "| pending:", result.pending)

# 3. Answer the questions the toolkit cannot answer for you, then look at the diff.
result = enhance(
    prompt,
    model="gemini-3-pro",
    answers={"PE302": "company (string), amount_usd (number)", "PE303": "use null"},
)
print(result.diff)
assert result.lock.ok  # every explicit requirement survived verbatim

# 4. Chat transcripts: only the latest user message is touched.
messages = [
    {"role": "system", "content": "You are a release-notes assistant."},
    {"role": "user", "content": "Draft release notes for v2.3. Only include user-facing changes and never list ticket numbers."},
]
new_messages, r = enhance_messages(messages, model="claude-sonnet-5")
assert new_messages[0] == messages[0]
print(new_messages[-1]["content"])
