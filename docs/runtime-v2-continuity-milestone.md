# Runtime V2 · Durable read-task continuation milestone

Base: `origin/main@31c5aba`
Branch: `feature/agent-turn-v2-continuity`
Scope: synthetic/local banking demo; no changes to team main or production databases.

## What is implemented

- A server-owned `ConversationTask` record stores a canonical, time-limited pending read goal (monthly bill query or analysis) when a user has not selected an account.
- The stored record contains only task kind, optional normalized month, state, ownership and timestamp. No raw message, bank tokens, phone numbers or model-generated instruction are saved.
- A later user turn with a freshly verified account/card and an unambiguous brief continuation (such as “继续”) injects a bounded `pending_read_task` note. The Runtime then pursues the original read goal.
- Only an authenticated, persisted monthly bill result completes the pending task. Chat history remains unchanged; financial operations never inherit pending read goals.
- Pending goals expire after two hours; unrelated messages and financial operations do not consume the stored goal.
- A privacy guard in the existing independent read-result synthesizer declines a second model call if the deterministic trusted readout contains the protected-data marker. The existing deterministic fallback remains authoritative.

## Database migration boundary

This branch adds **one** SQLite table: `conversationtask`. Existing databases must **not** be silently modified. The schema guard intentionally refuses startup if the table is missing.

For a fresh isolated database, normal application startup bootstraps all tables.

For an existing *backed-up, offline, authorized demo database*, stop the service first, back up the file, then from the branch's `backend` directory run:

```powershell
uv run python scripts/check_chat_schema.py
uv run python scripts/check_chat_schema.py --apply
```

The second command performs a **second SQLite backup** and applies missing additive chat tables. Never run this against team or production databases without explicit authorization.

## Verification

- `test_v2_durable_read_task.py`: missing account → persisted task → next turn with verified account → bill Tool result → task completed; unrelated messages do not reactivate task.
- Existing owner/amount/Tool/response policy tests retain their protections.
- `scripts/check_v2_live_readonly.py` uses a fresh synthetic SQLite database and ephemeral vault keys for real DeepSeek smoke testing. Never logs API keys or raw financial data.

## Open work

- General multi-step task states and complex write-operation continuations; **no previous bank selection is payment authorization**.
- More robust goal-completion coverage, improved explanation quality, rich category follow-up, SSE interrupted result recovery.
- A separate privacy review of the original model-request sanitization gap before using real customer information.

## Local live smoke command

Use a local or explicitly supplied test-only environment file; never commit it:

```powershell
# From backend/
$env:XIAOWE_TEST_ENV_FILE = "C:\path\to\test-only.env"
python scripts/check_v2_live_readonly.py
```

The runner creates a separate temporary SQLite database and ephemeral test vault/JWT keys. It reports only HTTP/SSE status, completion flags, and response lengths, not model transcripts or secrets.

Latest branch verification: **590 backend tests + 31 subtests passed**, and a real model run on isolated synthetic data completed three turns, including bill results and UI revisions. This does not constitute production security certification or a general multi-step planner.

## Follow-up hardening (second commit candidate)

- A verified bill from an unrelated turn must not complete a previously unfinished goal. Completion now requires a **resumed task version** and a **persisted bill for the exact expected month**.
- A newer pending goal remains active if an earlier resumed request finishes later, avoiding stale-request completion.
- A single-month analysis fallback now derives the highest/second-highest consumption categories from validated bill aggregates, then explicitly distinguishes *distribution* from *cause*. The model still cannot certify amounts or transaction outcomes.
- Category names fail closed if they contain sensitive masking markers, unsupported characters, repeated labels, or category totals inconsistent with recorded consumption.
- The new `bill_insights.py` module is included in the runtime/prompt review hash manifest; static SYSTEM/GUARD prompts remain unchanged.
- Tests exercise unrelated-month reads, version mismatch, conservative numerical/category validation, and existing privacy and grounded financial explanations.

The second-stage outcome is a safer and more helpful **bounded monthly-bill** continuation. It does not yet implement general multi-goal planning or autonomous financial-operation resumption.

## Verified history-backed category follow-up

The real DeepSeek three-turn local smoke test showed a specific gap: the third turn asked about categories in the immediately prior bill, but the model did not issue another Tool call and its text had no authenticated category evidence.

An additional server-side read-only continuation path now handles **narrow previous-bill category questions**. It is activated only when the user refers to the earlier bill, the conversation's read-only account selection is revalidated, and the encrypted historical snapshot matches the selected account name/number and post-selection timestamp. The response is built from verified saved category aggregates and is persisted as a new ordinary assistant message.

This path never sends the historical private bill data to a second model call, never reuses bank operation credentials, and does not pretend a new live Tool query happened. Questions requesting causes, comparisons, transactions or financial actions stay on the normal Agent path. Users can explicitly request a fresh query.

Real DeepSeek smoke: all three turns ended in `done`; third-turn `verified_history_followup=True`. These checks use synthetic banking data and do not constitute a full general-purpose memory or planning system.
