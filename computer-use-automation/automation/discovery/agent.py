"""Observe -> propose -> validate -> authorize -> act -> verify -> record."""
import asyncio
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from automation.artifacts import ArtifactBuilder, outcome_rules, output_definitions
from automation.errors import DiscoveryStoppedError, PolicyViolationError, SessionExpiredError, AmbiguousTargetError
from automation.models import Proposal, Result, Status, Step


class DiscoveryAgent:
    def __init__(self, surface, provider, handoff, evidence, *, max_steps=25):
        self.surface, self.provider, self.handoff, self.evidence = surface, provider, handoff, evidence
        self.max_steps = max_steps

    async def run(self, goal, inputs, artifact_path):
        await self.surface.navigate()
        steps, history, counts = [], [], Counter()
        for index in range(self.max_steps):
            try:
                await self.surface.exceptional(outcome_rules())
                observation = await self.surface.observe()
                fingerprint = hashlib.sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()
                counts[fingerprint] += 1
                if counts[fingerprint] > 4:
                    raise DiscoveryStoppedError("Repeated UI state: no progress")
                request = {"system": Path(__file__).with_name("system_prompt.txt").read_text(),
                    "goal": self.evidence.sanitizer.clean(goal), "input_parameters": {"member_id": "runtime-bound"},
                    "observation": observation, "action_schema": Proposal.model_json_schema(), "history": history[-8:]}
                self.evidence.save(f"model-request-{index + 1:03d}.json", request)
                started = time.monotonic()
                proposal = await self.provider.decide(request)
                self.evidence.save(f"model-response-{index + 1:03d}.json", proposal.model_dump())
                self.evidence.event("model_proposal", provider=self.provider.name, proposal=proposal.model_dump(),
                                    duration_ms=round((time.monotonic() - started) * 1000))
                target = self.surface.catalog.get(proposal.target_id) if proposal.target_id else None
                if proposal.target_id and target is None:
                    raise PolicyViolationError("Model target is not present in current observation")
                self.surface.policy.authorize(proposal.action, target)
                if proposal.action == "intervene":
                    raise DiscoveryStoppedError("Model requested intervention")
                if proposal.action == "complete":
                    outputs = await self.surface.verify_outputs(inputs, output_definitions())
                    if proposal.candidate_outputs != outputs:
                        raise DiscoveryStoppedError("Model candidate outputs disagree with verified UI values")
                    artifact = ArtifactBuilder().build(steps, self.surface.profile, self.surface.policy, self.evidence, self.provider.name)
                    ArtifactBuilder().save(artifact, artifact_path)
                    self.evidence.save("capability.json", artifact.model_dump())
                    return Result(status=Status.SUCCESS, outputs=outputs, run_id=self.evidence.run_id, session_id=self.evidence.session_id)
                before = await self.surface.checkpoint_here(inputs)
                if proposal.action == "click":
                    await self.surface.click(target)
                elif proposal.action == "fill":
                    await self.surface.fill(target, inputs, proposal.input_binding)
                elif proposal.action == "navigate":
                    await self.surface.navigate()
                elif proposal.action == "extract":
                    await self.surface.extract(target)
                elif proposal.action == "check":
                    await self.surface.locate(target)
                elif proposal.action == "wait":
                    await self.surface.wait_for_condition(before, inputs, outcome_rules=outcome_rules())
                await self.surface.exceptional(outcome_rules())
                # Wait for frame navigation to settle through observable document readiness.
                for frame in self.surface.page.frames:
                    await frame.wait_for_load_state("domcontentloaded")
                after = await self.surface.checkpoint_here(inputs, filled=proposal.action == "fill")
                if proposal.action in {"click", "fill", "navigate"}:
                    steps.append(Step(step_id=f"step-{len(steps) + 1:03d}", action_type=proposal.action, target=target,
                        input_binding=proposal.input_binding, route_ref="entry_point" if proposal.action == "navigate" else None,
                        before=before, checkpoint=after, timeout_ms=self.surface.policy.config["action_timeout_ms"],
                        risk_classification="session_bootstrap" if target and target.name == "Enter sandbox" else "read_only"))
                history.append({"action": proposal.action, "target": target.model_dump() if target else None,
                                "result": "verified", "checkpoint": after.name})
                self.evidence.event("action", step_id=steps[-1].step_id if steps else None, action=proposal.action,
                    target=target.model_dump() if target else None, checkpoint=after.name, result="verified")
            except (DiscoveryStoppedError, SessionExpiredError, AmbiguousTargetError) as error:
                await self.handoff.intervene(error, f"discovery-{index + 1}", goal=goal)
                # Continuing discovery after manual actions would produce an incomplete
                # artifact. Restart discovery from entry, on the same browser session.
                # Human assistance remains in evidence; it is never silently compiled.
                await self.surface.navigate()
                steps, history, counts = [], [], Counter()
        error = DiscoveryStoppedError("Discovery reached MAX_STEPS")
        await self.handoff.intervene(error, "max-steps", goal=goal)
        raise error  # The exhausted discovery budget cannot be reset by a handoff.
