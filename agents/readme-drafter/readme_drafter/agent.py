"""README Drafter: inspects a project folder and drafts its README with a local Gemma model."""

import json
import os

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .tools import extract_readme, inspect_project, list_project_files, read_file, save_readme_draft

MODEL_NAME = os.getenv("MODEL_NAME", "gemma4:e4b")
# Ollama's default context window is too small to hold several source files.
NUM_CTX = int(os.getenv("NUM_CTX", "32768"))

# Curly braces are ADK session-state placeholders; {project_context} is the only one used.
INSTRUCTION = """You are README Drafter. You write accurate README.md files for software projects
from what their files show. You never guess.

The project has already been inspected. The results are at the end of these instructions:
its stack, parsed manifests and the content of its most important files.

Work in this order:
1. Study the inspection results.
2. Only if something important is still unclear, call list_project_files and then read_file
   on up to 3 more files. Never read a file twice.
3. Reply with ONLY the README in Markdown. Start directly with the "# " title line. Do not write
   an introduction, notes about what you read, or anything after the README.
   Your reply is saved automatically as README.draft.md.

README sections, in this order:
# Project name
> One-sentence summary of what it does.
## Overview - the problem it solves, who it is for, key features as bullets.
## Technical Stack - language and runtime, frameworks, models, external services.
## Architecture & Data Flow - a short paragraph or a small text diagram.
## Prerequisites
## Installation & Setup - exact commands.
## Configuration & Environment Variables - a table with columns Variable, Required, Default, Description.
## How to Run - exact commands.
## Example Usage
## How to Test
## Known Limitations
## Security & Privacy Considerations
## License

Rules:
- Only state what the files show. Never invent features, commands, versions, URLs or example output.
  When something is unknown, write a line starting with "TODO:" that tells the author what to add.
- Describe the project from its source code. If an existing README is an unfilled template, never
  copy its placeholder text (such as "Feature 1: Brief description").
- Take commands from the manifests: package.json scripts, pyproject scripts, Makefile targets,
  the Dockerfile and docker-compose files. Write the standard command each manifest implies:
  pyproject.toml -> pip install . ; requirements.txt -> pip install -r requirements.txt ;
  package.json -> npm install and npm run <script> ; a pyproject script -> run it by its name ;
  nox sessions -> nox -s <session> ; docker-compose -> docker compose up.
- For the License section, use the "detected" license name and file from the inspection results
  in one line. If none was detected, write a TODO. Never paste license text.
- List environment variables by name only. Never copy keys, tokens or other secret values.
- Files like .env are deliberately unreadable. Describe them as files the user creates from .env.example.
- If the user asks for changes, reply with the complete updated README in the same way.

Inspection results (JSON):
{project_context}
"""


def inspect_before_run(callback_context: CallbackContext):
    """Inspects the project in code before each turn.

    Small models sometimes skip a required first tool call and write a placeholder
    README instead, so the inspection never depends on the model remembering it.
    """
    callback_context.state["project_context"] = json.dumps(inspect_project(), indent=1)
    return None


def save_readme_reply(callback_context: CallbackContext, llm_response: LlmResponse):
    """Saves the model's reply to README.draft.md whenever it contains a README."""
    content = llm_response.content
    if llm_response.partial or not content or not content.parts or llm_response.get_function_calls():
        return None
    readme = extract_readme("".join(part.text or "" for part in content.parts if not part.thought))
    if readme:
        saved = save_readme_draft(readme)
        content.parts = [
            types.Part(text=readme),
            types.Part(text=f"\n---\nSaved to `{saved['saved_to']}`"),
        ]
    return None


root_agent = Agent(
    name="readme_drafter",
    # Thinking off: with it on, gemma4:e4b sometimes imagines tool results instead of calling tools.
    # Retries cover the occasional malformed tool call that Ollama rejects.
    model=LiteLlm(
        model=f"ollama_chat/{MODEL_NAME}", num_ctx=NUM_CTX, reasoning_effort="none", num_retries=3
    ),
    description="Inspects a project folder and drafts a README.md for it.",
    instruction=INSTRUCTION,
    tools=[list_project_files, read_file],
    before_agent_callback=inspect_before_run,
    after_model_callback=save_readme_reply,
)
