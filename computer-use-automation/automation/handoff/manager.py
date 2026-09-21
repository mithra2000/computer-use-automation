"""Exclusive ownership and same-session human takeover, with explicit resume."""
import asyncio
import json
import time
import threading
from pathlib import Path
from uuid import uuid4

from automation.errors import CheckpointError, SessionExpiredError
from automation.models import InterventionRequest, SessionState


async def read_operator_input(prompt: str) -> str:
    """Use a daemon reader so a terminal read cannot defeat run timeout/shutdown."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def finish(value, error):
        if not future.done():
            if error:
                future.set_exception(error)
            else:
                future.set_result(value)

    def read():
        try:
            value, error = input(prompt), None
        except Exception as exc:
            value, error = None, exc
        try:
            loop.call_soon_threadsafe(finish, value, error)
        except RuntimeError:
            pass  # Run already timed out and its event loop closed.

    threading.Thread(target=read, daemon=True).start()
    return await future


class SessionHandoffManager:
    def __init__(self, surface, evidence, *, mode="none", timeout=300, operator=None):
        self.surface, self.evidence = surface, evidence
        self.mode, self.timeout, self.operator = mode, timeout, operator

    def transition(self, state):
        previous = self.surface.owner
        allowed = {
            SessionState.AUTOMATION: {SessionState.PAUSED, SessionState.COMPLETED, SessionState.FAILED},
            SessionState.PAUSED: {SessionState.HUMAN, SessionState.FAILED},
            SessionState.HUMAN: {SessionState.RESUMING, SessionState.FAILED},
            SessionState.RESUMING: {SessionState.AUTOMATION, SessionState.FAILED},
        }
        if state not in allowed.get(previous, set()):
            raise CheckpointError("Illegal session control transition")
        self.surface.owner = state
        self.evidence.event("ownership", previous=previous.value, current=state.value)

    async def intervene(self, error, step, *, goal=None):
        evidence_ref = await self.evidence.failure(self.surface, error)
        request = InterventionRequest(intervention_id=uuid4().hex, capability="get_savings_balance", goal=goal,
            run_id=self.evidence.run_id, session_id=self.evidence.session_id, current_step=step,
            stop_reason=error.code, evidence_reference=evidence_ref,
            instructions="Use the existing browser to restore the sandbox session or return to a known checkpoint. Resume explicitly; abort if uncertain.")
        self.evidence.save("intervention.json", request.model_dump())
        self.transition(SessionState.PAUSED)
        if self.mode == "none":
            self.transition(SessionState.FAILED)
            raise error
        if self.mode == "cli" and not self.surface.headed:
            self.transition(SessionState.FAILED)
            raise CheckpointError("Interactive handoff requires --headed")
        self.transition(SessionState.HUMAN)
        self.evidence.event("intervention_requested", intervention=request.model_dump(), operator_mode=self.mode)
        print(f"Automation paused: {error.code}\nRun {self.evidence.run_id}; use the SAME open browser.\nRestore session, then resume (or abort).", flush=True)
        try:
            async with asyncio.timeout(self.timeout):
                if self.operator:
                    # Dependency-injected operator only for explicitly labelled integration tests.
                    await self.operator(self.surface, request)
                elif self.mode == "cli":
                    answer = await read_operator_input("Press ENTER to resume; type abort to stop: ")
                    if answer.strip():
                        raise CheckpointError("Operator aborted")
                elif self.mode == "signal":
                    # A separate controller with access to the same visible session writes this token.
                    resume_path = self.evidence.directory / "resume.json"
                    while not resume_path.exists():
                        await asyncio.sleep(0.1)
                    payload = json.loads(resume_path.read_text())
                    resume_path.unlink()
                    if payload != {"intervention_id": request.intervention_id, "action": "resume"}:
                        raise CheckpointError("Resume signal does not match current intervention")
                else:
                    raise CheckpointError("Unknown operator mode")
        except BaseException:
            self.transition(SessionState.FAILED)
            raise
        self.transition(SessionState.RESUMING)
        # Handoff itself does not declare success. The caller must validate a checkpoint.
        self.evidence.event("resume_observation", observation=await self.surface.observe())
        self.surface.blocked_reason = None
        self.transition(SessionState.AUTOMATION)
        await self.surface.compatibility()
