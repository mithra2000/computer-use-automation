"""Only sanitized projections are persisted; raw DOM/traces are never saved."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Sanitizer:
    def __init__(self, policy: dict):
        self.fields = set(policy["sensitive_fields"]) | {"password", "token", "secret", "authorization", "api_key"}
        self.rules = policy["redaction_rules"]
        self.secrets = [v for k, v in os.environ.items() if any(s in k.lower() for s in ["api_key", "password", "token"]) and len(v) >= 6]

    def clean(self, value):
        if isinstance(value, dict):
            return {k: "[REDACTED]" if k.lower() in self.fields else self.clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)(bearer\s+|(?:password|token|api_key|secret)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
            if self.rules.get("mask_member_ids"):
                value = re.sub(r"\b[0-9]{5}\b", "[MEMBER_ID]", value)
            if self.rules.get("mask_financial_values"):
                value = re.sub(r"\b[0-9]+\.[0-9]{2}\b", "[BALANCE]", value)
            return value
        return value


class EvidenceRecorder:
    def __init__(self, root: Path, mode: str, sanitizer: Sanitizer, run_id: str | None = None):
        self.run_id = run_id or f"local-{mode}-{uuid4().hex[:10]}"
        self.session_id = uuid4().hex
        self.mode, self.sanitizer = mode, sanitizer
        self.directory = root / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)

    def event(self, event: str, **fields):
        payload = {"timestamp": now(), "run_id": self.run_id, "session_id": self.session_id,
                   "mode": self.mode, "capability": "get_savings_balance", "event": event, **fields}
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(self.sanitizer.clean(payload), ensure_ascii=False) + "\n")

    def save(self, filename: str, payload) -> str:
        path = self.directory / filename
        path.write_text(json.dumps(self.sanitizer.clean(payload), indent=2, ensure_ascii=False) + "\n")
        return str(path)

    async def failure(self, surface, error) -> str:
        # A sanitized structured UI snapshot is richer evidence than an action log.
        try:
            observation = await surface.observe()
        except Exception:
            observation = {"state": "unavailable"}
        path = self.save(f"failure-{uuid4().hex[:8]}.json", {"error_code": error.code, "observation": observation})
        self.event("failure_evidence", error_code=error.code, evidence_reference=path)
        return path
