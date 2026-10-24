"""murphy.yaml schema. Field names here are the public contract."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

FaultType = Literal["timeout_after_commit", "error_500", "slow", "malformed"]
PolicyMode = Literal["off", "monitor", "enforce"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Open(BaseModel):
    """Plugin-facing sections accept extra keys (passed to the plugin as options)."""

    model_config = ConfigDict(extra="allow")

    @property
    def extras(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class Upstream(Strict):
    name: str
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    inherit_env: bool = True  # pass the caller's environment (DATABASE_URL, API keys, ...) to the server


class FaultSpec(Strict):
    tool: str  # fnmatch glob
    type: FaultType
    on_call: int | None = None  # 1-based call index of a matching tool
    rate: float | None = Field(default=None, ge=0, le=1)
    delay_s: float = 5.0

    @model_validator(mode="after")
    def _one_trigger(self):
        if self.on_call is not None and self.rate is not None:
            raise ValueError("set either on_call or rate, not both")
        if self.on_call is None and self.rate is None:
            self.on_call = 1
        return self

    @property
    def label(self) -> str:
        return f"{self.type}({self.tool})"


class FaultScenario(Strict):
    id: str
    inject: list[FaultSpec] = Field(default_factory=list)


class IdempotentRule(Strict):
    id: str
    type: Literal["idempotent"]
    tool: str
    key: list[str]


class RequiresBeforeRule(Strict):
    id: str
    type: Literal["requires_before"]
    tool: str
    prior: str
    match: list[str] = Field(default_factory=list)
    prior_result: dict[str, Any] = Field(default_factory=dict)


class MaxCallsRule(Strict):
    id: str
    type: Literal["max_calls"]
    tool: str
    max: int


class BudgetRule(Strict):
    id: str
    type: Literal["budget"]
    max_tool_calls: int


Rule = Annotated[Union[IdempotentRule, RequiresBeforeRule, MaxCallsRule, BudgetRule], Field(discriminator="type")]


class PolicyConfig(Strict):
    mode: PolicyMode = "monitor"
    rules: list[Rule] = Field(default_factory=list)


class TargetConfig(Open):
    type: str  # adk | http | scripted | "module:Class"


class UserConfig(Open):
    type: str = "llm"  # llm | scripted | "module:Class"


class PersonaConfig(Strict):
    id: str
    description: str = ""
    goal: str
    traits: list[str] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)
    reveal: dict[str, str] = Field(default_factory=dict)
    behavior: list[str] = Field(default_factory=list)
    max_turns: int | None = None
    vars: dict[str, Any] = Field(default_factory=dict)


class CheckConfig(Open):
    id: str
    type: str  # trace | python | http | "module:Class"
    label: str = "wrong"
    hint: str = ""


class Limits(Strict):
    max_turns_default: int = 8
    run_timeout_s: float = 300


class FailIf(Strict):
    completion_below: float | None = Field(default=None, ge=0, le=1)
    any_label: list[str] = Field(default_factory=list)


class CiConfig(Strict):
    fail_if: FailIf = Field(default_factory=FailIf)


class ProjectConfig(Strict):
    version: Literal[1] = 1
    name: str
    python_path: list[str] = Field(default_factory=lambda: ["."])
    target: TargetConfig
    tools: list[Upstream] = Field(default_factory=list)
    user: UserConfig = Field(default_factory=UserConfig)
    personas: list[PersonaConfig]
    faults: list[FaultScenario] = Field(default_factory=lambda: [FaultScenario(id="no-fault")])
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    checks: list[CheckConfig] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    seed: int = 7
    ci: CiConfig = Field(default_factory=CiConfig)

    base_dir: Path = Field(default=Path("."), exclude=True)
    source: Path | None = Field(default=None, exclude=True)

    def persona(self, persona_id: str) -> PersonaConfig:
        for p in self.personas:
            if p.id == persona_id:
                return p
        raise KeyError(f"unknown persona {persona_id!r}")

    def scenario(self, scenario_id: str) -> FaultScenario:
        for s in self.faults:
            if s.id == scenario_id:
                return s
        raise KeyError(f"unknown fault scenario {scenario_id!r}")

    def max_turns(self, persona: PersonaConfig) -> int:
        return persona.max_turns or self.limits.max_turns_default
