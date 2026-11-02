# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`03426ceefa32e425452108195ea2ea9eb872c876`
- 当前 HEAD：`03426ceefa32e425452108195ea2ea9eb872c876`（包含工作区内相关未提交修改）
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
| `agent_loop` | `agent_loop:bd9b3523b46c09a5` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:3637e17f6d8f8e21` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index da829dd..3fae322 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -17,2 +17,5 @@ from app.agent.financial_summary import (
 from app.agent.read_completion import completed_readonly_summary
+from app.agent.read_result_recovery import (
+    CACHEABLE_READ_TOOLS, read_cache_key, verified_partial_read_reply,
+)
 from app.agent.response_policy import (
@@ -78,4 +81,6 @@ class AgentLoop:
         tool_results: list[tuple[str, dict]] = []
+        read_cache: dict[tuple[str, str], dict] = {}
         prior_calls: list[str] = []
         continuation_target: str | None = None
+        attempted_nonread = False

@@ -243,13 +248,33 @@ class AgentLoop:
                                  "tool_calls": mask_value(tool_calls)})
+                executed_count = 0
                 for call in tool_calls:
-                    outcome = await executor.execute(call, trusted, prior_calls)
-                    for event in outcome.events:
-                        yield AgentEvent(event.type, event.data)
-                    if outcome.stop_reason:
-                        return
-                    # Approval tokens travel only in client events; all other
-                    # Tool observations can safely be supplied to the model.
-                    if outcome.observation is None:
-                        raise RuntimeError("Nonterminal Tool execution had no observation")
                     name = call["function"]["name"]
+                    cache_key = (read_cache_key(name, call["function"]["arguments"])
+                                 if not attempted_nonread else None)
+                    if cache_key is not None and cache_key in read_cache:
+                        # Satisfy the model tool_call_id without re-executing or
+                        # duplicating SSE cards, audits or trusted result rows.
+                        observation = read_cache[cache_key]
+                    else:
+                        if name not in CACHEABLE_READ_TOOLS:
+                            attempted_nonread = True
+                            # A write or dynamic Tool may change state. Never
+                            # serve earlier read snapshots after it is attempted.
+                            read_cache.clear()
+                        outcome = await executor.execute(call, trusted, prior_calls)
+                        executed_count += 1
+                        for event in outcome.events:
+                            yield AgentEvent(event.type, event.data)
+                        if outcome.stop_reason:
+                            return
+                        # Approval tokens travel only in client events.
+                        if outcome.observation is None:
+                            raise RuntimeError("Nonterminal Tool execution had no observation")
+                        observation = outcome.observation
+                        tool_results.append((name, observation))
+                        prior_calls.append(
+                            f"{name}:{'success' if observation.get('ok') else 'denied'}"
+                        )
+                        if cache_key is not None and observation.get("ok") is True:
+                            read_cache[cache_key] = observation
                     messages.append({
@@ -257,8 +282,17 @@ class AgentLoop:
                         "tool_call_id": mask_text(call["id"]),
-                        "content": json.dumps(outcome.observation, ensure_ascii=False),
+                        "content": json.dumps(observation, ensure_ascii=False),
                     })
-                    tool_results.append((name, outcome.observation))
-                    prior_calls.append(
-                        f"{name}:{'success' if outcome.observation.get('ok') else 'denied'}"
+                if executed_count == 0:
+                    # Model repeated only already verified read calls. Do not
+                    # spend the remaining rounds on a no-progress loop.
+                    partial = verified_partial_read_reply(
+                        tool_results, user_request=original_request or "",
                     )
+                    if partial is not None:
+                        yield AgentEvent("delta", {"text": partial})
+                    else:
+                        yield AgentEvent("error", {
+                            "message": "查询没有取得新的可信结果，请简化请求后重试。",
+                        })
+                    return
                 # When the requested verified read-only results are already complete,
@@ -273,3 +307,12 @@ class AgentLoop:
         except Exception:
-            yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
+            # The provider or a later READ tool can fail after earlier tools
+            # succeeded. Preserve those verified observations; never invent
+            # the missing step or claim that a PREPARE operation succeeded.
+            partial = (verified_partial_read_reply(
+                tool_results, user_request=original_request or "",
+            ) if not attempted_nonread else None)
+            if partial is not None:
+                yield AgentEvent("delta", {"text": partial})
+            else:
+                yield AgentEvent("error", {"message": "模型服务暂时不可用，请稍后再试。"})
             return
diff --git a/backend/app/agent/read_result_recovery.py b/backend/app/agent/read_result_recovery.py
new file mode 100644
index 0000000..59d755f
--- /dev/null
+++ b/backend/app/agent/read_result_recovery.py
@@ -0,0 +1,62 @@
+"""Bounded reuse and verified partial-read fallback for Agent turns.
+
+A cached observation is specific to *one turn* and only to exact canonical
+arguments. This module never grants bank access; ToolExecutor authorizes the
+first execution, and only successful read-only observations are reusable.
+"""
+from __future__ import annotations
+
+import json
+from typing import Any
+
+from app.agent.compound_read_summary import summarize_transaction_subscription_review
+from app.tools.presentation import render_tool_result
+
+# Exclude dynamic action progress and balances, mutable subscriptions, and
+# any prepare/execute tools. Only these stable-in-turn read snapshots are reused.
+CACHEABLE_READ_TOOLS = frozenset({
+    "get_monthly_bill", "get_card_status",
+    "list_recent_transactions", "detect_subscriptions",
+})
+
+
+def read_cache_key(name: str, argument_json: str) -> tuple[str, str] | None:
+    if name not in CACHEABLE_READ_TOOLS:
+        return None
+    try:
+        arguments = json.loads(argument_json)
+    except (TypeError, ValueError):
+        return None
+    if not isinstance(arguments, dict):
+        return None
+    return (name, json.dumps(arguments, sort_keys=True, ensure_ascii=False,
+                             separators=(",", ":")))
+
+
+def verified_partial_read_reply(
+    results: list[tuple[str, dict[str, Any]]], *,
+    user_request: str,
+) -> str | None:
+    """Use only successful bank READ observations; never certify a failed goal."""
+    successful = [
+        (name, result) for name, result in results
+        if name in CACHEABLE_READ_TOOLS
+        and isinstance(result, dict) and result.get("ok") is True
+    ]
+    if not successful:
+        return None
+    compound = summarize_transaction_subscription_review(
+        successful, user_request=user_request,
+    )
+    rendered = []
+    for name, result in successful:
+        try:
+            text = render_tool_result(name, result)
+        except (TypeError, KeyError, IndexError, ValueError):
+            continue
+        if text:
+            rendered.append(text)
+    if not rendered:
+        return None
+    lead = "本轮部分只读查询已完成；其余步骤未能核实，请不要据此认定全部任务完成。"
+    return lead + "\n\n" + (compound + "\n\n" if compound else "") + "\n\n".join(rendered)
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
