# Verification record

Prepared 2026-09-14. This file distinguishes executed evidence from implementation that needs local verification.

## Executed

| Check | Evidence | Result |
|---|---|---|
| Actual LLM-driven discovery on live UI | `discovery-live-01/` | PASS: ChatGPT Work assistant supplied six proposals through the external-model bridge; five UI actions were recorded. |
| Typed, versioned, parameterized artifact | `discovery-live-01/capability.json`, `../capabilities/get_savings_balance/v1.json` | PASS: no hard-coded discovery member ID in the artifact. |
| Different-input replay with model provider unavailable | `verified-replay/` | PASS: member 67890 returned 8100.25 USD with `LLM_PROVIDER=unavailable` and empty API key. |
| Member not found | `verified-not-found/` | PASS: business outcome `member_not_found`. |
| Slow load | `verified-slow-load/` | PASS: bounded condition wait, recovery event, successful output. |
| Session expiry without operator | `verified-session-unattended/` | PASS: intervention request, failure snapshot, no unsafe continuation. |
| Same-session handoff mechanism | `verified-handoff-simulated/` | PASS with **simulated operator**, not a human. One session ID; PAUSED → HUMAN → RESUMING → AUTOMATION; revalidated continuation; successful output. |
| Human-side action capture | `verified-handoff-simulated/events.jsonl` | PASS: input/change/click/navigation metadata; entered password absent from every evidence JSON/JSONL file. |
| Irreversible action policy | `verified-policy-block/` | PASS: Transfer Funds proposal rejected before execution. |
| Ambiguous link | `verified-ambiguous/` | PASS: duplicate View member targets caused intervention; neither was arbitrarily selected. |
| Permission denial | `verified-permission-denied/` | PASS: hard failure `PERMISSION_DENIED`. |
| Wrong-member protection | `verified-wrong-member/` | PASS: member checkpoint failed; no outputs returned. |
| Recovery exhaustion | `verified-recovery-exhausted/` | PASS: two additional waits, then `RECOVERY_EXHAUSTED`. |
| Unsupported application version | `verified-version-mismatch/` | PASS: stopped before task execution. |
| Tests | `pytest-results.xml` | **35 passed in 40.45 seconds**. Includes schema/input validation, policy, parameterization, redaction, replay import isolation, live browser scenarios, stale resume tokens and bounded handoff timeout. |

The unit/integration test suite does not call an LLM API. The discovery evidence is a separate real run whose choices were made by the ChatGPT assistant from the live observations. Bridge transport cannot cryptographically prove who supplied a response; the provenance statement is explicit rather than inferred from filenames.

## Still requiring local verification

1. **Anthropic API provider round trip:** implemented, but no model API credentials were present in this environment. Supply `LLM_MODEL` and `LLM_API_KEY` and run the README's discover command if API-provider evidence is desired. Do not describe the included bridge run as an Anthropic call.
2. **An actual person using the headed operator UI:** the browser/control-transfer mechanism was exercised by a simulated operator. Run the README's `--headed --handoff cli` command on a desktop and perform the takeover yourself. No human-operated demonstration is claimed here.
3. **Standard Playwright bundled Chromium on your platform:** the browser CDN was unavailable in the build environment. Live tests used Playwright 1.62.0 with portable Chromium 153.0.0 through `BROWSER_EXECUTABLE_PATH`. Normal setup instructions use `python -m playwright install chromium`.

## Environment and reproduction

- Python 3.12.14, Linux, Playwright 1.62.0; dependencies pinned in `requirements.txt`.
- Local server only: `http://127.0.0.1:8000`.
- All member records and account amounts are synthetic. Name cells and input values were excluded from persisted snapshots; no entered test password was found in the evidence corpus.
- Run `python -m pytest -v` to reproduce tests. Run `python -m scripts.demo_scenarios` to create a fresh timestamped set of noninteractive demos.
- `verified-index.json` contains the scenario summaries. Each scenario directory contains `events.jsonl` and `summary.json`; exceptional states also contain a sanitized DOM-derived snapshot.
- Run IDs and session IDs identify actual runs. Evidence paths may include the original build directory; the corresponding files are retained under this archive's `evidence/` directory.
