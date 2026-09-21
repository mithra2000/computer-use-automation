"""Deterministic execution. This module has no model/provider imports."""
from automation.errors import ArtifactValidationError, AmbiguousTargetError, CheckpointError, SessionExpiredError
from automation.models import Capability, Result, Status


class ReplayEngine:
    def __init__(self, surface, handoff, evidence):
        self.surface, self.handoff, self.evidence = surface, handoff, evidence
        self.current_step = "initialization"

    def validate_compatibility(self, artifact):
        if artifact.app_profile != self.surface.profile.name or artifact.policy_ref != self.surface.policy.name:
            raise ArtifactValidationError("Artifact profile/policy mismatch")
        if artifact.metadata.get("application_version") != self.surface.profile.version:
            raise ArtifactValidationError("Artifact version is incompatible with the application profile")
        for step in artifact.steps:
            self.surface.policy.authorize(step.action_type, step.target)
            for checkpoint in [step.before, step.checkpoint]:
                for condition in checkpoint.conditions:
                    self.surface.policy.check_target(condition.target)
        for checkpoint in artifact.checkpoints:
            for condition in checkpoint.conditions:
                self.surface.policy.check_target(condition.target)
        for definition in artifact.outputs.values():
            self.surface.policy.check_target(definition.source)

    async def run(self, artifact, inputs):
        artifact = Capability.model_validate(artifact.model_dump())
        self.validate_compatibility(artifact)
        await self.surface.navigate()
        index, interventions = 0, 0
        rules = {r.code: r for r in artifact.recovery_rules}
        while index < len(artifact.steps):
            step = artifact.steps[index]
            self.current_step = step.step_id
            try:
                await self.surface.compatibility()
                await self.surface.wait_for_condition(step.before, inputs, attempts=rules.get("loading").max_attempts if "loading" in rules else 1,
                    timeout_ms=step.timeout_ms, outcome_rules=artifact.outcome_rules)
                self.evidence.event("action_started", step_id=step.step_id, action=step.action_type,
                                    target=step.target.model_dump() if step.target else None)
                if step.action_type == "navigate":
                    await self.surface.navigate()
                elif step.action_type == "click":
                    await self.surface.click(step.target)
                elif step.action_type == "fill":
                    await self.surface.fill(step.target, inputs, step.input_binding)
                elif step.action_type == "extract":
                    await self.surface.extract(step.target)
                # check and wait steps execute their declared checkpoint below.
                await self.surface.wait_for_condition(step.checkpoint, inputs,
                    attempts=min(step.retry_policy.max_attempts, rules["loading"].max_attempts) if "loading" in rules else 1,
                    timeout_ms=step.timeout_ms, outcome_rules=artifact.outcome_rules)
                self.evidence.event("action_completed", step_id=step.step_id, checkpoint=step.checkpoint.name, result="verified")
                index += 1
            except (SessionExpiredError, AmbiguousTargetError) as error:
                code = "session_expired" if isinstance(error, SessionExpiredError) else "ambiguous"
                if code not in rules or rules[code].strategy != "human" or interventions >= 2:
                    raise
                interventions += 1
                await self.handoff.intervene(error, step.step_id)
                await self.surface.exceptional(artifact.outcome_rules)
                if await self.surface.matches(step.checkpoint, inputs):
                    index += 1
                else:
                    # Restart at the earliest compatible before-checkpoint. It repeats
                    # only this read-only capability and rebinds member identity.
                    candidates = []
                    for position, candidate in enumerate(artifact.steps):
                        if await self.surface.matches(candidate.before, inputs):
                            candidates.append(position)
                    if not candidates:
                        raise CheckpointError("Human left session outside known continuation checkpoints")
                    index = min(candidates)
                self.evidence.event("resume_checkpoint_validated", next_step=index, result="safe_to_resume")
        for checkpoint in artifact.checkpoints:
            await self.surface.wait_for_condition(checkpoint, inputs, attempts=1, outcome_rules=artifact.outcome_rules)
        outputs = await self.surface.verify_outputs(inputs, artifact.outputs)
        return Result(status=Status.SUCCESS, outputs=outputs, run_id=self.evidence.run_id, session_id=self.evidence.session_id)
