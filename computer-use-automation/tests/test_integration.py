"""Real-browser integration checks; operator actions are explicitly simulated."""
import builtins
import json
import os
from pathlib import Path

import pytest

from automation.cli import ROOT, execute, parser
from automation.models import SessionState, Status, Target
from automation.errors import PolicyViolationError


def args_for(tmp_path, scenario="normal", member="67890", command="replay"):
    return parser().parse_args([command, "--member-id", member, "--scenario", scenario,
        "--evidence-dir", str(tmp_path), "--run-id", "test-" + scenario])


def events(tmp_path, scenario):
    return [json.loads(line) for line in (tmp_path / ("test-" + scenario) / "events.jsonl").read_text().splitlines()]


async def test_replay_with_different_id_and_no_model_import(bank_server, tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "this-provider-does-not-exist")
    original = builtins.__import__
    def guard(name, *args, **kwargs):
        if name.startswith("automation.discovery"):
            raise AssertionError("Replay attempted to import model code")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guard)
    result = await execute(args_for(tmp_path))
    assert result.status == Status.SUCCESS, result
    assert result.outputs.balance == "8100.25"
    assert result.outputs.currency == "USD"
    assert not any(e["event"] == "model_proposal" for e in events(tmp_path, "normal"))


@pytest.mark.parametrize("scenario,member,status,code", [
    ("normal", "99999", Status.BUSINESS_OUTCOME, "member_not_found"),
    ("permission_denied", "67890", Status.HARD_FAILURE, "PERMISSION_DENIED"),
    ("ambiguous", "67890", Status.INTERVENTION_REQUIRED, "AMBIGUOUS_TARGET"),
    ("session_expired", "67890", Status.INTERVENTION_REQUIRED, "SESSION_EXPIRED"),
    ("wrong_member", "67890", Status.HARD_FAILURE, "RECOVERY_EXHAUSTED"),
    ("unknown_version", "67890", Status.HARD_FAILURE, "UNSUPPORTED_APP_VERSION"),
    ("never_load", "67890", Status.HARD_FAILURE, "RECOVERY_EXHAUSTED"),
])
async def test_failure_classifications(bank_server, tmp_path, scenario, member, status, code):
    result = await execute(args_for(tmp_path, scenario, member))
    assert result.status == status, result
    assert (result.outcome or result.error_code) == code, result
    assert result.evidence_reference and Path(result.evidence_reference).exists()
    if scenario == "never_load":
        assert len([e for e in events(tmp_path, scenario) if e["event"] == "recovery_attempt"]) == 2


async def test_slow_load_recovers(bank_server, tmp_path):
    result = await execute(args_for(tmp_path, "slow_load"))
    assert result.status == Status.SUCCESS, result
    assert any(e["event"] == "recovery_attempt" for e in events(tmp_path, "slow_load"))


async def simulated_operator(surface, request):
    assert surface.owner == SessionState.HUMAN
    page = surface.page
    context = surface.context
    with pytest.raises(PolicyViolationError):
        await surface.click(Target(strategy="role", role="button", name="Search"))
    await page.get_by_label("Sandbox password (any value)").fill("DO-NOT-LOG-THIS-PASSWORD")
    await page.get_by_role("button", name="Restore session").click()
    await page.get_by_role("heading", name="Member details", exact=True).wait_for()
    assert surface.page is page and surface.context is context


async def test_same_session_handoff_with_simulated_operator(bank_server, tmp_path):
    args = args_for(tmp_path, "session_expired")
    args.handoff = "signal"
    result = await execute(args, operator=simulated_operator)
    assert result.status == Status.SUCCESS, result
    log = events(tmp_path, "session_expired")
    states = [e["current"] for e in log if e["event"] == "ownership"]
    assert states == ["PAUSED", "HUMAN", "RESUMING", "AUTOMATION"]
    assert any(e["event"] == "human_action" and e["event_type"] == "click" for e in log)
    assert any(e["event"] == "resume_checkpoint_validated" for e in log)
    assert len({e["session_id"] for e in log}) == 1
    all_text = "\n".join(p.read_text() for p in tmp_path.rglob("*.json*"))
    assert "DO-NOT-LOG-THIS-PASSWORD" not in all_text


async def test_policy_demo_blocks_before_action(bank_server, tmp_path):
    result = await execute(args_for(tmp_path, command="policy-demo"))
    assert result.status == Status.POLICY_BLOCKED
    assert not any(e["event"] == "action_completed" for e in events(tmp_path, "normal"))
