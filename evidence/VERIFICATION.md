# Verification record

Updated 2026-09-22. Reviewed evidence comes from public commit `ba957a0`; the later manual failure is separately identified as operator-reported terminal output. No new test run or successful manual takeover is claimed by this documentation update. Paths below are relative to `evidence/`.

## Confirmed evidence

| Check | Evidence | Result |
|---|---|---|
| Anthropic discovery on live UI | `local-discover-38388153bd/` | PASS: `claude-haiku-4-5-20251001`; six proposals, five UI actions; member 12345 returned 2500.50 USD. |
| Historical bridge discovery | `discovery-live-01/` | PASS in original run: ChatGPT Work assistant supplied live-observation proposals through the bridge. Separate provenance from the current Anthropic artifact. |
| Current typed, versioned, parameterized artifact | `local-discover-38388153bd/capability.json`, `../capabilities/get_savings_balance/v1.json` | PASS: artifacts match; member input is bound by parameter rather than a literal discovery ID. |
| Historical different-input replay with model provider unavailable | `verified-replay/` | PASS: member 67890 returned 8100.25 USD with `LLM_PROVIDER=unavailable` and empty API key. |
| Local replay of current capability | `my-replay-01/` | PASS: member 67890 returned 8100.25 USD; log records `llm_decisions: false`. |
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
| Historical tests (2026-09-14) | `pytest-results.xml` | **35 passed in 40.45 seconds** in the original Linux environment; not a fresh run against the current artifact. Includes schema/input validation, policy, parameterization, redaction, replay import isolation, live browser scenarios, stale resume tokens and bounded handoff timeout. |

The `verified-*` scenario directories and original test report are historical build evidence. The later Anthropic discovery and `my-replay-01` have separate provenance. Unit/integration tests do not call an LLM API. The Anthropic and bridge discovery folders retain their own request/response evidence; bridge transport itself cannot cryptographically prove who supplied a response.

## Manual attempts that have not passed

| Run | Available evidence | Result |
|---|---|---|
| `my-human-handoff-01` | Published `my-human-handoff-01/summary.json` and events | FAIL: `AUTOMATION_ERROR`, timeout at step 001 before takeover; no human interaction events. |
| `manual-handoff-20260921-212447` | Operator-shared terminal output; generated path reported as `manual-handoff-20260921-212447/failure-31c730f8.json` | FAIL: reached `SESSION_EXPIRED` pause, then `CHECKPOINT_FAILED` at step 004: “Human left session outside known continuation checkpoints.” Full run files were not present in the reviewed commit; snapshot not inspected. |

The second attempt confirms reaching the pause and reporting a resume failure. It does not establish successful human restoration or end-to-end completion. Timing and manually advancing past the expected screen remain hypotheses until the snapshot is inspected.

## Remaining submission checks

1. **Complete a human-operated headed run.** Follow the README's unique-run-ID command. After Restore session, wait for Member details for 67890 and the Accounts iframe; leave the Savings account link for automation. Require final success, captured human actions, the ownership sequence, one session ID and a validated resume checkpoint. Retain failures honestly. The current immediate continuation check can reject loading or later screens; do not bypass it to manufacture a pass.
2. **Rerun tests against the current artifact.** Run `python -X utf8 -m pytest -v --junitxml=evidence/pytest-results-local.xml` from the repository root. Record actual counts, date, Python/Playwright/browser versions and OS after completion. No fresh local report has been supplied for this review.
3. **Commit reviewed evidence and consistent documentation.** Include the successful manual run and fresh test report once available. The Anthropic discovery folder is already tracked. Default `local-*` run directories are ignored; stage selected sanitized runs explicitly when needed. Keep `.env` and credentials out of Git.

## Environment and reproduction

- Original build/tests: Python 3.12.14, Linux, Playwright 1.62.0, portable Chromium 153.0.0 via `BROWSER_EXECUTABLE_PATH`; standard browser CDN was unavailable in that environment.
- Later operator runs: Windows PowerShell. Exact local Python, Playwright and browser versions were not supplied; do not infer them from dependency pins. Normal setup uses `python -m playwright install chromium`.
- Use `python -X utf8 -m ...` on Windows because some text-file operations still depend on the platform encoding.
- Local server only: `http://127.0.0.1:8000`.
- All member records and account amounts are synthetic. Name cells and input values were excluded from persisted snapshots; the original verification recorded no entered test password in its evidence corpus. Review newly generated evidence before publication.
- Run `python -X utf8 -m pytest -v --junitxml=evidence/pytest-results-local.xml` to reproduce tests and save a separate current report. Run `python -m scripts.demo_scenarios` to create a fresh timestamped set of noninteractive demos.
- `verified-index.json` contains historical scenario summaries. Each scenario directory contains `events.jsonl` and `summary.json`; exceptional states also contain a sanitized DOM-derived snapshot.
- Run IDs and session IDs identify actual runs. Evidence paths may include the original build directory; use the relative run directories in the repository when reviewing retained evidence on another machine.
