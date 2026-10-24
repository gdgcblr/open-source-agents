---
description: Improve a prompt for a target model with minimal, intent-preserving patches and show the diff. Use when the user asks to improve, enhance, fix or tighten a prompt, or runs /prompt-enhancer:enhance.
argument-hint: "[--model <id>] <prompt text or path to a prompt file>"
---

Improve the prompt the user gave you: $ARGUMENTS

If the argument is a path to a file, read the file and use its contents as the prompt. If it starts with `--model <id>`, pass that id as `model`. If the user names no model, leave `model` out: inside Claude Code the server defaults to the Claude profile; otherwise use the model the user mentioned, or leave `model` out.

1. Call the `enhance_prompt` tool from the `prompt-enhancer` MCP server with the prompt (and model).
2. Show the user the diagnostics summary. By default the tool changes nothing until the user answers its questions or accepts patches; it never rewrites the user's wording.
3. If the result lists **questions for the user**, ask them those questions. Do not answer them yourself and do not guess; these are details only the user knows.
4. Offer any **opt-in patches** by id and say what each does. Structural patches (`S.wrap`, `S.constraints`, `S.reminder`) follow the vendor's documented formatting advice but showed no measured gain in the toolkit's live tests on Claude Haiku, so present them as optional. Apply a patch only if the user agrees.
5. Call `enhance_prompt` again with `answers` (keyed by patch id) and `accept` for the patches the user chose.
6. Show the final enhanced prompt in a code block and the requirement-lock status. If the lock failed or the status is `blocked`, say so and keep the original prompt.

Never claim the enhanced prompt will produce better answers: the tool checks structure and preserved requirements, not answer quality.
