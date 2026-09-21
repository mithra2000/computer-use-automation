"""Code-enforced closed-world read-only policy, independent of model claims."""
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import yaml

from automation.errors import PolicyViolationError
from automation.models import Target


class PolicyEngine:
    def __init__(self, path: Path):
        self.config = yaml.safe_load(path.read_text())
        self.name = self.config["name"]

    def check_url(self, url: str, method: str = "GET", owner: str = "AUTOMATION"):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if parts.username or parts.password or origin not in self.config["allowed_origins"]:
            raise PolicyViolationError("Origin is outside the allowlist")
        path = unquote(parts.path)
        if not any(re.fullmatch(rule, path) for rule in self.config["allowed_routes"]):
            raise PolicyViolationError("Route is outside the allowlist")
        if set(parse_qs(parts.query)) - set(self.config["navigation_rules"]["allowed_query_keys"]):
            raise PolicyViolationError("Unapproved query parameter")
        if method not in {"GET", "HEAD"}:
            if not (method == "POST" and (path == "/enter" or (path == "/restore" and owner == "HUMAN"))):
                raise PolicyViolationError("Mutating request blocked")

    def check_target(self, target: Target):
        if target.frame and target.frame not in self.config["allowed_frames"]:
            raise PolicyViolationError("Unapproved frame")
        if target.table not in {None, "Member details", "Account summary", "Search results"}:
            raise PolicyViolationError("Unapproved table scope")
        key = target.role if target.strategy == "role" else target.strategy
        if target.strategy == "text":
            if target.name not in {"No member found", "Loading results…", "Invalid member ID"}:
                raise PolicyViolationError("Unapproved text condition")
            return
        if target.name not in self.config["allowed_controls"].get(key, []):
            raise PolicyViolationError("Control is not approved for read-only banking")

    def authorize(self, action: str, target: Target | None = None):
        if action not in self.config["allowed_action_types"]:
            raise PolicyViolationError("Action type is not allowed")
        if target:
            if any(word in target.name.lower() for word in self.config["blocked_action_categories"]):
                raise PolicyViolationError("Irreversible banking operation blocked")
            self.check_target(target)
        if action == "fill" and (not target or target.strategy != "label" or target.name != "Member ID"):
            raise PolicyViolationError("Only Member ID input may be filled")
        if action == "click" and (not target or target.strategy != "role" or target.role not in {"button", "link"}):
            raise PolicyViolationError("Click requires an approved interactive control")

    def retry_limit(self, requested: int) -> int:
        return min(requested, self.config["max_retries"] + 1)
