"""AI-native: how deeply and how well AI is built in (beyond a single prompt wrapper).

Places the submission on a maturity ladder with file:line evidence, then scores the engineering
around the model: robustness, portability, evals, observability and guardrails.
"""

from __future__ import annotations

import ast
import json
import re

from judge.analyzers import pyast
from judge.models import AnalyzerResult, Check
from judge.workspace import Workspace

DIM = "ai_native"
LEVELS = [
    "No AI detected",
    "Prompt wrapper",
    "Structured prompting",
    "Tool use",
    "Agent loop",
    "Multi-agent / RAG / MCP",
]

PY_PROVIDERS = [
    (
        (
            "google.generativeai",
            "google.genai",
            "vertexai",
            "langchain_google_genai",
            "langchain_google_vertexai",
            "google.adk",
        ),
        "Gemini",
    ),
    (("openai", "langchain_openai"), "OpenAI"),
    (("anthropic", "langchain_anthropic"), "Anthropic"),
    (("groq", "langchain_groq"), "Groq"),
    (("ollama", "langchain_ollama"), "Ollama"),
    (("mistralai", "langchain_mistralai"), "Mistral"),
    (("cohere",), "Cohere"),
    (("transformers", "huggingface_hub", "sentence_transformers"), "Hugging Face"),
    (("litellm",), "LiteLLM"),
    (("together",), "Together"),
]
JS_PROVIDERS = {
    "@google/genai": "Gemini",
    "@google/generative-ai": "Gemini",
    "openai": "OpenAI",
    "@anthropic-ai/sdk": "Anthropic",
    "groq-sdk": "Groq",
    "ollama": "Ollama",
    "@ai-sdk/google": "Gemini",
    "@ai-sdk/openai": "OpenAI",
    "@ai-sdk/anthropic": "Anthropic",
    "@mistralai/mistralai": "Mistral",
}
URL_PROVIDERS = [
    (re.compile(r"api\.groq\.com"), "Groq"),
    (re.compile(r"openrouter\.ai"), "OpenRouter"),
    (re.compile(r"localhost:11434|127\.0\.0\.1:11434"), "Ollama"),
    (re.compile(r"generativelanguage\.googleapis\.com"), "Gemini"),
    (re.compile(r"api\.anthropic\.com"), "Anthropic"),
    (re.compile(r"api\.openai\.com"), "OpenAI"),
]
GO_PROVIDERS = [
    (re.compile(r'"google\.golang\.org/genai"|"github\.com/google/generative-ai-go'), "Gemini"),
    (re.compile(r'"github\.com/(?:sashabaranov/go-openai|openai/openai-go)'), "OpenAI"),
    (re.compile(r'"github\.com/anthropics/anthropic-sdk-go'), "Anthropic"),
    (re.compile(r'"github\.com/ollama/ollama/api"'), "Ollama"),
]
GO_FRAMEWORKS = [
    (re.compile(r'"google\.golang\.org/adk'), "Google ADK"),
    (re.compile(r'"github\.com/tmc/langchaingo'), "LangChain"),
    (re.compile(r'"github\.com/firebase/genkit/go'), "Genkit"),
    (re.compile(r'"github\.com/(?:mark3labs/mcp-go|modelcontextprotocol/go-sdk)'), "MCP"),
]
PY_FRAMEWORKS = [
    (("google.adk",), "Google ADK"),
    (("langgraph",), "LangGraph"),
    (("langchain",), "LangChain"),
    (("crewai",), "CrewAI"),
    (("agents",), "OpenAI Agents SDK"),
    (("mcp", "fastmcp"), "MCP"),
    (("llama_index",), "LlamaIndex"),
    (("autogen", "autogen_agentchat"), "AutoGen"),
    (("semantic_kernel",), "Semantic Kernel"),
    (("pydantic_ai",), "PydanticAI"),
    (("dspy",), "DSPy"),
    (("smolagents",), "smolagents"),
    (("haystack",), "Haystack"),
    (("genkit",), "Genkit"),
    (("fastapi",), "FastAPI"),
    (("flask",), "Flask"),
    (("streamlit",), "Streamlit"),
    (("gradio",), "Gradio"),
    (("chainlit",), "Chainlit"),
    (("typer", "click"), "CLI"),
]
JS_FRAMEWORKS = {
    "@modelcontextprotocol/sdk": "MCP",
    "langchain": "LangChain",
    "@langchain/core": "LangChain",
    "@langchain/langgraph": "LangGraph",
    "ai": "Vercel AI SDK",
    "@openai/agents": "OpenAI Agents SDK",
    "@google/adk": "Google ADK",
    "genkit": "Genkit",
    "@genkit-ai/ai": "Genkit",
    "@genkit-ai/core": "Genkit",
    "react": "React",
    "next": "Next.js",
    "express": "Express",
    "vue": "Vue",
}
AI_FRAMEWORKS = {
    "Google ADK",
    "LangGraph",
    "LangChain",
    "CrewAI",
    "OpenAI Agents SDK",
    "MCP",
    "LlamaIndex",
    "AutoGen",
    "Semantic Kernel",
    "PydanticAI",
    "DSPy",
    "smolagents",
    "Haystack",
    "Vercel AI SDK",
    "Genkit",
}


AI_TERMS = re.compile(
    r"(?i)\b(?:llms?|prompts?|model context protocol|mcp|tokens?|embeddings?|rag|evals?|"
    r"agents?|gemini|claude|openai|gpt|tool[- ]calls?|function[- ]calling|hallucinat\w*)\b"
)


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p)


SIGNALS: dict[str, re.Pattern[str]] = {
    "structured": _rx(
        r"response_format|response_mime_type|response_schema|json_schema|with_structured_output|"
        r"output_schema|output_type\s*=|structured_output|generationConfig.*responseMimeType"
    ),
    "system_prompt": _rx(
        r"system_instruction|['\"]role['\"]\s*:\s*['\"]system['\"]|role\s*=\s*['\"]system|"
        r"SystemMessage|\binstruction\s*=|system_prompt|SYSTEM_PROMPT|systemInstruction"
    ),
    "tools": _rx(
        r"\btools\s*=|['\"]tools['\"]\s*:|function_declarations|FunctionDeclaration|@tool\b|bind_tools|FunctionTool|tool_choice|"
        r"tool_calls|function_call|@function_tool|@mcp\.tool|\bTool\(|functionDeclarations|tools\s*:|functiontool\.New|defineTool"
    ),
    "agent": _rx(
        r"\b(?:Llm)?Agent\s*\(|StateGraph\s*\(|\bCrew\s*\(|create_react_agent|AgentExecutor|Runner\.run|"
        r"CodeAgent\s*\(|ToolCallingAgent\s*\(|create_tool_calling_agent|ReActAgent|llmagent\.New|runner\.New"
    ),
    "loop_tools": _rx(r"tool_calls|function_call|functionCall"),
    "memory": _rx(
        r"(?i)conversation_history|chat_history|messages\.append|history\.append|SessionService|"
        r"ConversationBuffer|checkpointer|MemorySaver|\bmemory\s*="
    ),
    "multi_agent": _rx(r"sub_agents|SequentialAgent|ParallelAgent|LoopAgent|GroupChat|handoffs?\s*=|\bCrew\s*\("),
    "rag": _rx(
        r"embed_content|embeddings?\.create|Embeddings\s*\(|chromadb|faiss|pinecone|qdrant|weaviate|pgvector|"
        r"VectorStore|vector_store|similarity_search|text-embedding|embedding_model"
    ),
    "retries": _rx(r"tenacity|\bbackoff\b|retrying|max_retries|\bretry\b|\bRetry\s*\(|retries\s*=|attempt"),
    "timeouts": _rx(r"\btimeout\s*=|request_options|http_options|\bTimeout\s*\(|timeout:"),
    "limits": _rx(
        r"max_tokens|max_output_tokens|max_completion_tokens|max_iterations|max_steps|max_turns|"
        r"recursion_limit|MAX_STEPS|MAX_ITER|maxOutputTokens|maxTokens"
    ),
    "streaming": _rx(r"stream\s*=\s*True|generate_content_stream|\.stream\(|astream|send_message_stream|streamText"),
    "model_env": _rx(
        r"""getenv\(\s*['"][A-Z_]*MODEL[A-Z_]*['"]|environ[^\n]*['"][A-Z_]*MODEL|process\.env\.[A-Z_]*MODEL"""
    ),
    "base_url": _rx(r"base_url\s*=|BASE_URL|baseURL"),
    "mock": _rx(
        r"(?i)\bmock[_ -]?(?:mode|llm|provider|client|response)|--mock|dry[-_]?run|--offline|offline[_ -]mode|"
        r"FakeLLM|fake_llm|MOCK_|use_mock|demo[_-]mode|stub[_ -]llm"
    ),
    "local_model": _rx(r"vllm|llama_cpp|llama-cpp|lmstudio|localhost:11434|localhost:1234|ollama"),
    "usage": _rx(
        r"usage_metadata|\.usage\b|total_tokens|prompt_tokens|token_count|count_tokens|input_tokens|usageMetadata"
    ),
    "tracing": _rx(r"opentelemetry|langsmith|langfuse|logfire|arize|phoenix|\bweave\b|agentops|traceloop|openllmetry"),
    "guardrails": _rx(
        r"(?i)safety_settings|moderation|guardrail|sanitiz|max_length|max_chars|truncat|\[y/n\]|\(y/n\)|"
        r"confirm\(|human_in_the_loop|interrupt_before|allowlist|whitelist|prompt[_ ]injection"
    ),
    "eval_mock": _rx(r"(?i)mock|patch|MagicMock|monkeypatch|FakeLLM|fake|stub"),
}


def _first_hit(ws: Workspace, key: str, files: list[str]) -> str | None:
    for rel, line, _, _ in ws.grep(SIGNALS[key], files):
        return f"{rel}:{line}"
    return None


def detect_stack(ws: Workspace) -> tuple[list[str], list[str]]:
    providers: list[str] = []
    frameworks: list[str] = []

    def add(lst: list[str], item: str) -> None:
        if item not in lst:
            lst.append(item)

    for rel in ws.py_files:
        tree = ws.ast(rel)
        if tree is None:
            continue
        mods = [i.module for i in pyast.imports(tree)]
        for prefixes, name in PY_PROVIDERS:
            if any(m == p or m.startswith(p + ".") for m in mods for p in prefixes):
                add(providers, name)
        for prefixes, name in PY_FRAMEWORKS:
            if any(m == p or m.startswith(p + ".") for m in mods for p in prefixes):
                add(frameworks, name)
    for pkg in [ws.find("package.json")] if ws.find("package.json") else []:
        try:
            data = json.loads(ws.read(pkg) or "{}")
        except json.JSONDecodeError:
            data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        for name in deps:
            if name in JS_PROVIDERS:
                add(providers, JS_PROVIDERS[name])
            if name in JS_FRAMEWORKS:
                add(frameworks, JS_FRAMEWORKS[name])
    code = ws.source_files + ws.files_by_language("HTML")
    for pat, name in URL_PROVIDERS + GO_PROVIDERS:
        if any(True for _ in ws.grep(pat, code)):
            add(providers, name)
    for pat, name in GO_FRAMEWORKS:
        if any(True for _ in ws.grep(pat, ws.files_by_language("Go"))):
            add(frameworks, name)
    if (
        "OpenAI" in providers
        and len(providers) > 1
        and not any(True for _ in ws.grep(re.compile(r"api\.openai\.com|OPENAI_API_KEY"), code))
    ):
        providers.remove("OpenAI")  # the openai SDK used only as an OpenAI-compatible client
    if "Google ADK" in frameworks and not providers:
        providers.append("Gemini")  # ADK's default model backend
    return providers, frameworks


# Model calls outside Python: JS/TS SDKs, Go SDKs and raw REST calls to provider endpoints.
OTHER_LLM_CALLS = re.compile(
    r"generateContent|GenerateContent\(|chat\.completions\.create|messages\.create|generateText|streamText|"
    r"responses\.create|ollama\.chat|CreateChatCompletion|Messages\.New\(|Chat\.Completions\.New\(|"
    r"generativelanguage\.googleapis\.com|api\.openai\.com/v1/(?:chat|responses)|api\.groq\.com|"
    r"api\.anthropic\.com/v1/messages|/v1/chat/completions|localhost:11434/api/(?:chat|generate)"
)


def llm_call_sites(ws: Workspace) -> list[str]:
    sites: list[str] = []
    for rel in ws.py_files:
        tree = ws.ast(rel)
        if tree is None or ws.is_test_file(rel):
            continue
        aliases = pyast.alias_map(tree)
        ai = pyast.llm_framework_imported(tree)
        sites.extend(f"{rel}:{c.lineno}" for c, q in pyast.calls(tree, aliases) if pyast.is_llm_call(q, ai))
    others = [f for f in ws.source_files if not ws.is_test_file(f)]
    seen = {s.rsplit(":", 1)[0] for s in sites}
    for rel, line, _, _ in ws.grep(OTHER_LLM_CALLS, others):
        if rel.endswith(".py") and rel in seen:
            continue  # the AST pass already found the SDK calls in this file
        sites.append(f"{rel}:{line}")
    return sites


def _llm_calls_guarded(ws: Workspace) -> tuple[int, int]:
    """(LLM calls inside a try block, total LLM calls) for Python."""
    inside = total = 0
    for rel in ws.py_files:
        tree = ws.ast(rel)
        if tree is None or ws.is_test_file(rel):
            continue
        aliases = pyast.alias_map(tree)
        ai = pyast.llm_framework_imported(tree)
        guarded: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for sub in node.body:
                    guarded |= {id(n) for n in ast.walk(sub) if isinstance(n, ast.Call)}
        for c, q in pyast.calls(tree, aliases):
            if pyast.is_llm_call(q, ai):
                total += 1
                inside += id(c) in guarded
    return inside, total


def analyze(ws: Workspace) -> AnalyzerResult:
    r = AnalyzerResult()
    providers, frameworks = detect_stack(ws)
    ai_frameworks = [f for f in frameworks if f in AI_FRAMEWORKS]
    src = [f for f in ws.source_files if ws.language(f) != "Shell"] + ws.files_by_language("HTML")
    sites = llm_call_sites(ws)
    hit = {k: _first_hit(ws, k, src) for k in SIGNALS if k != "eval_mock"}

    # ---- maturity ladder --------------------------------------------------------------------
    evidence: list[str] = []
    uses_llm = bool(sites) or bool(ai_frameworks and ai_frameworks != ["MCP"])
    mcp = "MCP" in frameworks
    level = 0
    if uses_llm:
        level = 1
        evidence.append(f"LLM call: {sites[0]}" if sites else f"Framework: {', '.join(ai_frameworks)}")
        if hit["structured"] or hit["system_prompt"]:
            level = 2
            evidence.append(f"Structured output/system prompt: {hit['structured'] or hit['system_prompt']}")
        if hit["tools"]:
            level = 3
            evidence.append(f"Tool calling: {hit['tools']}")
            if hit["agent"] or hit["memory"] or ai_frameworks:
                level = 4
                evidence.append(f"Agent loop/memory: {hit['agent'] or hit['memory'] or ai_frameworks[0]}")
        elif hit["agent"]:
            level = 4
            evidence.append(f"Agent construct: {hit['agent']}")
        if (hit["multi_agent"] or (hit["rag"] and level >= 2) or mcp) and level >= 2:
            level = 5
            evidence.append(f"Multi-agent/RAG/MCP: {hit['multi_agent'] or hit['rag'] or 'MCP'}")
    elif mcp:
        level = 3
        evidence.append("Exposes tools to models via MCP")

    label = LEVELS[level]
    tooling = False
    if level == 0 and ws.category == "tools":
        # Developer tools *for* AI (schema linters, token calculators, eval harnesses) needn't call a model.
        corpus = ws.readme + " ".join(ws.read(f) or "" for f in ws.source_files[:30])
        mentions = len(AI_TERMS.findall(corpus))
        if mentions >= 8:
            level, label, tooling = 2, "AI tooling (no model calls)", True
            evidence.append(f"Operates on AI artefacts ({mentions} references to prompts/LLMs/MCP/tokens/evals)")

    r.checks.append(
        Check(
            id="ai_level",
            dimension=DIM,
            label="AI maturity: prompt → structured → tools → agent → multi-agent/RAG/MCP",
            weight=4,
            status="pass" if level >= 3 else "warn" if level >= 1 else "fail",
            score=level / 5,
            detail=f"Level {level}: {label}",
            fix=None
            if level >= 3 or tooling
            else "Go beyond a single prompt: structured output, tool calling, or an agent loop.",
        )
    )

    if level == 0 or tooling:
        r.facts.update(
            providers=providers,
            frameworks=frameworks,
            ai_level=level,
            ai_level_label=label,
            ai_evidence=evidence,
            llm_sites=sites,
        )
        return r

    inside, total = _llm_calls_guarded(ws)
    if total:
        guard_ratio = inside / total
    else:  # non-Python: Go checks `err != nil`, JS/TS uses try/catch
        other = [f for f in src if not f.endswith(".py")]
        guard_ratio = (
            1.0 if any(True for _ in ws.grep(re.compile(r"err != nil|\bcatch\s*[({]|\.catch\("), other)) else 0.0
        )
    parts = {
        "retries/backoff": bool(hit["retries"]),
        "timeouts": bool(hit["timeouts"]),
        "token/step limits": bool(hit["limits"]),
        "errors handled around model calls": guard_ratio >= 0.5,
    }
    rob = sum(parts.values()) / len(parts) + (0.1 if hit["streaming"] else 0)
    missing = [k for k, v in parts.items() if not v]
    r.checks.append(
        Check(
            id="robustness",
            dimension=DIM,
            label="Robust model calls (retries, timeouts, limits, error handling)",
            weight=2.5,
            status="pass" if rob >= 0.75 else "warn" if rob >= 0.4 else "fail",
            score=min(1.0, rob),
            detail="Missing: " + ", ".join(missing)
            if missing
            else "All present" + (" + streaming" if hit["streaming"] else ""),
            fix="Add retries with backoff on 429, timeouts and max token/step limits." if missing else None,
        )
    )

    mock = hit["mock"] or (
        re.search(r"(?i)mock mode|--mock|offline mode|without an api key|no api key", ws.readme) and "README.md"
    )
    port = (
        0.35 * bool(hit["model_env"])
        + 0.35 * bool(mock)
        + 0.2 * bool(hit["base_url"] or len(providers) > 1)
        + 0.1 * bool(hit["local_model"] or "Ollama" in providers)
    )
    r.checks.append(
        Check(
            id="portability",
            dimension=DIM,
            label="Provider-portable (model via env, mock/offline mode, local models)",
            weight=1.5,
            status="pass" if port >= 0.65 else "warn" if port >= 0.3 else "fail",
            score=port,
            detail=", ".join(
                k
                for k, v in {
                    "model from env": hit["model_env"],
                    "mock/offline mode": mock,
                    "configurable endpoint/multi-provider": hit["base_url"] or len(providers) > 1,
                    "local model": hit["local_model"],
                }.items()
                if v
            )
            or "Hard-wired to one model",
            fix="Read the model name from an env var and add a mock mode so reviewers can run it without keys."
            if port < 0.65
            else None,
        )
    )

    test_mock = any(SIGNALS["eval_mock"].search(ws.read(f) or "") for f in ws.test_files)
    eval_sets = any(
        re.search(r"(^|/)(evals?|golden|benchmarks?)(/|_|\.\w+$)|eval_[\w-]+\.(py|json|jsonl)$", f) for f in ws.files
    )
    ev = 0.7 * test_mock + 0.3 * eval_sets
    r.checks.append(
        Check(
            id="evals",
            dimension=DIM,
            label="AI behaviour is tested (mocked-LLM tests, eval sets)",
            weight=1,
            status="pass" if ev >= 0.7 else "warn" if ev > 0 else "fail",
            score=ev,
            detail=", ".join(k for k, v in {"tests mock the model": test_mock, "eval dataset": eval_sets}.items() if v)
            or "No AI-specific tests",
            fix="Add tests that stub the model and golden examples that check output quality." if ev < 0.7 else None,
        )
    )

    obs = 0.6 * bool(hit["usage"]) + 0.4 * bool(hit["tracing"])
    r.checks.append(
        Check(
            id="observability",
            dimension=DIM,
            label="Tracks token usage / tracing",
            weight=0.5,
            status="pass" if obs >= 0.6 else "warn",
            score=max(obs, 0.0),
            detail=", ".join(k for k, v in {"token usage": hit["usage"], "tracing": hit["tracing"]}.items() if v)
            or "No usage tracking",
        )
    )
    r.checks.append(
        Check(
            id="guardrails",
            dimension=DIM,
            label="Guardrails (input limits, safety settings, confirmations)",
            weight=0.5,
            status="pass" if hit["guardrails"] else "warn",
            detail=f"Found at {hit['guardrails']}" if hit["guardrails"] else "None detected",
        )
    )

    r.facts.update(
        providers=providers,
        frameworks=frameworks,
        ai_level=level,
        ai_level_label=label,
        ai_evidence=evidence,
        llm_sites=sites,
        signals={k: v for k, v in hit.items() if v},
    )
    return r
