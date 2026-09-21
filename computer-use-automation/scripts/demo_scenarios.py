"""Generate reproducible real-browser evidence, with an explicitly simulated operator.

Run genuine model discovery first. This script never creates fake discovery evidence.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone

from automation.cli import ROOT, execute, parser
from automation.local_server import local_server
from automation.models import SessionState


async def simulated_operator(surface, request):
    """Test driver exercising the human side of the ownership boundary, not a human."""
    assert surface.owner == SessionState.HUMAN
    surface.evidence.event("operator_provenance", identity="scripted integration-test operator; NOT a human demonstration")
    original_page, original_context = surface.page, surface.context
    await surface.page.get_by_label("Sandbox password (any value)").fill("synthetic-password-never-log")
    await surface.page.get_by_role("button", name="Restore session").click()
    await surface.page.get_by_role("heading", name="Member details", exact=True).wait_for()
    assert surface.page is original_page and surface.context is original_context


async def run(prefix):
    summaries = []
    for label, scenario, member, command, operator in [
        ("replay", "normal", "67890", "replay", None),
        ("not-found", "normal", "99999", "replay", None),
        ("slow-load", "slow_load", "67890", "replay", None),
        ("session-unattended", "session_expired", "67890", "replay", None),
        ("handoff-simulated", "session_expired", "67890", "replay", simulated_operator),
        ("policy-block", "normal", "67890", "policy-demo", None),
        ("ambiguous", "ambiguous", "67890", "replay", None),
        ("permission-denied", "permission_denied", "67890", "replay", None),
        ("wrong-member", "wrong_member", "67890", "replay", None),
        ("recovery-exhausted", "never_load", "67890", "replay", None),
        ("version-mismatch", "unknown_version", "67890", "replay", None),
    ]:
        args = parser().parse_args([command, "--member-id", member, "--scenario", scenario,
            "--run-id", f"{prefix}-{label}", "--handoff", "signal" if operator else "none"])
        result = await execute(args, operator=operator)
        summaries.append(result.model_dump(mode="json"))
        print(label, result.status, result.outcome or result.error_code or result.outputs.model_dump())
    (ROOT / "evidence" / f"{prefix}-index.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--prefix", default=datetime.now(timezone.utc).strftime("demo-%Y%m%d-%H%M%S"))
    args = cli.parse_args()
    with local_server():
        asyncio.run(run(args.prefix))
