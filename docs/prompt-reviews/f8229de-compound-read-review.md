# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`f8229de4a6018cf46bd7c22fa57a6f419f7f80cd`
- 当前 HEAD：`f8229de4a6018cf46bd7c22fa57a6f419f7f80cd`（包含工作区内相关未提交修改）
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
| `compound_read_summary` | `compound_read_summary:eb96d91ed1194e2e` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:3637e17f6d8f8e21` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/compound_read_summary.py b/backend/app/agent/compound_read_summary.py
new file mode 100644
index 0000000..0286c1a
--- /dev/null
+++ b/backend/app/agent/compound_read_summary.py
@@ -0,0 +1,109 @@
+"""Grounded final summary for completed and partially completed read-only goals.
+
+We never summarize model-authored findings as bank facts. The transaction list
+and periodic-payment detector are two different evidence sources: the latter
+does not prove duplicate subscriptions, double charges, or fraud.
+"""
+from __future__ import annotations
+
+from typing import Any
+import re
+
+_TRANSACTION_TOOL = "list_recent_transactions"
+_DETECTION_TOOL = "detect_subscriptions"
+_SUPPORTED = frozenset({_TRANSACTION_TOOL, _DETECTION_TOOL})
+_TRANSACTION_CUES = ("交易", "流水", "明细", "收支记录")
+_SUBSCRIPTION_CUES = ("订阅", "周期扣费", "自动续费", "自动扣费", "重复扣", "重复支付")
+_SKIP_DETECTION = re.compile(
+    r"(?:无需|不用|不要|别|不必|不需要).{0,6}"
+    r"(?:查|看|识别|检测|检查|排查|核对).{0,10}"
+    r"(?:订阅|自动扣费|周期扣费|重复扣费|重复支付)"
+    r"|(?:只|仅)(?:需|要)?(?:看|查|查询).{0,8}(?:交易|流水)"
+)
+
+
+def _valid_rows(name: str, result: dict[str, Any]) -> list[dict] | None:
+    if not isinstance(result, dict) or result.get("ok") is not True:
+        return None
+    items = result.get("data")
+    limit = 50 if name == _TRANSACTION_TOOL else 10
+    if not isinstance(items, list) or len(items) > limit:
+        return None
+    if name == _TRANSACTION_TOOL:
+        if not all(
+            isinstance(item, dict)
+            and item.get("direction") in {"income", "expense"}
+            and type(item.get("amount_fen")) is int
+            and item["amount_fen"] >= 0
+            for item in items
+        ):
+            return None
+    else:
+        if not all(
+            isinstance(item, dict)
+            and isinstance(item.get("merchant"), str)
+            and type(item.get("occurrences")) is int
+            and item["occurrences"] >= 2
+            and type(item.get("amount_fen")) is int
+            and item["amount_fen"] >= 0
+            for item in items
+        ):
+            return None
+    return items
+
+
+def summarize_transaction_subscription_review(
+    results: list[tuple[str, dict]], *, user_request: str,
+) -> str | None:
+    """Only describe what has been verified; call out an explicitly missing goal.
+
+    Return None for other tool combinations or ordinary single-goal requests,
+    preserving the established presentation path.
+    """
+    if not results or any(name not in _SUPPORTED for name, _ in results):
+        return None
+    requested_both = (
+        any(cue in user_request for cue in _TRANSACTION_CUES)
+        and any(cue in user_request for cue in _SUBSCRIPTION_CUES)
+        and not _SKIP_DETECTION.search(user_request)
+    )
+    observed = {name for name, _ in results}
+    if not requested_both and observed != _SUPPORTED:
+        return None
+
+    # Repeated/malformed responses should not create a misleading "complete"
+    # verdict. The first successful, well-formed observation is authoritative.
+    verified: dict[str, list[dict]] = {}
+    for name, result in results:
+        rows = _valid_rows(name, result)
+        if rows is not None and name not in verified:
+            verified[name] = rows
+
+    descriptions: list[str] = []
+    transactions = verified.get(_TRANSACTION_TOOL)
+    detection = verified.get(_DETECTION_TOOL)
+    if transactions is not None:
+        descriptions.append(f"最近交易查询本次返回 {len(transactions)} 笔记录。")
+    elif requested_both:
+        descriptions.append("本轮尚未取得可核验的最近交易列表。")
+
+    if detection is not None:
+        if detection:
+            descriptions.append(
+                f"从近六个月的支出流水中识别到 {len(detection)} 项疑似周期性扣费线索。"
+            )
+        else:
+            descriptions.append("本轮未从近六个月的支出流水中识别到疑似周期性扣费线索。")
+    elif requested_both:
+        descriptions.append("本轮尚未完成可核验的周期性扣费识别。")
+
+    if not descriptions:
+        return None
+    descriptions.append(
+        "同一商户、同一金额跨月份出现，只能提示可能的订阅扣费；"
+        "不能单凭这些记录认定存在重复订阅或异常扣费。"
+        "建议对照订阅清单及扣费日期核实。"
+    )
+    if any(term in user_request for term in ("取消", "退订", "关闭订阅")):
+        descriptions.append("当前结果仅包含查询与识别，不代表已经取消任何订阅。")
+    return "".join(descriptions)
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index d78d24f..91be190 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -10,2 +10,3 @@ from app.agent.llm import LLMProvider, get_llm
 from app.agent.prompt_assembly import assemble_agent_prompt
+from app.agent.compound_read_summary import summarize_transaction_subscription_review
 from app.agent.financial_summary import (
@@ -130,3 +131,13 @@ class AgentLoop:
                         )
-                        if fully_supported and len(tool_results) > 1:
+                        compound_summary = summarize_transaction_subscription_review(
+                            tool_results, user_request=original_request or "",
+                        )
+                        if compound_summary is not None:
+                            # The summary states coverage and evidence limits.
+                            # Preserve the exact verified transaction details below.
+                            summary = compound_summary + "\n\n" + "\n\n".join(
+                                render_tool_result(name, result)
+                                for name, result in tool_results
+                            )
+                        elif fully_supported and len(tool_results) > 1:
                             summary = (summarize_bill_comparison(tool_results)
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
