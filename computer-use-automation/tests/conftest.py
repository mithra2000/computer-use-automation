from pathlib import Path
import pytest

from automation.cli import ROOT
from automation.local_server import local_server
from automation.policy import PolicyEngine


@pytest.fixture
def policy():
    return PolicyEngine(ROOT / "config/policy.yaml")


@pytest.fixture(scope="session")
def bank_server():
    with local_server():
        yield
