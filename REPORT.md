# 1. Architecture

One Python process coordinates discovery or replay through the same SurfaceAdapter, PolicyEngine, EvidenceRecorder and SessionHandoffManager. A separate local FastAPI process supplies a synthetic legacy banking UI. The adapter performs every task read/action through Playwright; the automation never imports the app's member data. Tables, forms, a named account iframe and fault injection exercise more than a clean single-page happy path.

Discovery alone depends on a Provider. AnthropicProvider uses typed tool proposals through the Messages API. BridgeProvider allows an external tool-enabled LLM to consume live snapshots and return proposals through files. The included genuine discovery used the ChatGPT Work assistant through this bridge, not a scripted policy or an Anthropic API call. Each request/response and verified UI action is retained. The API adapter requires the submitter's credentials and was not live-tested here. Replay never imports discovery/provider modules; an integration test enforces that boundary.

# 2. Artifact schema

The strict Pydantic capability is a versioned contract: identity/version, profile reference, typed inputs/outputs, ordered actions, before/after checkpoints, outcome and recovery rules, policy reference, and provenance. Unknown fields and unsupported versions are rejected. Each action binds semantic targets and frame/table scope; fill uses the explicit member_id parameter rather than a recorded literal. Outputs use decimal strings and currency codes. The builder uses actual executed actions and UI checkpoints, excluding observation-only work; it does not attempt unsafe path minimization.

The persisted v1 capability comes from five real UI actions and a verified completion proposal. Model transcripts are separate evidence. Navigation resolves the app entry point at invocation time. Profile/policy/version compatibility is checked before replay. Artifact saves validate first and use atomic replacement; unsuccessful discovery preserves the preceding capability. New capability revisions are deliberate repository changes, not silent upgrades.

# 3. Determinism & error handling

Replay resolves exact role/name and label locators, plus scoped table rows inside a named frame. It requires one match and refuses ambiguity. Fixed locator rules and bounded condition polling replace model decisions. Retry budgets are capped by both artifact and external policy. Recovery extends checkpoint waits rather than blindly reissuing clicks; even safe state-changing session bootstrap actions are not repeated as an automatic timeout retry.

Before/after checkpoints verify headings and member bindings. Final verification independently checks the requested member in the outer details page and account iframe, the Savings account type, and validated balance/currency. A model completion claim cannot bypass these checks. member_not_found is a BUSINESS_OUTCOME; loading is recoverable within bounds; session expiry/ambiguity requires intervention; permission denial, incompatible versions, invalid contracts, wrong-member checkpoints and exhausted waits fail clearly. Structured results carry step, expected/observed state, error code and sanitized snapshot reference. Overall/step limits and repeated-state detection bound discovery; overall timeout and capped interventions bound replay.

# 4. Heterogeneity & multi-tenant

AppProfile separates vendor identity/version, deployment base URL, approved origins, entry point, capabilities and reviewed locator overrides from the reusable flow. Overrides are keyed by stable target descriptions and remain subject to policy. Unknown visible version markers stop the run. Another tenant can reuse the same capability family with an explicitly reviewed profile reference and supported version; the prototype does not implement a tenant registry or automatic profile inheritance. Do not discover unreviewed overrides during replay.

SurfaceAdapter is the perception/action boundary. A future desktop implementation would translate the same action and condition concepts into window/control accessibility identifiers, then approved visual anchors when necessary. It would need its own target types and an artifact schema migration, not a claim that web selectors work unchanged on desktop. The current browser implementation requires enough labels/table structure to identify controls; it intentionally does not claim arbitrary visual computer use or universal legacy compatibility.

# 5. Escalation & handoff

The ownership state machine is AUTOMATION → PAUSED → HUMAN → RESUMING → AUTOMATION, with terminal COMPLETED/FAILED states. Intervention requests preserve capability/goal, run/session IDs, step, reason, instructions and sanitized UI evidence. CLI mode keeps the same headed browser/context alive, lets a person restore the synthetic session, and waits for an explicit Enter/abort decision. Signal mode binds resume to the current intervention token. Adapter actions reject non-automation ownership; network policy remains active during takeover.

Owned event listeners capture human click/input/change metadata without input values; navigation is recorded separately. On resume, replay verifies the intended post-checkpoint or resumes at the earliest matching known pre-checkpoint. An unknown state fails safely. Discovery restarts its recording from entry after manual help so unrecorded human actions cannot become hidden capability dependencies. Tests exercise a real browser/context and ownership transfer with a clearly labelled simulated operator. An actual person's headed demonstration remains a local verification step. Native browser chrome, OS interactions and exact text edits are outside this recorder's coverage. Unattended mode emits a request and terminates rather than retaining an inaccessible session.

# 6. Safety

All proposals are untrusted structured data. There is no eval, model-supplied JavaScript, shell execution, arbitrary selector execution or unrestricted navigation. Models choose only target IDs in the current observation. Loaded artifacts remain subject to the same closed-world action/target policy. Exact origins, route patterns, query keys and request methods are checked; browser request interception blocks redirects and unauthorized requests, popups are closed, unexpected dialogs are dismissed and flagged, and service workers are disabled. Banking mutations are prohibited. Only human ownership permits the mock reauthentication POST.

The observation projection excludes input values and marked personal-name cells at source. Recursive redaction covers configured fields, known environment secrets, token-like text, and optional synthetic member/balance masking before persistence. Failure evidence uses structured DOM-derived snapshots instead of raw HTML/traces/screenshots. Outputs are returned to the caller but persisted under the evidence policy. This is a reviewed synthetic-app policy, not complete DLP, host isolation, or protection against arbitrary compromised application JavaScript. Production deployment needs institution-specific controls, authenticated operator access, stricter egress/session isolation and a data-retention policy.

# 7. Cuts

No full desktop automation, production tenant infrastructure, distributed orchestration, real banking authentication, advanced visual perception, automatic capability approval or LLM replay fallback was built. Those would dilute the main deliverable: actual goal discovery, a reusable typed artifact, independently verified deterministic replay, runtime outcome handling, enforced policy and same-session control transfer.

Next steps are a live API-provider run with the submitter's credentials, a recorded human-operated headed demo, reviewed artifact approval/signing, a second vendor/tenant variant, and richer desktop targeting. The supplied evidence distinguishes genuine external-model discovery from scripted test operators and does not represent unperformed demonstrations as completed work.
