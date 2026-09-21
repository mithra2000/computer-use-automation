"""Strict serialized contracts. No executable strings or arbitrary selectors."""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Status(StrEnum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    RECOVERABLE_ERROR = "recoverable_error"
    INTERVENTION_REQUIRED = "intervention_required"
    HARD_FAILURE = "hard_failure"
    POLICY_BLOCKED = "policy_blocked"


class SessionState(StrEnum):
    AUTOMATION = "AUTOMATION"
    PAUSED = "PAUSED"
    HUMAN = "HUMAN"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Inputs(StrictModel):
    member_id: str = Field(pattern=r"^[0-9]{5}$", strict=True)


class Outputs(StrictModel):
    balance: str = Field(pattern=r"^-?[0-9]+\.[0-9]{2}$", strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$", strict=True)


class Target(StrictModel):
    strategy: Literal["role", "label", "text", "table_cell"]
    name: str = Field(min_length=1, max_length=120)
    role: Literal["button", "link", "textbox", "heading"] | None = None
    frame: str | None = None
    table: str | None = None


class Condition(StrictModel):
    target: Target
    operator: Literal["visible", "equals", "equals_input"] = "visible"
    value: str | None = None
    parameter: Literal["member_id"] | None = None

    @model_validator(mode="after")
    def valid_comparison(self):
        if self.operator == "equals" and self.value is None:
            raise ValueError("equals needs value")
        if self.operator == "equals_input" and self.parameter is None:
            raise ValueError("equals_input needs a parameter")
        return self


class Checkpoint(StrictModel):
    name: str
    conditions: list[Condition] = Field(min_length=1)


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=3, ge=1, le=3)
    idempotent: bool = True


class Step(StrictModel):
    step_id: str
    action_type: Literal["navigate", "click", "fill", "extract", "check", "wait"]
    target: Target | None = None
    input_binding: Literal["member_id"] | None = None
    route_ref: Literal["entry_point"] | None = None
    before: Checkpoint
    checkpoint: Checkpoint
    timeout_ms: int = Field(default=800, ge=100, le=5000)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    risk_classification: Literal["read_only", "session_bootstrap"] = "read_only"

    @model_validator(mode="after")
    def action_fields(self):
        if self.action_type == "fill" and (not self.target or not self.input_binding):
            raise ValueError("fill needs target and explicit input binding")
        if self.action_type in {"click", "extract"} and not self.target:
            raise ValueError("action needs target")
        if self.action_type == "navigate" and not self.route_ref:
            raise ValueError("navigation must reference the profile entry point")
        return self


class OutputDefinition(StrictModel):
    type: Literal["decimal_string", "currency_code"]
    source: Target


class OutcomeRule(StrictModel):
    code: Literal["member_not_found"]
    condition: Condition


class RecoveryRule(StrictModel):
    code: Literal["loading", "session_expired", "ambiguous"]
    strategy: Literal["bounded_wait", "human"]
    max_attempts: int = Field(default=3, ge=1, le=3)


class Capability(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    capability_name: Literal["get_savings_balance"] = "get_savings_balance"
    capability_version: Literal["1.0.0"] = "1.0.0"
    app_profile: str
    inputs: dict[str, dict]
    outputs: dict[str, OutputDefinition]
    steps: list[Step] = Field(min_length=1, max_length=50)
    checkpoints: list[Checkpoint] = Field(min_length=1)
    outcome_rules: list[OutcomeRule]
    recovery_rules: list[RecoveryRule]
    policy_ref: str
    metadata: dict[str, str]

    @model_validator(mode="after")
    def contract(self):
        if self.inputs != {"member_id": {"type": "string", "pattern": "^[0-9]{5}$", "required": True}}:
            raise ValueError("Unsupported input contract")
        if set(self.outputs) != {"balance", "currency"}:
            raise ValueError("Capability requires balance and currency")
        if self.outputs["balance"].type != "decimal_string" or self.outputs["currency"].type != "currency_code":
            raise ValueError("Output type mismatch")
        if len({s.step_id for s in self.steps}) != len(self.steps):
            raise ValueError("Duplicate step IDs")
        if not any(s.input_binding == "member_id" for s in self.steps):
            raise ValueError("Capability must bind member_id")
        return self


class AppProfile(StrictModel):
    name: str
    application_family: str
    version: str
    base_url: str
    entry_point: str
    approved_origins: list[str]
    supported_capabilities: list[str]
    locator_overrides: dict[str, Target]
    compatibility_rules: dict[str, str]


class Proposal(StrictModel):
    action: Literal["navigate", "click", "fill", "extract", "wait", "check", "complete", "intervene"]
    target_id: str | None = None
    input_binding: Literal["member_id"] | None = None
    reason: str = Field(max_length=300)
    candidate_outputs: Outputs | None = None

    @model_validator(mode="after")
    def validate_action(self):
        if self.action in {"click", "fill", "extract", "check"} and not self.target_id:
            raise ValueError("Target must refer to the current observation")
        if self.action == "fill" and self.input_binding != "member_id":
            raise ValueError("Only bound member lookup inputs may be filled")
        return self


class Result(StrictModel):
    status: Status
    capability: str = "get_savings_balance"
    outputs: Outputs | None = None
    outcome: str | None = None
    error_code: str | None = None
    step: str | None = None
    expected: str | None = None
    observed: str | None = None
    evidence_reference: str | None = None
    run_id: str
    session_id: str


class InterventionRequest(StrictModel):
    intervention_id: str
    capability: str
    goal: str | None = None
    run_id: str
    session_id: str
    current_step: str
    stop_reason: str
    evidence_reference: str
    instructions: str
