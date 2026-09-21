"""Browser interaction boundary. Only application-owned static JS is evaluated."""
import asyncio
import hashlib
import json
import os
import re
import time
from urllib.parse import urlencode, urljoin, urlsplit

from playwright.async_api import TimeoutError as PlaywrightTimeout, async_playwright

from automation.errors import (AmbiguousTargetError, BusinessOutcome, CheckpointError,
    CompatibilityError, PermissionDeniedError, PolicyViolationError, RecoveryExhaustedError,
    SessionExpiredError, TargetNotFoundError)
from automation.models import Checkpoint, Condition, Inputs, Outputs, SessionState, Target

# Values are intentionally excluded at the source, including passwords and names.
OBSERVE_JS = """() => {
 const visible = e => !!(e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
 const controls = [...document.querySelectorAll('button,a,input:not([type=hidden])')].filter(visible).map(e => ({
   tag:e.tagName.toLowerCase(), type:e.type || '', name:e.labels?.[0]?.innerText?.trim() || e.getAttribute('aria-label') || e.innerText.trim(),
   has_value: e.type === 'password' ? false : !!e.value
 }));
 const rows = [...document.querySelectorAll('table tr')].filter(visible).map(r => [...r.children].map(e => e.hasAttribute('data-sensitive') ? '[REDACTED]' : e.innerText.trim()));
 return {headings:[...document.querySelectorAll('h1')].filter(visible).map(e=>e.innerText.trim()), controls, rows,
 statuses:[...document.querySelectorAll('[role=status],[role=alert]')].filter(visible).map(e=>e.innerText.trim())};
}"""

CAPTURE_JS = """(() => {
 const send = (type,e) => {
   const t=e.target;
   if (!t || !window.recordHumanEvent) return;
   const label=t.labels?.[0]?.innerText || t.getAttribute?.('aria-label') || (t.tagName==='BUTTON' ? t.innerText : '') || t.tagName;
   window.recordHumanEvent({event_type:type, target:String(label).slice(0,80), tag:t.tagName,
       value_metadata:type==='click' ? null : '[REDACTED]', path:location.pathname}).catch(()=>{});
 };
 document.addEventListener('click', e=>send('click',e),true);
 document.addEventListener('input', e=>send('input',e),true);
 document.addEventListener('change', e=>send('change',e),true);
})()"""


def target_id(target: Target) -> str:
    return hashlib.sha256(target.model_dump_json().encode()).hexdigest()[:12]


class SurfaceAdapter:
    def __init__(self, profile, policy, evidence, *, headed=False, scenario="normal"):
        self.profile, self.policy, self.evidence = profile, policy, evidence
        self.headed, self.scenario = headed, scenario
        self.owner = SessionState.AUTOMATION
        self.blocked_reason = None
        self.catalog: dict[str, Target] = {}
        self.page = None

    async def __aenter__(self):
        self.pw = await async_playwright().start()
        try:
            self.browser = await self.pw.chromium.launch(headless=not self.headed,
                executable_path=os.environ.get("BROWSER_EXECUTABLE_PATH") or None,
                args=["--disable-dev-shm-usage"])
            self.context = await self.browser.new_context(service_workers="block", accept_downloads=False)
            await self.context.route("**/*", self._route)
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.policy.config["action_timeout_ms"])
            self.context.on("page", self._popup)
            self.page.on("dialog", self._dialog)
            self.page.on("framenavigated", self._navigation)
            await self.context.expose_binding("recordHumanEvent", self._human_event)
            await self.context.add_init_script(CAPTURE_JS)
            return self
        except Exception:
            await self.pw.stop()
            raise

    async def __aexit__(self, *exc):
        await self.context.close()
        await self.browser.close()
        await self.pw.stop()

    async def _route(self, route):
        try:
            self.policy.check_url(route.request.url, route.request.method, self.owner.value)
            await route.continue_()
        except PolicyViolationError as error:
            self.blocked_reason = str(error)
            self.evidence.event("network_blocked", error_code=error.code)
            await route.abort("blockedbyclient")

    async def _popup(self, page):
        self.blocked_reason = "Unexpected window blocked"
        await page.close()

    async def _dialog(self, dialog):
        self.blocked_reason = "Unexpected dialog dismissed; explicit intervention needed"
        self.evidence.event("dialog_blocked", dialog_type=dialog.type)
        await dialog.dismiss()

    def _navigation(self, frame):
        if self.owner == SessionState.HUMAN:
            self.evidence.event("human_action", event_type="navigation", path=urlsplit(frame.url).path)

    def _human_event(self, source, event):
        if self.owner == SessionState.HUMAN:
            # Source-side values are excluded; only bounded, sanitized metadata survives.
            self.evidence.event("human_action", **{k: event.get(k) for k in ["event_type", "target", "tag", "value_metadata", "path"]})

    def assert_owner(self):
        if self.owner != SessionState.AUTOMATION:
            raise PolicyViolationError("Automation does not own this session")
        if self.blocked_reason:
            raise PolicyViolationError(self.blocked_reason)

    async def navigate(self):
        self.assert_owner()
        self.policy.authorize("navigate")
        url = urljoin(self.profile.base_url, self.profile.entry_point)
        if self.scenario != "normal":
            url += "?" + urlencode({"scenario": self.scenario})
        self.policy.check_url(url)
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.compatibility()

    async def compatibility(self):
        self.policy.check_url(self.page.url)
        marker = self.profile.compatibility_rules["visible_marker"]
        if not await self.page.get_by_text(marker, exact=True).is_visible():
            raise CompatibilityError("Application identity/version does not match profile")

    def root(self, target: Target):
        if target.frame:
            frames = [f for f in self.page.frames if f.name == target.frame]
            if len(frames) > 1:
                raise AmbiguousTargetError("Multiple matching frames")
            if not frames:
                raise TargetNotFoundError("Frame not found")
            return frames[0]
        return self.page

    def locator(self, target: Target):
        self.policy.check_target(target)
        target = self.profile.locator_overrides.get(target_id(target), target)
        self.policy.check_target(target)
        root = self.root(target)
        if target.strategy == "role":
            return root.get_by_role(target.role, name=target.name, exact=True)
        if target.strategy == "label":
            return root.get_by_label(target.name, exact=True)
        if target.strategy == "text":
            return root.get_by_text(target.name, exact=True)
        base = root.get_by_role("table", name=target.table, exact=True) if target.table else root.locator("table")
        return base.locator("tr").filter(has=root.locator("th").filter(has_text=re.compile("^" + re.escape(target.name) + "$"))).locator("td")

    async def locate(self, target: Target, timeout_ms: int | None = None):
        loc = self.locator(target)
        try:
            await loc.first.wait_for(state="visible", timeout=timeout_ms or self.policy.config["action_timeout_ms"])
        except PlaywrightTimeout as exc:
            raise TargetNotFoundError("Target did not become visible", expected=target.name, observed="absent or hidden") from exc
        if await loc.count() != 1:
            raise AmbiguousTargetError("Target is not unique", expected="one control", observed=f"{await loc.count()} matches")
        return loc

    async def click(self, target: Target):
        self.assert_owner()
        self.policy.authorize("click", target)
        loc = await self.locate(target)
        # Guard concrete destinations before clicking, in addition to request interception.
        href = await loc.get_attribute("href")
        if href:
            self.policy.check_url(urljoin(self.root(target).url, href))
        await loc.click()
        self.assert_owner()

    async def fill(self, target: Target, inputs: Inputs, binding: str):
        self.assert_owner()
        self.policy.authorize("fill", target)
        if binding != "member_id":
            raise PolicyViolationError("Unknown input binding")
        await (await self.locate(target)).fill(inputs.member_id)

    async def extract(self, target: Target) -> str:
        self.policy.authorize("extract", target)
        loc = await self.locate(target)
        return (await loc.input_value() if target.strategy == "label" else await loc.inner_text()).strip()

    async def check(self, condition: Condition, inputs: Inputs) -> bool:
        self.policy.authorize("check", condition.target)
        try:
            loc = self.locator(condition.target)
            count = await loc.count()
            if count > 1:
                raise AmbiguousTargetError("Checkpoint target is ambiguous", expected="one match", observed=str(count))
            if count == 0 or not await loc.is_visible():
                return False
            if condition.operator == "visible":
                return True
            value = await loc.input_value() if condition.target.strategy == "label" else await loc.inner_text()
            expected = inputs.member_id if condition.operator == "equals_input" else condition.value
            return value.strip() == expected
        except TargetNotFoundError:
            return False

    async def matches(self, checkpoint: Checkpoint, inputs: Inputs) -> bool:
        for condition in checkpoint.conditions:
            if not await self.check(condition, inputs):
                return False
        return True

    async def exceptional(self, outcome_rules=()):
        self.assert_owner()
        for rule in outcome_rules:
            if await self.check(rule.condition, Inputs(member_id="00000")):
                raise BusinessOutcome(rule.code)
        if await self.page.get_by_role("heading", name="Session expired", exact=True).is_visible():
            raise SessionExpiredError("Session expired")
        if await self.page.get_by_role("heading", name="Access denied", exact=True).is_visible():
            raise PermissionDeniedError("Application denied account access")
        if await self.page.get_by_text("Invalid member ID", exact=True).is_visible():
            raise CheckpointError("Application rejected input", observed="Invalid member ID")

    async def wait_for_condition(self, checkpoint, inputs, *, attempts=3, timeout_ms=None, outcome_rules=()):
        self.policy.authorize("wait")
        timeout_ms = min(timeout_ms or self.policy.config["action_timeout_ms"], self.policy.config["max_action_timeout_ms"])
        for attempt in range(self.policy.retry_limit(attempts)):
            end = time.monotonic() + timeout_ms / 1000
            while time.monotonic() < end:
                await self.exceptional(outcome_rules)
                if await self.matches(checkpoint, inputs):
                    self.evidence.event("checkpoint", checkpoint=checkpoint.name, result="passed")
                    return
                await asyncio.sleep(0.05)  # Poll a condition; never use a fixed delay to infer success.
            if attempt + 1 < self.policy.retry_limit(attempts):
                self.evidence.event("recovery_attempt", checkpoint=checkpoint.name, attempt=attempt + 1,
                                    result="recoverable_error", strategy="bounded_wait")
        raise RecoveryExhaustedError("Checkpoint wait exhausted", expected=checkpoint.name, observed="condition not satisfied within bound")

    async def observe(self):
        frames, catalog = [], {}
        for frame in self.page.frames:
            if frame != self.page.main_frame and frame.name not in self.policy.config["allowed_frames"]:
                continue
            data = await frame.evaluate(OBSERVE_JS)
            name = frame.name if frame != self.page.main_frame else None
            for control in data["controls"]:
                if control["type"] == "password":
                    continue
                target = Target(strategy="label" if control["tag"] == "input" else "role", name=control["name"],
                                role=None if control["tag"] == "input" else ("link" if control["tag"] == "a" else "button"), frame=name)
                key = target_id(target)
                control["target_id"] = key
                catalog[key] = target
            frames.append({"frame": name, **data})
        self.catalog = catalog
        return self.evidence.sanitizer.clean({"path": urlsplit(self.page.url).path, "frames": frames,
            "targets": {k: v.model_dump() for k, v in catalog.items()}})

    async def checkpoint_here(self, inputs: Inputs, *, filled=False) -> Checkpoint:
        observation = await self.observe()
        conditions, names = [], []
        for frame in observation["frames"]:
            for heading in frame["headings"]:
                conditions.append(Condition(target=Target(strategy="role", role="heading", name=heading, frame=frame["frame"])))
                names.append(heading)
        main_heading = observation["frames"][0]["headings"]
        if "Search results" in main_heading:
            conditions.append(Condition(target=Target(strategy="role", role="link", name="View member")))
        if "Member details" in main_heading:
            conditions.append(Condition(target=Target(strategy="table_cell", name="Member ID", table="Member details"), operator="equals_input", parameter="member_id"))
        if filled:
            conditions.append(Condition(target=Target(strategy="label", name="Member ID"), operator="equals_input", parameter="member_id"))
        if not conditions:
            raise CheckpointError("No stable checkpoint in this UI state")
        checkpoint = Checkpoint(name=" / ".join(names) + (" / input-bound" if filled else ""), conditions=conditions)
        await self.wait_for_condition(checkpoint, inputs, attempts=1)
        return checkpoint

    async def verify_outputs(self, inputs: Inputs, definitions) -> Outputs:
        await self.compatibility()
        for target in [Target(strategy="table_cell", name="Member ID", table="Member details"),
                       Target(strategy="table_cell", name="Member ID", table="Account summary", frame="accounts")]:
            if await self.extract(target) != inputs.member_id:
                raise CheckpointError("Returned account belongs to another member", expected="requested member", observed="member mismatch")
        if await self.extract(Target(strategy="table_cell", name="Account type", table="Account summary", frame="accounts")) != "Savings":
            raise CheckpointError("Account is not savings")
        return Outputs(**{key: await self.extract(value.source) for key, value in definitions.items()})
