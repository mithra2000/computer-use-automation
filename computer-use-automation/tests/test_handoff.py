import asyncio
import json
from types import SimpleNamespace

import pytest

from automation.evidence import EvidenceRecorder, Sanitizer
from automation.errors import CheckpointError, SessionExpiredError
from automation.handoff import SessionHandoffManager
from automation.models import SessionState


class FakeSurface:
    owner = SessionState.AUTOMATION
    headed = True
    blocked_reason = None

    async def observe(self):
        return {"screen": "test state"}

    async def compatibility(self):
        return None


async def test_stale_resume_token_is_rejected(tmp_path, policy):
    surface = FakeSurface()
    evidence = EvidenceRecorder(tmp_path, "test", Sanitizer(policy.config), "stale-token")
    manager = SessionHandoffManager(surface, evidence, mode="signal", timeout=1)
    (evidence.directory / "resume.json").write_text(json.dumps({"intervention_id": "stale", "action": "resume"}))
    with pytest.raises(CheckpointError):
        await manager.intervene(SessionExpiredError("expired"), "step-1")
    assert surface.owner == SessionState.FAILED


async def test_handoff_timeout_is_bounded(tmp_path, policy):
    surface = FakeSurface()
    evidence = EvidenceRecorder(tmp_path, "test", Sanitizer(policy.config), "timeout")
    manager = SessionHandoffManager(surface, evidence, mode="signal", timeout=0.05)
    with pytest.raises(TimeoutError):
        await manager.intervene(SessionExpiredError("expired"), "step-1")
    assert surface.owner == SessionState.FAILED


def test_illegal_ownership_transition(tmp_path, policy):
    manager = SessionHandoffManager(FakeSurface(), EvidenceRecorder(tmp_path, "test", Sanitizer(policy.config), "illegal"))
    with pytest.raises(CheckpointError):
        manager.transition(SessionState.HUMAN)
