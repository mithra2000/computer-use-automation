"""Build capabilities from executed actions, never from a model transcript."""
from pathlib import Path
from pydantic import ValidationError

from automation.errors import ArtifactValidationError
from automation.models import Capability, Checkpoint, Condition, OutcomeRule, OutputDefinition, RecoveryRule, Target


def output_definitions():
    return {"balance": OutputDefinition(type="decimal_string", source=Target(strategy="table_cell", name="Balance", table="Account summary", frame="accounts")),
            "currency": OutputDefinition(type="currency_code", source=Target(strategy="table_cell", name="Currency", table="Account summary", frame="accounts"))}


def outcome_rules():
    return [OutcomeRule(code="member_not_found", condition=Condition(target=Target(strategy="text", name="No member found")))]


def final_checkpoint():
    return Checkpoint(name="FINAL_SUCCESS", conditions=[
        Condition(target=Target(strategy="table_cell", name="Member ID", table="Member details"), operator="equals_input", parameter="member_id"),
        Condition(target=Target(strategy="table_cell", name="Member ID", table="Account summary", frame="accounts"), operator="equals_input", parameter="member_id"),
        Condition(target=Target(strategy="table_cell", name="Account type", table="Account summary", frame="accounts"), operator="equals", value="Savings"),
        Condition(target=Target(strategy="table_cell", name="Balance", table="Account summary", frame="accounts")),
        Condition(target=Target(strategy="table_cell", name="Currency", table="Account summary", frame="accounts"))])


class ArtifactBuilder:
    def build(self, steps, profile, policy, evidence, provider_name):
        # Keep every executed state-changing action. Only observations/checks without
        # side effects are omitted; unsafe path optimization would need another replay.
        return Capability(app_profile=profile.name,
            inputs={"member_id": {"type": "string", "pattern": "^[0-9]{5}$", "required": True}},
            outputs=output_definitions(), steps=steps, checkpoints=[final_checkpoint()],
            outcome_rules=outcome_rules(), recovery_rules=[
                RecoveryRule(code="loading", strategy="bounded_wait"),
                RecoveryRule(code="session_expired", strategy="human"),
                RecoveryRule(code="ambiguous", strategy="human")], policy_ref=policy.name,
            metadata={"source_run_id": evidence.run_id, "provider": provider_name,
                      "locator_strategy": "Exact semantic controls, named frame, scoped table rows; fail on ambiguity",
                      "application_version": profile.version})

    def save(self, artifact, path: Path):
        artifact = Capability.model_validate(artifact.model_dump())
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(artifact.model_dump_json(indent=2) + "\n")
        temporary.replace(path)


def load_artifact(path: Path) -> Capability:
    try:
        return Capability.model_validate_json(path.read_text())
    except (OSError, ValidationError, ValueError) as exc:
        raise ArtifactValidationError("Capability could not be read or validated") from exc
