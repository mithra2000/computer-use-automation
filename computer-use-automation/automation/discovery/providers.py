"""One live API provider and a transparent external-model file bridge."""
import asyncio
import json
import os
from pathlib import Path
from typing import Protocol

import httpx

from automation.errors import AutomationError
from automation.models import Proposal


class Provider(Protocol):
    name: str

    async def decide(self, request: dict) -> Proposal: ...


class AnthropicProvider:
    def __init__(self):
        self.model = os.environ.get("LLM_MODEL", "")
        self.key = os.environ.get("LLM_API_KEY", "")
        if not self.model or not self.key:
            raise AutomationError("Set LLM_MODEL and LLM_API_KEY for live discovery; credentials are never needed for replay")
        self.name = f"anthropic:{self.model}"

    async def decide(self, request):
        # Tool use supplies a JSON Schema contract. Local validation remains mandatory.
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers={
                "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 700, "system": request["system"],
                    "messages": [{"role": "user", "content": json.dumps({k: v for k, v in request.items() if k != "system"})}],
                    "tools": [{"name": "propose_action", "description": "Propose one permitted UI action", "input_schema": Proposal.model_json_schema()}],
                    "tool_choice": {"type": "tool", "name": "propose_action"}})
        if response.is_error:
            raise AutomationError(f"LLM API failed with HTTP {response.status_code}; response body omitted to protect credentials")
        calls = [b for b in response.json().get("content", []) if b.get("type") == "tool_use" and b.get("name") == "propose_action"]
        if len(calls) != 1:
            raise AutomationError("LLM must return exactly one structured action")
        return Proposal.model_validate(calls[0]["input"])


class BridgeProvider:
    """A tool-enabled LLM reads request-NNN.json and writes response-NNN.json.

    This does not itself prove an LLM answered: provenance is recorded explicitly.
    Never relabel scripted test responses as live model evidence.
    """
    def __init__(self, directory: Path, provenance: str):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        self.name = f"external-model-bridge:{provenance}"
        self.index = 0

    async def decide(self, request):
        self.index += 1
        suffix = f"{self.index:03d}.json"
        path = self.directory / f"request-{suffix}"
        path.write_text(json.dumps(request, indent=2) + "\n")
        print(f"MODEL_REQUEST {path}", flush=True)
        answer = self.directory / f"response-{suffix}"
        while not answer.exists():
            await asyncio.sleep(0.1)
        return Proposal.model_validate_json(answer.read_text())


def make_provider(bridge_dir=None, provenance="unspecified"):
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "bridge":
        return BridgeProvider(Path(bridge_dir or os.environ.get("LLM_BRIDGE_DIR", ".bridge")), provenance)
    raise AutomationError("Unsupported LLM_PROVIDER; choose anthropic or bridge")
