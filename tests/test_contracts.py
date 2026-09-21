import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from automation.artifacts import load_artifact
from automation.cli import ROOT
from automation.errors import ArtifactValidationError, PolicyViolationError
from automation.evidence import Sanitizer
from automation.models import Capability, Inputs, Outputs, Proposal, Target


def test_artifact_is_parameterized_and_versioned():
    artifact = load_artifact(ROOT / "capabilities/get_savings_balance/v1.json")
    assert artifact.schema_version == "1.0"
    assert any(s.input_binding == "member_id" for s in artifact.steps)
    assert "12345" not in artifact.model_dump_json()
    assert artifact.metadata["source_run_id"]


@pytest.mark.parametrize("value", [12345, "../12", "1234", "123456", "abcde"])
def test_input_rejects_invalid_member(value):
    with pytest.raises(ValidationError):
        Inputs(member_id=value)


@pytest.mark.parametrize("value", ["NaN", "1e9", "12.345", 12.50])
def test_outputs_require_decimal_string(value):
    with pytest.raises(ValidationError):
        Outputs(balance=value, currency="USD")


def test_artifact_rejects_unknown_version_and_duplicate_steps():
    data = json.loads((ROOT / "capabilities/get_savings_balance/v1.json").read_text())
    data["schema_version"] = "9.0"
    with pytest.raises(ValidationError):
        Capability.model_validate(data)
    data["schema_version"] = "1.0"
    data["steps"].append(data["steps"][0])
    with pytest.raises(ValidationError):
        Capability.model_validate(data)


def test_artifact_loading_error(tmp_path):
    with pytest.raises(ArtifactValidationError):
        load_artifact(tmp_path / "missing.json")


def test_proposal_cannot_carry_code_or_literal_input():
    with pytest.raises(ValidationError):
        Proposal(action="fill", target_id="x", input_binding="member_id", reason="fill", code="print(1)")
    with pytest.raises(ValidationError):
        Proposal(action="fill", target_id="x", reason="fill")


def test_policy_allows_lookup_and_rejects_mutation(policy):
    policy.authorize("click", Target(strategy="role", role="button", name="Search"))
    for name in ["Transfer Funds", "Delete account", "Change credentials"]:
        with pytest.raises(PolicyViolationError):
            policy.authorize("click", Target(strategy="role", role="button", name=name))


@pytest.mark.parametrize("url", ["https://evil.example/", "http://127.0.0.1:8000/delete", "http://127.0.0.1:8000/?token=secret", "http://user:pass@127.0.0.1:8000/"])
def test_policy_blocks_destinations(policy, url):
    with pytest.raises(PolicyViolationError):
        policy.check_url(url)


def test_reauth_is_human_only(policy):
    with pytest.raises(PolicyViolationError):
        policy.check_url("http://127.0.0.1:8000/restore", "POST")
    policy.check_url("http://127.0.0.1:8000/restore", "POST", "HUMAN")


def test_redaction_covers_nested_and_configured_data(policy, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "super-secret-key-123")
    sanitizer = Sanitizer(policy.config)
    clean = sanitizer.clean({"password": "never-save", "nested": [{"token": "never-save"}], "message": "super-secret-key-123"})
    assert "never-save" not in json.dumps(clean)
    assert "super-secret-key-123" not in json.dumps(clean)
    policy.config["redaction_rules"]["mask_member_ids"] = True
    policy.config["redaction_rules"]["mask_financial_values"] = True
    assert Sanitizer(policy.config).clean("12345 2500.50") == "[MEMBER_ID] [BALANCE]"


def test_retry_policy_has_upper_bound(policy):
    assert policy.retry_limit(99) == 3
