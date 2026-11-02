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

## SSE request recovery: persisted partial evidence

This checkpoint hardens interrupted and crashed chat turns that already received
authenticated Tool results.

- A disconnected stream that has not reached the final persistence boundary
  now saves its partial assistant record and encrypted Tool snapshots **with the
  original ChatSubmission ID**, then marks the request `interrupted`. It is
  never considered a completed task and is never replayed.
- A later unexpected runtime error after verified Tool results attempts to
  persist the trusted partial snapshot and retains the submission state
  `failed`. The public SSE error is generic, not the internal traceback.
- `GET .../requests/{request_id}` returns `partial_message` only for
  `failed` and `interrupted` submissions which have a saved assistant row.
  The existing `message` field continues to mean an actually completed
  submission. Prepared financial actions still require their independent
  confirmation flow; no confirmation tokens are returned here.
- On reload, the front end distinguishes an incomplete but saved verified
  partial result from a failed request with no recoverable evidence. It never
  automatically repeats tool calls.

Focused synthetic fault-injection tests cover disconnect after a trusted bill,
exception after a trusted bill, and failure before any trusted data. All paths
keep their request status and account ownership checks. Client tests confirm
reload warnings are specific to incomplete-but-saved results.

This is a demo-readiness reliability improvement, not an exactly-once
distributed transaction guarantee or a complete SSE resumption protocol. The
client still retrieves status and persisted history rather than replaying raw
SSE frames.

## Real Chrome + FastAPI SSE transport checkpoint (verified)

This closes the earlier transport-level gap beyond mocked API/browser tests.

**Environment:** Windows LYJ-Laptop; independent local ports 8193 (actual FastAPI/uvicorn) and 5187 (Vite proxy); a new temporary SQLite database, ephemeral vault/JWT keys and a deterministic synthetic-only model. Real bank read Tool, authenticated HTTP routes, Server-Sent Events, result encryption/persistence and the browser's fetch/reload path run normally. No external model calls or financial write actions are used.

**Observed Playwright E2E:** 1/1 passed. The test submits a monthly-bill request, waits for the real bank Tool's trusted `bill_result`, then reloads the Chrome page while the backend is deliberately awaiting its next step. It checks:
- Request status resolves to `interrupted` rather than a false `completed` state.
- The interrupted request's `partial_message` contains the trusted CNY monthly bill snapshot.
- The conversation history contains exactly one saved assistant bill with the request-linked message ID.
- Reposting the identical `request_id` receives HTTP 409.
- The fixture Agent turn count remains exactly one; no duplicate tool processing.
- Browser recovery UI displays the incomplete saved-result message without JS errors.

**Reproduction, from two local terminals** (run only with synthetic data):
```powershell
# 1: from backend/
python scripts/sse_disconnect_fixture_server.py

# 2: from frontend/, with local dependencies installed
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8193'
npm run dev -- --host 127.0.0.1 --port 5187 --strictPort

# 3: separate terminal, from frontend/
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:5187'
$env:PLAYWRIGHT_CHANNEL = 'chrome'
$env:XIAOWE_REAL_FASTAPI_E2E = '1'
npx playwright test e2e/real-fastapi-disconnect.browser.cjs --workers=1
```

The fixture is bound to 127.0.0.1 and is for controlled development tests only. This establishes correctness for the tested cancellation boundary, **not** a general exactly-once distributed transaction guarantee.

## Multi-goal read-only plan (three explicit goals)

This checkpoint adds a narrowly bounded, typed `ReadGoalPlan` for a user
who **explicitly** requests monthly bills, recent transactions and suspected
recurring-payment detection together. The Runtime compares each actual Tool
result with the plan instead of taking a model-written "all done" as proof.

- Only these three read-only tools can participate. The model still proposes
  each call; the existing ToolExecutor revalidates account ownership and
  risk, and the plan will not execute a different Tool during continuation.
- A successful but incomplete result permits at most **two** extra targeted
  model nudges. A failed Tool is not silently retried and a model refusing
  to continue produces a grounded partial report.
- A completed report separates monthly bill aggregates, a limited recent
  transaction list and a broader suspected-recurring-payment scan. It never
  equates suspected recurrence with fraud, a confirmed duplicate charge,
  or cancellation of a subscription.
- The existing `ConversationTask` row can now retain a canonical
  `read_bundle` goal while an account is missing. When the user selects an
  account and continues, the full three-part goal is restored.
- A resumed bundle becomes `completed` only after **all three** Tool
  outcomes are verified and the matching bill is saved. A partial bill alone
  is insufficient. This changes no database tables.
- Other tasks, mixed requests containing financial actions, two-goal tasks
  and general-purpose planning keep their previous behavior. Existing bank
  authorization and confirmation boundaries are unchanged.

Tests include model premature completion, two bounded continuations,
attempted switch to a write Tool, partial/failing Tool evidence, missing
account then multi-goal resume, and rejection of premature task completion.

**Scope boundary:** This is a deliberately small, typed implementation of
multi-step read progress, not a generic user-directed workflow engine. Other
read combinations and persistent per-step snapshots remain future work.

## Single-month evidence matching in bounded three-goal plans

A monthly-bill Tool result now counts as completion only if it matches the user's canonical requested month. The plan recognizes explicit months (`2026-10`, `2026/10`, `2026年10月`) and the China-local relative phrases `本月`/`上个月`. Multi-month and ambiguous ranges use the established model/Tool path instead of being forced into a single-month plan. A wrong-month verified snapshot may be presented as a historical fact, but the requested bill goal remains incomplete. Regression coverage includes a three-Tool API call where the model retrieves an incorrect month.

## Real-model read-goal follow-up acceptance

The three-goal live smoke was extended with opt-in flags `XIAOWE_TEST_THREE_READ=1`, `XIAOWE_ONLY_THREE_READ=1` and `XIAOWE_TRACE_READ_TOOLS=1`. It runs with synthetic banking data in a separate temporary SQLite DB and ephemeral vault keys. Tracing prints only requested Tool **names**, not model text, arguments, banking data or keys.

Initial DeepSeek attempt returned a valid October bill but failed the transactions objective when two accounts were present. Root cause: the server-validated selected account was rebound for `get_monthly_bill` but not `list_recent_transactions`. ToolExecutor now binds the same verified account to all account-scoped READ tools (balance, monthly bill, latest transactions) and overrides any model-supplied account token. Direct tests show the second account stays isolated even when the model sends a stale first-account token.

After the fix, a new real DeepSeek triple-read test requested all three tools, reported `three_read_complete=True`, produced a 292-character response, and returned `bill_result` / `ui_view` / `done` with no SSE errors. This confirms the representative **synthetic** scenario, not every possible model response or production deployment.

Regression checkpoint: 607 backend tests + 31 subtests passed after account-scope and goal-month changes; the subsequent narrow cross-turn month normalization passed a further focused 18/18 task/plan/manifest tests. Real DeepSeek simulated three-goal smoke finished with `three_read_complete=True` and no SSE error.
