# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`2eb7454d349354592064c1a6859756230d4ea0a8`
- 当前 HEAD：`2eb7454d349354592064c1a6859756230d4ea0a8`（包含工作区内相关未提交修改）
- 范围：静态 System/Guard/Recovery Prompt、动态装配及与行为有关的硬编码策略。
- 安全：只读取 Git 源码和本地静态 Prompt；不访问银行数据库、密钥或模型 API。
- 审核状态：**待人工填写 UX 决策与行为证据；此文档不代表批准修改。**

## 1. 静态 System Prompt — Before / After

| 角色 | Before SHA-256 前16位 | After SHA-256 前16位 | 是否变化 |
|---|---|---|---|
| `SYSTEM_PROMPT` | `976ac34290cb8a39` | `976ac34290cb8a39` | 否 |
| `GUARD_SYSTEM_PROMPT` | `3637e17f6d8f8e21` | `3637e17f6d8f8e21` | 否 |
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
| `agent_loop` | `agent_loop:4a08dfc3d318c6fb` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:3637e17f6d8f8e21` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/compound_read_summary.py b/backend/app/agent/compound_read_summary.py
index e2bee65..4709879 100644
--- a/backend/app/agent/compound_read_summary.py
+++ b/backend/app/agent/compound_read_summary.py
@@ -21,2 +21,4 @@ _SKIP_DETECTION = re.compile(
     r"|(?:只|仅)(?:需|要)?(?:看|查|查询).{0,8}(?:交易|流水)"
+    r"|(?:不需要|不用|不要|不必|无需|无须|暂不).{0,5}(?:订阅|自动扣费|周期扣费)"
+    r"|订阅.{0,4}(?:不用|不要|下次|以后|暂不)"
 )
@@ -54,2 +56,32 @@ def _valid_rows(name: str, result: dict[str, Any]) -> list[dict] | None:

+def _requests_transaction_and_subscription(user_request: str) -> bool:
+    return (
+        any(cue in user_request for cue in _TRANSACTION_CUES)
+        and any(cue in user_request for cue in _SUBSCRIPTION_CUES)
+        and not _SKIP_DETECTION.search(user_request)
+    )
+
+
+def missing_read_goal_for_retry(
+    results: list[tuple[str, dict]], *, user_request: str,
+) -> str | None:
+    """Find one unattempted, explicit, low-risk read goal.
+
+    Do not retry a failed tool, extend a mixed/action task, or guess from
+    model-authored prose. An empty successful result counts as completed.
+    """
+    if (len(results) != 1 or any(action in user_request for action in (
+        "取消", "退订", "关闭", "转账", "汇款", "打款", "申购", "赎回",
+        "挂失", "冻结", "购买", "支付", "账单", "余额",
+        "卡片状态", "银行卡状态", "理财", "持仓", "风险测评",
+    ))):
+        return None
+    if not _requests_transaction_and_subscription(user_request):
+        return None
+    done, result = results[0]
+    if done not in _SUPPORTED or _valid_rows(done, result) is None:
+        return None
+    return (_DETECTION_TOOL if done == _TRANSACTION_TOOL else _TRANSACTION_TOOL)
+
+
 def summarize_transaction_subscription_review(
@@ -64,7 +96,3 @@ def summarize_transaction_subscription_review(
         return None
-    requested_both = (
-        any(cue in user_request for cue in _TRANSACTION_CUES)
-        and any(cue in user_request for cue in _SUBSCRIPTION_CUES)
-        and not _SKIP_DETECTION.search(user_request)
-    )
+    requested_both = _requests_transaction_and_subscription(user_request)
     observed = {name for name, _ in results}
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index 91be190..da829dd 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -10,3 +10,5 @@ from app.agent.llm import LLMProvider, get_llm
 from app.agent.prompt_assembly import assemble_agent_prompt
-from app.agent.compound_read_summary import summarize_transaction_subscription_review
+from app.agent.compound_read_summary import (
+    missing_read_goal_for_retry, summarize_transaction_subscription_review,
+)
 from app.agent.financial_summary import (
@@ -77,2 +79,3 @@ class AgentLoop:
         prior_calls: list[str] = []
+        continuation_target: str | None = None

@@ -88,2 +91,24 @@ class AgentLoop:
                 if not tool_calls:
+                    # Allow one model-directed chance to finish an explicit,
+                    # unattempted second read goal. No extra read permission,
+                    # automatic Tool execution, or unlimited retry is granted.
+                    missing_goal = missing_read_goal_for_retry(
+                        tool_results, user_request=original_request or "",
+                    )
+                    if (missing_goal is not None and continuation_target is None
+                            and intent_action is None
+                            and round_index < MAX_TOOL_ROUNDS - 1):
+                        continuation_target = missing_goal
+                        messages.append({
+                            "role": "system",
+                            "content": (
+                                "服务端只读任务覆盖检查：用户明确请求最近交易查询和疑似订阅识别。"
+                                f"已有可信结果只覆盖其中一项，尚未尝试的工具为 {missing_goal}。"
+                                "如有足够条件，请优先调用这个只读工具完成剩余目标。"
+                                "遵守现有权限与账户范围，不得执行写操作、不得重复已成功的查询。"
+                                "如无法查询或需要用户选择账户，请正常解释尚未完成的目标。"
+                                "不得把疑似周期扣费直接断言成重复订阅。"
+                            ),
+                        })
+                        continue
                     if tool_results:
@@ -197,2 +222,21 @@ class AgentLoop:
                     return
+                if (continuation_target is not None and (
+                        len(tool_calls) != 1
+                        or tool_calls[0]["function"]["name"] != continuation_target)):
+                    # The extra turn is authorized only to complete the single
+                    # remaining READ goal. Do not execute unrelated tools.
+                    partial = summarize_transaction_subscription_review(
+                        tool_results, user_request=original_request or "",
+                    )
+                    if partial is not None:
+                        answer = partial + "\n\n" + "\n\n".join(
+                            render_tool_result(name, result)
+                            for name, result in tool_results
+                        )
+                        yield AgentEvent("delta", {"text": answer})
+                    else:
+                        yield AgentEvent("error", {
+                            "message": "剩余查询未完成，请重试或缩小请求范围。",
+                        })
+                    return
                 messages.append({"role": "assistant", "content": mask_text("".join(content)) or None,
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
