"""CLI composition root. Replay never imports a discovery provider."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from automation.artifacts import load_artifact
from automation.errors import AutomationError, BusinessOutcome, PolicyViolationError
from automation.evidence import EvidenceRecorder, Sanitizer
from automation.handoff import SessionHandoffManager
from automation.models import AppProfile, Inputs, Result, SessionState, Status, Target
from automation.policy import PolicyEngine
from automation.replay import ReplayEngine
from automation.surface import SurfaceAdapter

ROOT = Path(__file__).resolve().parents[1]


async def execute(args, *, operator=None, provider=None):
    policy = PolicyEngine(ROOT / "config/policy.yaml")
    if os.environ.get("ACTION_TIMEOUT_MS"):
        configured_timeout = int(os.environ["ACTION_TIMEOUT_MS"])
        if not 100 <= configured_timeout <= policy.config["max_action_timeout_ms"]:
            raise ValueError("ACTION_TIMEOUT_MS must be within policy limits (100..5000)")
        policy.config["action_timeout_ms"] = configured_timeout
    profile = AppProfile.model_validate_json((ROOT / "config/app.json").read_text(encoding="utf-8"))
    evidence = EvidenceRecorder(Path(args.evidence_dir), args.command, Sanitizer(policy.config), args.run_id)
    surface, engine = None, None
    try:
        inputs = Inputs(member_id=args.member_id)
        async with SurfaceAdapter(profile, policy, evidence, headed=args.headed, scenario=args.scenario) as surface:
            handoff = SessionHandoffManager(surface, evidence, mode=args.handoff, operator=operator,
                                           timeout=int(os.environ.get("HANDOFF_TIMEOUT_SECONDS", "300")))
            try:
                async with asyncio.timeout(args.timeout):
                    if args.command == "discover":
                        from automation.discovery.agent import DiscoveryAgent
                        from automation.discovery.providers import make_provider
                        model = provider or make_provider(args.bridge_dir, args.provenance)
                        evidence.event("run_started", provider=model.name, goal=args.goal, llm_decisions=True)
                        engine = DiscoveryAgent(surface, model, handoff, evidence, max_steps=args.max_steps)
                        result = await engine.run(args.goal, inputs, Path(args.artifact))
                    elif args.command == "replay":
                        evidence.event("run_started", llm_decisions=False)
                        engine = ReplayEngine(surface, handoff, evidence)
                        result = await engine.run(load_artifact(Path(args.artifact)), inputs)
                    else:
                        await surface.navigate()
                        policy.authorize("click", Target(strategy="role", role="button", name="Transfer Funds"))
                        raise AutomationError("Policy demo unexpectedly allowed the action")
                surface.owner = SessionState.COMPLETED
            except Exception as error:
                result = await failure_result(error, surface, evidence, getattr(engine, "current_step", None))
                surface.owner = SessionState.FAILED
    except Exception as error:
        result = await failure_result(error, None, evidence, None)
    evidence.save("summary.json", result.model_dump(mode="json"))
    evidence.event("run_finished", result=result.model_dump(mode="json"))
    return result


async def failure_result(error, surface, evidence, step):
    if isinstance(error, ValidationError):
        error = AutomationError("Input or structured payload validation failed")
        error.code = "VALIDATION_ERROR"
    elif isinstance(error, TimeoutError):
        error = AutomationError("Overall run or handoff timeout reached")
        error.code = "RUN_TIMEOUT"
    elif not isinstance(error, AutomationError):
        # Avoid persisting raw third-party exception text: it may contain inputs/URLs.
        kind = type(error).__name__
        error = AutomationError(f"Unexpected {kind}; inspect sanitized failure state")
    reference = await evidence.failure(surface, error) if surface else None
    return Result(status=error.status, outcome=error.code if isinstance(error, BusinessOutcome) else None,
        error_code=None if isinstance(error, BusinessOutcome) else error.code, step=step,
        expected=error.expected, observed=error.observed or str(error), evidence_reference=reference,
        run_id=evidence.run_id, session_id=evidence.session_id)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["discover", "replay", "policy-demo"])
    p.add_argument("--goal", default="Find the supplied member and return their current savings balance")
    p.add_argument("--member-id", default="12345")
    p.add_argument("--capability", default="get_savings_balance", choices=["get_savings_balance"])
    p.add_argument("--artifact", default=str(ROOT / "capabilities/get_savings_balance/v1.json"))
    p.add_argument("--scenario", default="normal", choices=["normal", "slow_load", "session_expired", "permission_denied", "ambiguous", "wrong_member", "unknown_version", "never_load"])
    p.add_argument("--headed", action="store_true")
    p.add_argument("--start-app", action="store_true", help="Start and stop the local mock server with this run")
    p.add_argument("--handoff", choices=["none", "cli", "signal"], default="none")
    p.add_argument("--evidence-dir", default=str(ROOT / "evidence"))
    p.add_argument("--run-id")
    p.add_argument("--bridge-dir")
    p.add_argument("--provenance", default="unspecified")
    p.add_argument("--timeout", type=int, default=int(os.environ.get("RUN_TIMEOUT_SECONDS", "180")))
    p.add_argument("--max-steps", type=int, default=int(os.environ.get("MAX_STEPS", "25")))
    return p


def main():
    load_dotenv(ROOT / ".env")
    args = parser().parse_args()
    from automation.local_server import local_server
    with local_server(args.start_app):
        result = asyncio.run(execute(args))
    print(result.model_dump_json(indent=2))
    raise SystemExit(0 if result.status in {Status.SUCCESS, Status.BUSINESS_OUTCOME} or (args.command == "policy-demo" and result.status == Status.POLICY_BLOCKED) else 2)


if __name__ == "__main__":
    main()
