# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`31c5abae246545d6b4949d126239a150500e47b5`
- 当前 HEAD：`31c5abae246545d6b4949d126239a150500e47b5`（包含工作区内相关未提交修改）
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
| `agent_loop` | `agent_loop:181ba7569e2d2604` |
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
| `snapshot_contract` | `snapshot_contract:0979c55f1caf7bb0` |
| `tool_executor` | `tool_executor:57745137ae0a760d` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/context_assembly.py b/backend/app/agent/context_assembly.py
index f132e45..a2e9808 100644
--- a/backend/app/agent/context_assembly.py
+++ b/backend/app/agent/context_assembly.py
@@ -19,3 +19,3 @@ NoteSource = Literal[
     "validated_intent", "verified_object", "temporary_phone_reference",
-    "trusted_bill_context", "readonly_selection", "trusted_view_context",
+    "trusted_bill_context", "readonly_selection", "trusted_view_context", "pending_read_task",
 ]
@@ -24,3 +24,3 @@ _ALLOWED_NOTE_SOURCES = frozenset((
     "validated_intent", "verified_object", "temporary_phone_reference",
-    "trusted_bill_context", "readonly_selection", "trusted_view_context",
+    "trusted_bill_context", "readonly_selection", "trusted_view_context", "pending_read_task",
 ))
diff --git a/backend/app/api/routes/chat.py b/backend/app/api/routes/chat.py
index f5b0f40..16d3a1e 100644
--- a/backend/app/api/routes/chat.py
+++ b/backend/app/api/routes/chat.py
@@ -42,2 +42,5 @@ from app.services.conversation_context import (allow_readonly_followup, remember
 from app.services.intent_service import IntentError, build_intent_prompt
+from app.services.conversation_tasks import (
+    ReadGoal, can_resume_task, classify_pending_read_goal, pending_task, remember_pending_task,
+)
 from app.services.vault import VaultError, create_account_token, create_contact_token
@@ -264,2 +267,16 @@ async def send_message(
     injection = detect_injection(display_content)
+    # Only user-selected, presently verified accounts can resume an old read goal.
+    # The stored canonical task is neither a client instruction nor payment authority.
+    unfinished_read = pending_task(session, conversation_id=conversation_id, user_id=user.id)
+    resumed_read_goal = None
+    if (unfinished_read is not None and not injection.blocked and payload.intent is None
+            and view_snapshot is None and (selected_account is not None or selected_card is not None)
+            and can_resume_task(payload.content)):
+        resumed_read_goal = ReadGoal(unfinished_read.kind, unfinished_read.month).model_goal
+        trusted_notes.append(TrustedContextNote(
+            source="pending_read_task",
+            content=("[服务端保存的未完成只读目标：" + resumed_read_goal
+                     + "。本轮用户已补充并经服务端核验账户对象，仅允许完成只读查询；"
+                     "禁止将先前选择视为新的资金操作授权。]"),
+        ))
     view_selection = None
@@ -328,2 +345,10 @@ async def send_message(
                 detail="此请求已接收或结果尚未确定。请核对会话及操作记录，不要重复发起。")
+    # Remember the *canonical* missing read goal before model execution.
+    # A model/error fallback may otherwise lose it across the next turn.
+    if (not injection.blocked and payload.intent is None and view_snapshot is None
+            and not payload.references and selected_account is None and selected_card is None):
+        goal = classify_pending_read_goal(payload.content)
+        if goal is not None:
+            remember_pending_task(session, conversation_id=conversation_id,
+                                  user_id=user.id, goal=goal)
     phone_references: list[tuple[str, str]] = []
@@ -464,3 +489,3 @@ async def send_message(
         history=history,
-        original_request=prepared_context.original_request,
+        original_request=resumed_read_goal or prepared_context.original_request,
         verified=VerifiedToolContext(
diff --git a/backend/app/services/chat_turn.py b/backend/app/services/chat_turn.py
index f748871..07e71c3 100644
--- a/backend/app/services/chat_turn.py
+++ b/backend/app/services/chat_turn.py
@@ -21,2 +21,4 @@ from app.agent.ui_composer import get_ui_composer
 from app.services.chat_submissions import advance_submission
+from app.db.session import session_scope
+from app.services.conversation_tasks import mark_task_completed
 from app.services.security_service import record_failure
@@ -263,2 +265,9 @@ async def stream_chat_turn(
                                    trusted_results, view=context_view)
+        if message is not None and trusted_bill is not None:
+            # Clear pending READ goal only after its verified result was saved.
+            try:
+                with session_scope() as task_session:
+                    mark_task_completed(task_session, conversation_id=conversation_id, user_id=user_id)
+            except Exception:
+                logger.warning("pending read task finalization failed")
         yield encode({"type": "done", "message": message})
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。

## 4. Engineering / UX and safety evaluation

- **Reason for change:** A missing-account bill request previously survived only as ordinary text, so the next turn `继续` with a selected account had no server-verifiable task to resume.
- **Before:** Recent history and `ConversationSelection` retained some context, but no durable pending read goal existed.
- **After:** A canonical, time-limited `ConversationTask` record restores only a monthly-bill read objective when the new turn carries a freshly verified account. No user text is promoted to a trusted note. The task is closed only after persisted trusted bill evidence.
- **UX evidence:** The simulated conversation test verifies request → missing account → cross-turn account selection → resumed read Tool → completed persisted state.
- **Safety evidence:** Unrelated text and financial actions cannot activate task restoration; previously selected accounts never authorize payments. Private-data masking boundaries and read-only result presentation remain in force. A second language-model call is suppressed if the trusted result includes the privacy-mask marker.
- **Database:** The additive task table uses the existing explicit migration with backup; no silent migration on an existing SQLite instance.
- **Scope:** The static system, Guard and Recovery prompts were left unchanged. This is a change to the surrounding context/result orchestration and schema.
- **Evidence limitation:** Live DeepSeek smoke tests confirm the existing model, bill, SSE persistence and UI paths, while cross-turn completion is confirmed by deterministic end-to-end tests. Further real-model qualitative evaluation remains advisable before production usage.

This note records the reviewed rationale and observations; the branch has not been promoted to team main.
