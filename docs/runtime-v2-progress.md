# Agent Turn Runtime V2 — Integration checkpoint

Base: klutz-runtime@84243f6; implementation branch: v2/integrate.
Scope: synthetic banking demo, no writes to team main.

## Working vertical slices
1. One verified monthly-bill tool result can trigger a second tool-free model call for an explanatory response, with deterministic verified amounts retained and persisted as the assistant reply.
2. Missing explicit bill analysis goal after a successful but insufficient balance/read query can be nudged toward one further read-only Tool call.
3. A missing account query or unverified operation-status question can receive a separate, bounded natural-language clarification rather than only a canned script.
4. A validated UI category follow-up can receive a separate tool-free explanation; the service-generated category total remains authoritative.
5. Asset pointer drag to chat composer, @ mention of a holding, and holding-to-holding intent drag send typed object/intent data. Holding references are ownership-verified on the server and restricted to read-only context.
6. The existing structured CNY amount input ("转换金额：1000") is parsed as 100000 fen only when a service-validated intent is present.

## Verified
- Backend 117 tests + 31 subtests in core regression subset (before the later broadened view/holding changes).
- Backend 102 tests in the integrated read/intent/view/holding subset after latest changes.
- Browser Chrome Playwright V2 scenarios: 3 passed (drag-to-chat, @ holding, holding-to-holding intent and amount).
- Frontend TypeScript and targeted Vitest verified earlier in this checkpoint.
- A synthetic API integration test confirms the second model reply is stored in conversation history.
- Mock providers and synthetic bank data used; no live DeepSeek multi-turn evaluation yet.

## Unfinished, next critical work
1. Persistent cross-turn TaskState to resume unfinished tasks when a user supplies missing account/amount in a later message; text history alone is not a trusted task state.
2. Richer goal coverage beyond a bounded missing monthly-bill read; improve explanatory response under partial/failed tool data.
3. Actual agent+business confirmation/execute round trip for holding conversion and financial operations with real provider.
4. SSE interruption/recovery and historical status consistency from the screenshot incident.
5. Model-boundary sensitive-data sanitization, a deliberately deferred privacy milestone. Use synthetic data until complete.

## Integration discipline
- Avoid parallel backend pytest invocations sharing the same default temporary SQLite DB; each worktree needs isolated test DB or sequential runs.
- Do not change or merge team main implicitly.
- Do not remove existing ToolExecutor, risk checks, confirmation boundaries, or request_id idempotency.
- Limit tests to changed module + vertical contract per PR; run broad validation at merge milestones.
