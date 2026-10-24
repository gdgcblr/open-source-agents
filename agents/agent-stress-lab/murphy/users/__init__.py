"""Build the simulated user from config. Built-ins: llm, scripted; or an import path to a class."""

from __future__ import annotations

from murphy import plugins
from murphy.config.schema import PersonaConfig, UserConfig


def build_user(cfg: UserConfig, persona: PersonaConfig, seed: int, max_turns: int):
    opts = cfg.extras
    if cfg.type == "llm":
        from murphy.users.llm import LlmUser

        if not opts.get("model"):
            raise ValueError("user.model is required for type: llm")
        return LlmUser(persona, opts["model"], max_turns=max_turns, seed=seed, temperature=opts.get("temperature", 0.4))
    if cfg.type == "scripted":
        from murphy.users.scripted import ScriptedUser

        return ScriptedUser(opts.get("messages", []), opts.get("final_status", "goal_met"))
    if plugins.is_import_path(cfg.type):
        return plugins.load(cfg.type)(persona=persona, seed=seed, max_turns=max_turns, **opts)
    raise ValueError(f"user.type: unknown type {cfg.type!r} (use llm, scripted, or module:Class)")
