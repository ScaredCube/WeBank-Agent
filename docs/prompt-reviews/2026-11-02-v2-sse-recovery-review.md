# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`c5110d01919bc81eeb75fe0247a63a6786d12191`
- 当前 HEAD：`c5110d01919bc81eeb75fe0247a63a6786d12191`（包含工作区内相关未提交修改）
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
| `chat_request_recovery` | `chat_request_recovery:fa3094688f65cb35` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:03e814d7bb7ea71d` |
| `read_completion` | `read_completion:6d839f7daa46db59` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:df28150fd22c66a8` |
| `tool_executor` | `tool_executor:57745137ae0a760d` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/api/routes/chat.py b/backend/app/api/routes/chat.py
index 807a4bc..6cac70a 100644
--- a/backend/app/api/routes/chat.py
+++ b/backend/app/api/routes/chat.py
@@ -147,3 +147,10 @@ def read_submission_status(
         "message": None,
+        "partial_message": None,
     }
+    if attempt.state in {"failed", "interrupted"} and attempt.assistant_message_id is not None:
+        partial = session.get(Message, attempt.assistant_message_id)
+        if partial is not None and partial.conversation_id == conversation_id and partial.role == "assistant":
+            # Explicitly distinguish an incomplete reply from a completed turn.
+            # Never return action confirmation tokens or model-only claims of success.
+            result["partial_message"] = present_message(session, partial).model_dump(mode="json")
     if attempt.state == "completed" and attempt.assistant_message_id is not None:
diff --git a/backend/app/services/chat_messages.py b/backend/app/services/chat_messages.py
index e4b60d3..456fcdf 100644
--- a/backend/app/services/chat_messages.py
+++ b/backend/app/services/chat_messages.py
@@ -60,3 +60,5 @@ def persist_assistant(conversation_id: int, content: str,
     if not content and not (tool_results or bill_result or card_result):
-        if submission_id is not None:
+        # A disconnected/incomplete stream uses finalize=False. An empty
+        # partial result must never mark the original request completed.
+        if submission_id is not None and finalize:
             advance_submission(submission_id=submission_id, state="completed")
diff --git a/backend/app/services/chat_turn.py b/backend/app/services/chat_turn.py
index 960c297..318b6d5 100644
--- a/backend/app/services/chat_turn.py
+++ b/backend/app/services/chat_turn.py
@@ -301,4 +301,11 @@ async def stream_chat_turn(
         else:
+            # Atomic link: the partial historical reply and request identity
+            # must be stored together, while the request remains interrupted.
+            try:
+                persist_assistant(conversation_id, "".join(collected),
+                                  trusted_bill, trusted_cards, trusted_results,
+                                  submission_id=submission_id, finalize=False)
+            except Exception:
+                logger.exception("interrupted chat result persistence failed")
             advance_submission(submission_id=submission_id, state="interrupted")
-            persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards, trusted_results)
         raise
@@ -306,4 +313,23 @@ async def stream_chat_turn(
         logger.exception("chat event stream failed")
+        partial_persisted = saved_message is not None
+        if saved_message is None and trusted_results:
+            # Preserve already authenticated Tool evidence if a later runtime,
+            # model or UI stage crashes. Do not mark the user goal complete.
+            try:
+                partial_persisted = persist_assistant(
+                    conversation_id,
+                    "".join(collected) + (
+                        "\n\n部分查询已取得可信结果，但后续步骤异常，"
+                        "请核对下方历史记录；不能据此认定其他任务完成。"
+                    ),
+                    trusted_bill, trusted_cards, trusted_results,
+                    submission_id=submission_id, finalize=False,
+                ) is not None
+            except Exception:
+                logger.exception("failed chat partial result persistence failed")
         advance_submission(submission_id=submission_id, state="failed")
-        yield encode({"type": "error", "message": "服务出现异常，请稍后再试。"})
+        yield encode({"type": "error", "message": (
+            "服务出现异常，请核对历史中已保存的部分结果。" if partial_persisted
+            else "服务出现异常，请稍后再试。"
+        )})
     finally:
diff --git a/frontend/src/features/chat/useChatController.ts b/frontend/src/features/chat/useChatController.ts
index 71e312a..ff9f468 100644
--- a/frontend/src/features/chat/useChatController.ts
+++ b/frontend/src/features/chat/useChatController.ts
@@ -84,5 +84,9 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
             clearPendingChatRequest(item.requestId)
-            recoveryWarning.current('此前请求已被服务端确认失败；如涉及模拟金融操作，仍需先核对历史与操作记录，再决定是否作为新请求发起。')
+            recoveryWarning.current(status.partial_message
+              ? '此前请求执行失败，但已经取得的可信部分结果已保存到历史。请核对历史和操作记录，不会自动重新执行。'
+              : '此前请求已被服务端确认失败；如涉及模拟金融操作，仍需先核对历史与操作记录，再决定是否作为新请求发起。')
           } else {
-            recoveryWarning.current('检测到尚未确认完成的历史请求，请先核对会话及操作记录，不要重复发起。')
+            recoveryWarning.current(status.state === 'interrupted' && status.partial_message
+              ? '此前请求已中断，但可信部分结果已保存在历史中；请核对未完成的步骤，不要重复发起资金操作。'
+              : '检测到尚未确认完成的历史请求，请先核对会话及操作记录，不要重复发起。')
           }
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。

## SSE response recovery: source-of-truth / safety assessment

The change preserves the established request-id and financial confirmation boundaries.
It fixes an empty non-final save that incorrectly marked a disconnected request as
completed, and links any recoverable partial assistant record (including encrypted
trusted Tool snapshots) to its original authenticated request.

The new status response uses `partial_message` only for `failed` or
`interrupted` requests, and retains `message` only for `completed` requests.
No financial confirmation or execution token is returned by this read-only
recovery endpoint, and the client does not automatically retry the original POST.
An error before any trusted evidence retains the generic error message and does
not claim that a partial result has been saved.

Verification includes synthetic post-Tool exceptions, transport interruption both
before and after the first trusted Tool result, request ownership, action idempotency,
and reload behavior. The static system, Guard, and Recovery prompt strings are
unchanged; the modified runtime services are included in the current manifest.
