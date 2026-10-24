"""Build the agent under test from config. Built-ins: adk, http, scripted; or an import path to a class."""

from __future__ import annotations

from murphy import plugins
from murphy.config.schema import TargetConfig


def build_target(cfg: TargetConfig, override: str | None = None):
    """`override` (CLI --target) replaces the adk factory / scripted policy / http url."""
    opts = cfg.extras
    if cfg.type == "adk":
        from murphy.targets.adk import AdkTarget

        ref = override or opts["factory"]
        return AdkTarget(plugins.load(ref), label=ref, model=opts.get("model"))
    if cfg.type == "scripted":
        from murphy.targets.scripted import ScriptedTarget

        ref = override or opts["policy"]
        return ScriptedTarget(plugins.load(ref), label=ref)
    if cfg.type == "http":
        from murphy.targets.http import HttpTarget

        url = override or opts["url"]
        return HttpTarget(url, label=url, timeout_s=opts.get("timeout_s", 120), headers=opts.get("headers"))
    if plugins.is_import_path(cfg.type):
        return plugins.load(cfg.type)(**opts)
    raise ValueError(f"target.type: unknown type {cfg.type!r} (use adk, http, scripted, or module:Class)")


def target_label(cfg: TargetConfig, override: str | None = None) -> str:
    opts = cfg.extras
    return override or opts.get("factory") or opts.get("policy") or opts.get("url") or cfg.type
