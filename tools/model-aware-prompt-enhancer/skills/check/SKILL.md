---
description: Diagnose a prompt without changing it (ambiguity, conflicts, missing context, output format, injection risks, model-specific guidance). Use when the user asks to review, check or lint a prompt, or runs /prompt-enhancer:check.
argument-hint: "[--model <id>] <prompt text or path to a prompt file>"
---

Check this prompt and report problems without rewriting it: $ARGUMENTS

If the argument is a path to a file, read the file and use its contents. If it starts with `--model <id>`, pass that id as `model`. If the user names no model, leave `model` out: inside Claude Code the server defaults to the Claude profile.

Call the `analyze_prompt` tool from the `prompt-enhancer` MCP server. Report the findings grouped by severity (error, warning, info). For each one, give the rule id, the quoted evidence, and the suggested fix. Mention the source link for model-specific guidance. If there are no findings, say the prompt looks fine as written. Do not rewrite the prompt unless the user asks; point them to `/prompt-enhancer:enhance`.
