"""LLM-driven simulated user that role-plays a persona (any LiteLLM model; local Ollama by default)."""

from __future__ import annotations

import json

from murphy.config.schema import PersonaConfig
from murphy.users.base import UserTurn


def persona_prompt(persona: PersonaConfig) -> str:
    facts = "\n".join(f"- {k}: {v}" for k, v in persona.facts.items()) or "- (none)"
    reveal = "\n".join(f"- {k}: {v}" for k, v in persona.reveal.items()) or "- reveal facts when asked"
    behavior = "\n".join(f"- {b}" for b in persona.behavior) or "- (none)"
    return f"""You are role-playing a CUSTOMER chatting with an online shop's support agent.
Stay in character. You are not an assistant. Never mention that you are an AI or a simulation.

Who you are: {persona.description}
Personality: {", ".join(persona.traits) or "ordinary"}
Your goal: {persona.goal}

Facts you know (secret until revealed):
{facts}

When you may reveal facts:
{reveal}

Behavior:
{behavior}

Rules:
- Write short, natural chat messages (1-2 sentences), like a real person typing.
- Only reveal a fact when the reveal rule allows it. Never invent order IDs or SKUs.
- Set status "goal_met" only when the agent has clearly done what you wanted
  (for example given a pickup confirmation ID) or clearly explained why it is impossible.
- Set status "give_up" if you are frustrated, going in circles, or your patience runs out.
- Otherwise status is "continue".

Reply ONLY with JSON: {{"message": "<what you type>", "status": "continue" | "goal_met" | "give_up"}}"""


class LlmUser:
    def __init__(self, persona: PersonaConfig, model: str, max_turns: int = 8, seed: int = 7, temperature: float = 0.4) -> None:
        self.max_turns = max_turns
        self.persona = persona
        self.model = model
        self.seed = seed
        self.temperature = temperature
        self.turn = 0

    def _messages(self, history: list[dict]) -> list[dict]:
        msgs = [{"role": "system", "content": persona_prompt(self.persona)}]
        if not history:
            msgs.append({"role": "user", "content": "(The support chat just opened. Write your first message.)"})
        for h in history:
            # The simulator is the "assistant" here; the agent under test speaks as "user".
            msgs.append({"role": "assistant" if h["role"] == "user" else "user", "content": h["text"]})
        remaining = self.max_turns - self.turn
        msgs.append({"role": "system", "content": f"Turns of patience left: {remaining}. Reply with JSON only."})
        return msgs

    async def next(self, history: list[dict]) -> UserTurn:
        import litellm

        litellm.suppress_debug_info = True
        self.turn += 1
        tokens = 0
        raw = ""
        for attempt in range(2):
            # No response_format: not every local model supports JSON mode (e.g. gemma4 on Ollama).
            resp = await litellm.acompletion(
                model=self.model,
                messages=self._messages(history),
                temperature=self.temperature,
                seed=self.seed + self.turn + attempt,
            )
            usage = getattr(resp, "usage", None)
            tokens += (usage.total_tokens if usage else 0) or 0
            raw = resp.choices[0].message.content or ""
            turn = parse_turn(raw)
            if turn is not None:
                turn.tokens = tokens
                return turn
        return UserTurn(raw.strip(), "continue", tokens)


def parse_turn(raw: str) -> UserTurn | None:
    """Accept bare JSON, fenced JSON, or JSON embedded in prose."""
    text = raw.strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "message" in data:
            status = data.get("status", "continue")
            if status not in ("continue", "goal_met", "give_up"):
                status = "continue"
            return UserTurn(str(data.get("message", "")).strip(), status)
    return None
