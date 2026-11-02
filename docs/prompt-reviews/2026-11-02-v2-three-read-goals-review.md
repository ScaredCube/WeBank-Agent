# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`e5e1ab1ad048403d14aacc06695dea0be7a0db22`
- 当前 HEAD：`e5e1ab1ad048403d14aacc06695dea0be7a0db22`（包含工作区内相关未提交修改）
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
| `agent_loop` | `agent_loop:cbd48c90a8dcdab4` |
| `bill_followups` | `bill_followups:918b9b1404151a3b` |
| `bill_insights` | `bill_insights:7a0733828e8273bd` |
| `chat_request_recovery` | `chat_request_recovery:fa3094688f65cb35` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:03e814d7bb7ea71d` |
| `read_completion` | `read_completion:6d839f7daa46db59` |
| `read_goal_plan` | `read_goal_plan:2f916b286bed159c` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:beadee78807f200f` |
| `tool_executor` | `tool_executor:57745137ae0a760d` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index 435f943..fded42f 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -9,2 +9,3 @@ from app.agent.guard import GuardProvider, get_guard
 from app.agent.goal_completion import missing_bill_goal
+from app.agent.read_goal_plan import build_read_goal_plan
 from app.agent.bill_insights import summarize_bill_insights
@@ -100,5 +101,11 @@ class AgentLoop:
         attempted_nonread = False
+        read_plan = build_read_goal_plan(original_request or "")
+        plan_nudges = 0
+        plan_progress_len = 0
+        # An explicit three-part read may need two extra bounded clarification
+        # rounds when the model stops after each completed Tool call.
+        round_limit = MAX_TOOL_ROUNDS + (2 if read_plan is not None else 0)

         try:
-            for round_index in range(MAX_TOOL_ROUNDS + 1):
+            for round_index in range(round_limit + 1):
                 tool_calls: list[dict[str, Any]] | None = None
@@ -118,7 +125,13 @@ class AgentLoop:
                         tool_results, user_request=original_request or "",
-                    ))
-                    if (missing_goal is not None and continuation_target is None
+                    ) or (read_plan.next_unattempted(tool_results) if read_plan else None))
+                    can_nudge = (continuation_target is None or (
+                        read_plan is not None and plan_nudges < 2
+                        and len(tool_results) > plan_progress_len))
+                    if (missing_goal is not None and can_nudge
                             and intent_action is None
-                            and round_index < MAX_TOOL_ROUNDS - 1):
+                            and round_index < round_limit - 1):
                         continuation_target = missing_goal
+                        if read_plan is not None:
+                            plan_nudges += 1
+                            plan_progress_len = len(tool_results)
                         messages.append({
@@ -178,2 +191,3 @@ class AgentLoop:
                         )
+                        plan_summary = read_plan.report(tool_results) if read_plan else None
                         compound_summary = summarize_transaction_subscription_review(
@@ -181,3 +195,5 @@ class AgentLoop:
                         )
-                        if compound_summary is not None:
+                        if plan_summary is not None:
+                            summary = plan_summary
+                        elif compound_summary is not None:
                             # The summary states coverage and evidence limits.
@@ -206,2 +222,7 @@ class AgentLoop:
                             ))
+                        if (read_plan is not None and plan_summary is not None
+                                and len(read_plan.verified(tool_results)) == 3):
+                            yield AgentEvent("read_goal_coverage", {
+                                "goals": list(read_plan.verified(tool_results)),
+                            })
                         messages.append({"role": "assistant", "content": summary})
@@ -245,3 +266,3 @@ class AgentLoop:
                     return
-                if round_index == MAX_TOOL_ROUNDS or len(tool_calls) > MAX_CALLS_PER_ROUND:
+                if round_index == round_limit or len(tool_calls) > MAX_CALLS_PER_ROUND:
                     yield AgentEvent("error", {"message": "查询步骤过多，请简化请求后重试。"})
@@ -261,5 +282,6 @@ class AgentLoop:
                     # remaining READ goal. Do not execute unrelated tools.
-                    partial = summarize_transaction_subscription_review(
-                        tool_results, user_request=original_request or "",
-                    )
+                    partial = ((read_plan.report(tool_results) if read_plan else None)
+                               or summarize_transaction_subscription_review(
+                                   tool_results, user_request=original_request or "",
+                               ))
                     if partial is not None:
@@ -275,2 +297,13 @@ class AgentLoop:
                     return
+                if (read_plan is not None and any(
+                        call["function"]["name"] not in read_plan.goals
+                        for call in tool_calls)):
+                    partial = read_plan.report(tool_results)
+                    if partial is not None:
+                        yield AgentEvent("delta", {"text": partial})
+                    else:
+                        yield AgentEvent("error", {
+                            "message": "当前请求仅允许执行已明确提出的只读查询。",
+                        })
+                    return
                 messages.append({"role": "assistant", "content": mask_text("".join(content)) or None,
@@ -303,2 +336,5 @@ class AgentLoop:
                         tool_results.append((name, observation))
+                        if (read_plan is not None and name == continuation_target
+                                and observation.get("ok") is True):
+                            continuation_target = None
                         prior_calls.append(
@@ -316,5 +352,6 @@ class AgentLoop:
                     # spend the remaining rounds on a no-progress loop.
-                    partial = verified_partial_read_reply(
-                        tool_results, user_request=original_request or "",
-                    )
+                    partial = ((read_plan.report(tool_results) if read_plan else None)
+                               or verified_partial_read_reply(
+                                   tool_results, user_request=original_request or "",
+                               ))
                     if partial is not None:
@@ -329,5 +366,5 @@ class AgentLoop:
                 # otherwise produce redundant/unsafe tool calls without new value.
-                final_readonly_text = completed_readonly_summary(
+                final_readonly_text = (None if read_plan else completed_readonly_summary(
                     history, tool_results, user_request=original_request,
-                )
+                ))
                 if final_readonly_text is not None:
@@ -347,5 +384,6 @@ class AgentLoop:
             # the missing step or claim that a PREPARE operation succeeded.
-            partial = (verified_partial_read_reply(
-                tool_results, user_request=original_request or "",
-            ) if not attempted_nonread else None)
+            partial = (((read_plan.report(tool_results) if read_plan else None)
+                       or verified_partial_read_reply(
+                           tool_results, user_request=original_request or "",
+                       )) if not attempted_nonread else None)
             if partial is not None:
diff --git a/backend/app/api/routes/chat.py b/backend/app/api/routes/chat.py
index 6cac70a..7a4eefa 100644
--- a/backend/app/api/routes/chat.py
+++ b/backend/app/api/routes/chat.py
@@ -518,2 +518,3 @@ async def send_message(
         resumed_read_month=resumed_read_month,
+        resumed_read_kind=unfinished_read.kind if resumed_read_goal and unfinished_read else None,
         prior_bill_followup_summary=prior_bill_summary,
diff --git a/backend/app/services/chat_turn.py b/backend/app/services/chat_turn.py
index 318b6d5..ef40b60 100644
--- a/backend/app/services/chat_turn.py
+++ b/backend/app/services/chat_turn.py
@@ -57,2 +57,3 @@ class ChatTurn:
     resumed_read_month: str | None = None
+    resumed_read_kind: str | None = None
     prior_bill_followup_summary: str | None = None
@@ -88,2 +89,3 @@ async def stream_chat_turn(
     trusted_results: list[dict] = []
+    verified_read_goals: set[str] = set()
     ui_results: list[dict] = []
@@ -133,3 +135,9 @@ async def stream_chat_turn(
                 raise asyncio.CancelledError
-            if event.type == "delta":
+            if event.type == "read_goal_coverage":
+                goals = event.data.get("goals")
+                if (isinstance(goals, list) and set(goals) == {
+                        "get_monthly_bill", "list_recent_transactions",
+                        "detect_subscriptions"}):
+                    verified_read_goals.update(goals)
+            elif event.type == "delta":
                 text = event.data["text"]
@@ -288,3 +296,5 @@ async def stream_chat_turn(
                                         user_id=user_id, resumed_version=turn.resumed_read_version,
-                                        verified_months=verified_months, expected_month=expected_month)
+                                        verified_months=verified_months, expected_month=expected_month,
+                                        bundle_verified=(turn.resumed_read_kind == 'read_bundle'
+                                            and len(verified_read_goals) == 3))
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

## 4. UX rationale, evidence and risk decision

**Problem:** The previous Runtime had a single missing-bill retry and a
specific transactions-plus-subscription retry. An explicit three-goal user
request could finish after one or two reads because the model had no typed
coverage contract. A subsequent "continue" after account selection could
also resume only the bill and lose the other goals.

**Decision:** Build a bounded, typed three-read plan and preserve its canonical
`read_bundle` designation in the existing pending task. Only authenticated
Tool results count as coverage, so free-text statements from the model cannot
establish successful reads. The only new server-to-server signal,
`read_goal_coverage`, is emitted when all three observations are validated;
it is never derived from user text or exposed as a client financial receipt.

**UX:** A completed bundle has a truthful summary of the bill, the limited
recent transaction sample, the suspicious-recurring-payment scan, and their
different account/time scopes. A partial bundle explicitly names the
remaining unverified goal. The model may be nudged twice but is not forced to
retry a failed read, and it cannot use the nudge to prepare an unrelated action.

**Financial safety:** No model-authored balance, spending amount, subscription
cancellation or payment success is treated as proven. Transaction lists and
recurrence detection have different scopes. Current account selection is
revalidated by the service; previous selections do not authorize a transfer.
Cross-turn completion still requires a matching saved bill and now also a
verified three-goal coverage marker.

**Tests:** New unit/API tests demonstrate an entire three-read chain, model
premature closure, attempted unrelated financial operation, incomplete
results, and cross-turn resume/completion. The old read-goal, ToolExecutor,
risk policy and response-history tests remain in the regression scope.
No static SYSTEM, GUARD or RECOVERY Prompt literals were edited.

**Limit:** Only one explicitly defined three-part read combination is
supported. Per-goal persistent snapshots, arbitrary workflows and financial
action continuation are outside this change; additional combinations need
their own evidence semantics and tests.
