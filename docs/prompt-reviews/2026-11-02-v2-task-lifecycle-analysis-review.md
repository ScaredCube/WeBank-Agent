# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`d6028266df81de770e3cf1b2570a71d3563225b8`
- 当前 HEAD：`d6028266df81de770e3cf1b2570a71d3563225b8`（包含工作区内相关未提交修改）
- 范围：静态 System/Guard/Recovery Prompt、动态装配及与行为有关的硬编码策略。
- 安全：只读取 Git 源码和本地静态 Prompt；不访问银行数据库、密钥或模型 API。
- 审核状态：**待人工填写 UX 决策与行为证据；此文档不代表批准修改。**

## 1. 静态 System Prompt — Before / After

| 角色 | Before SHA-256 前16位 | After SHA-256 前16位 | 是否变化 |
|---|---|---|---|
| `SYSTEM_PROMPT` | `976ac34290cb8a39` | `976ac34290cb8a39` | 否 |
| `GUARD_SYSTEM_PROMPT` | `03e814d7bb7ea71d` | `03e814d7bb7ea71d` | 否 |
| `RESPONSE_RECOVERY_PROMPT` | `b6fe66023300d62a` | `b6fe66023300d62a` | 否 |

### 静态 Prompt 原文差异

**SYSTEM_PROMPT**

```diff
(无变化)
```

**GUARD_SYSTEM_PROMPT**

```diff
(无变化)
```

**RESPONSE_RECOVERY_PROMPT**

```diff
(无变化)
```

## 2. 当前实际装配版本（不是模型表现评测）

| 装配入口 | Version |
|---|---|
| `agent` | `agent:976ac34290cb8a39` |
| `agent:collect` | `agent:cb004ee5d68762a7` |
| `agent:convert` | `agent:67b9da4bc7f8c6ba` |
| `agent:internal_transfer` | `agent:5f88f97514f7cec4` |
| `agent:purchase` | `agent:293f98322a40e2ce` |
| `agent:redeem` | `agent:99b476628139c9cc` |
| `agent:transfer` | `agent:5702dbd3ebea98b6` |
| `agent_loop` | `agent_loop:db2013b79837260c` |
| `bill_followups` | `bill_followups:918b9b1404151a3b` |
| `bill_insights` | `bill_insights:7a0733828e8273bd` |
| `chat_request_recovery` | `chat_request_recovery:7f69cdc969238d95` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:03e814d7bb7ea71d` |
| `read_completion` | `read_completion:6d839f7daa46db59` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:77cd6dd594731618` |
| `tool_executor` | `tool_executor:57745137ae0a760d` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index 3b7ce09..435f943 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -9,2 +9,3 @@ from app.agent.guard import GuardProvider, get_guard
 from app.agent.goal_completion import missing_bill_goal
+from app.agent.bill_insights import summarize_bill_insights
 from app.agent.llm import LLMProvider, get_llm
@@ -198,2 +199,3 @@ class AgentLoop:
                                 for name, result in tool_results)
+                        summary = (summarize_bill_insights(tool_results, request) or summary)
                         if should_synthesize_readoutcome(request, tool_results):
@@ -331,2 +333,4 @@ class AgentLoop:
                 if final_readonly_text is not None:
+                    final_readonly_text = (summarize_bill_insights(
+                        tool_results, original_request or "") or final_readonly_text)
                     if should_synthesize_readoutcome(original_request or "", tool_results):
diff --git a/backend/app/api/routes/chat.py b/backend/app/api/routes/chat.py
index 16d3a1e..807a4bc 100644
--- a/backend/app/api/routes/chat.py
+++ b/backend/app/api/routes/chat.py
@@ -45,2 +45,5 @@ from app.services.conversation_tasks import (
 )
+from app.services.bill_followups import (
+    asks_about_previous_bill_categories, verified_previous_bill_summary,
+)
 from app.services.vault import VaultError, create_account_token, create_contact_token
@@ -271,2 +274,4 @@ async def send_message(
     resumed_read_goal = None
+    resumed_read_version = None
+    resumed_read_month = None
     if (unfinished_read is not None and not injection.blocked and payload.intent is None
@@ -275,2 +280,4 @@ async def send_message(
         resumed_read_goal = ReadGoal(unfinished_read.kind, unfinished_read.month).model_goal
+        resumed_read_version = unfinished_read.updated_at
+        resumed_read_month = unfinished_read.month
         trusted_notes.append(TrustedContextNote(
@@ -483,2 +490,14 @@ async def send_message(
     history = prepared_context.model_messages()
+    prior_bill_summary = None
+    if (not injection.blocked and payload.intent is None and view_snapshot is None
+            and not payload.references and reused_readonly_selection
+            and selected_account is not None
+            and asks_about_previous_bill_categories(payload.content)):
+        selection = previously_selected(session, conversation_id=conversation_id, user_id=user.id)
+        if selection is not None and selection.account_id == selected_account.id:
+            prior_bill_summary = verified_previous_bill_summary(
+                session, conversation_id=conversation_id, user_id=user.id,
+                masked_number=selected_account.masked_number,
+                account_name=selected_account.name, selection_time=selection.updated_at,
+            )
     loop = AgentLoop()
@@ -490,2 +509,5 @@ async def send_message(
         original_request=resumed_read_goal or prepared_context.original_request,
+        resumed_read_version=resumed_read_version,
+        resumed_read_month=resumed_read_month,
+        prior_bill_followup_summary=prior_bill_summary,
         verified=VerifiedToolContext(
diff --git a/backend/app/services/chat_turn.py b/backend/app/services/chat_turn.py
index 07e71c3..960c297 100644
--- a/backend/app/services/chat_turn.py
+++ b/backend/app/services/chat_turn.py
@@ -6,2 +6,3 @@ from collections.abc import AsyncIterator, Awaitable, Callable
 from dataclasses import dataclass
+from datetime import datetime, timedelta, timezone
 from typing import Any, TypeVar
@@ -54,2 +55,5 @@ class ChatTurn:
     view_selection: dict | None = None
+    resumed_read_version: datetime | None = None
+    resumed_read_month: str | None = None
+    prior_bill_followup_summary: str | None = None

@@ -89,2 +93,9 @@ async def stream_chat_turn(
     try:
+        if turn.prior_bill_followup_summary is not None and not injection_blocked:
+            # Reuse the encrypted server-authored read snapshot, not the model's
+            # transcript. No fresh Tool call or operation authority is implied.
+            summary = turn.prior_bill_followup_summary
+            yield encode({"type": "delta", "text": summary})
+            yield encode({"type": "done", "message": finish_reply(summary)})
+            return
         if injection_blocked:
@@ -265,7 +276,15 @@ async def stream_chat_turn(
                                    trusted_results, view=context_view)
-        if message is not None and trusted_bill is not None:
-            # Clear pending READ goal only after its verified result was saved.
+        if message is not None and turn.resumed_read_version is not None:
+            # Only an explicitly resumed, matching bill can finish the task.
+            # Persisted Tool results are the authority; UI wording is not.
+            verified_months = {item['data']['month'] for item in trusted_results
+                if item['kind'] == 'monthly_bill' and isinstance(item.get('data'), dict)
+                and isinstance(item['data'].get('month'), str)}
+            expected_month = (turn.resumed_read_month or
+                utcnow().astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m'))
             try:
                 with session_scope() as task_session:
-                    mark_task_completed(task_session, conversation_id=conversation_id, user_id=user_id)
+                    mark_task_completed(task_session, conversation_id=conversation_id,
+                                        user_id=user_id, resumed_version=turn.resumed_read_version,
+                                        verified_months=verified_months, expected_month=expected_month)
             except Exception:
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。

## Verification of historical bill read boundary

The encrypted snapshot-based category follow-up addresses a source-of-truth gap: recent prose history is not enough to authorize a claim about a user's financial categories. The service now requires an owned conversation, current server-validated read-only account selection, account name and masked number equality, and a saved result later than that account's selection. The snapshot is decrypted and schema-validated and category aggregation is validated before a deterministic explanation is emitted. No raw snapshot data is sent to an independent wording model for this fast path.

Only narrow questions about the previous bill's categories use this path; causality, new-month comparisons, transfer intentions, stale identities and transaction-level questions continue into the ordinary bounded Runtime and Tool execution. Source-coded `bill_followups` is tracked by the effective-version manifest.

Synthetic API tests cover account/owner mismatch, stale-snapshot time, unsupported follow-up intentions and history persistence. Real DeepSeek local E2E reported a verified history category follow-up on the third turn without repeating a bank Tool call. This is an engineering/safety rationale and testing record rather than production compliance approval.
