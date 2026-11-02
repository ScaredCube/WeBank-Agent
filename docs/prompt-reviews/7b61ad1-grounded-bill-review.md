# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`7b61ad1fe4eda8686ccaaff648d4113046e0fea9`
- 当前 HEAD：`7b61ad1fe4eda8686ccaaff648d4113046e0fea9`（包含工作区内相关未提交修改）
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
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:3637e17f6d8f8e21` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/financial_summary.py b/backend/app/agent/financial_summary.py
index a6d7e2d..30bc19a 100644
--- a/backend/app/agent/financial_summary.py
+++ b/backend/app/agent/financial_summary.py
@@ -1,5 +1,53 @@
-"""Deterministic narration of multiple trusted monthly bill tool results.
+"""Grounded and privacy-conscious comparison of two verified monthly bills.

-Amounts in this text must originate from validated Tool data, never the model.
+A category difference is evidence about where consumption changed; it is not
+proof of *why* the customer spent more. Figures stay in protected result cards.
 """
+import re
+
+_MONTH = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
+_CATEGORY = re.compile(r"^(?:[\u4e00-\u9fff]{1,16}|[A-Za-z][A-Za-z _/\-]{0,20})$")
+
+
+def _category_amounts(data: dict) -> dict[str, int] | None:
+    rows = data.get("categories")
+    consumption = data.get("consumption_fen")
+    if not isinstance(rows, list) or type(consumption) is not int or consumption < 0:
+        return None
+    amounts: dict[str, int] = {}
+    for row in rows:
+        if not isinstance(row, dict):
+            return None
+        category, amount = row.get("category"), row.get("amount_fen")
+        if (not isinstance(category, str) or not _CATEGORY.fullmatch(category)
+                or type(amount) is not int or amount < 0 or category in amounts):
+            # Never surface arbitrary category text or infer partial-category causes.
+            return None
+        amounts[category] = amount
+    if sum(amounts.values()) != consumption:
+        return None
+    return amounts
+
+
+def incomplete_bill_comparison(results: list[tuple[str, dict]], request: str) -> str | None:
+    """Do not mistake a single monthly bill for an explanation of growth."""
+    if not any(term in request for term in (
+        "为什么", "原因", "增加", "变多", "上涨", "变高", "上升",
+        "相比", "对比", "比较", "差异", "变化",
+    )):
+        return None
+    if not any(term in request for term in ("消费", "账单", "支出", "收支")):
+        return None
+    if not results or any(name != "get_monthly_bill" or not result.get("ok")
+                          for name, result in results):
+        return None
+    months = {result.get("data", {}).get("month") for _, result in results
+              if isinstance(result.get("data"), dict)}
+    if len(months) != 1:
+        return None
+    return ("本轮只有一个月份的可信账单，无法据此判断消费是否增加，"
+            "也不能确定增加的原因。可以指定一个对比月份继续查询；"
+            "当前月份的明细见下方账单卡。")
+
+
 def summarize_bill_comparison(results: list[tuple[str, dict]]) -> str | None:
@@ -14,3 +62,4 @@ def summarize_bill_comparison(results: list[tuple[str, dict]]) -> str | None:
         amount = data.get("consumption_fen")
-        if not isinstance(month, str) or type(amount) is not int or amount < 0:
+        if (not isinstance(month, str) or not _MONTH.fullmatch(month)
+                or type(amount) is not int or amount < 0):
             continue
@@ -28,6 +77,25 @@ def summarize_bill_comparison(results: list[tuple[str, dict]]) -> str | None:
     old_amount, new_amount = old["consumption_fen"], new["consumption_fen"]
-    # Keep raw amounts only inside privacy-aware financial cards.
-    # The short, Tool-derived qualitative comparison avoids duplicate sensitive
-    # figures in the assistant prose and cannot be authored by the model.
     direction = "增加" if new_amount > old_amount else "减少" if new_amount < old_amount else "持平"
-    return f"{second_month} 的消费较 {first_month} {direction}。两个月的账单明细见下方。"
+    headline = f"{second_month} 的消费较 {first_month} {direction}。"
+    older, newer = _category_amounts(old), _category_amounts(new)
+    if older is None or newer is None:
+        return headline + "分类数据不足，无法确定主要变化来自哪里；两个月的明细见下方账单卡。"
+
+    differences = {category: newer.get(category, 0) - older.get(category, 0)
+                   for category in older.keys() | newer.keys()}
+    if new_amount > old_amount:
+        ranked = sorted(((category, delta) for category, delta in differences.items() if delta > 0),
+                        key=lambda item: (-item[1], item[0]))
+        category_note = (f"分类对比中，{ranked[0][0]}的支出增加最多。"
+                         if ranked else "分类数据未显示单项支出增长，需核对账单。")
+    elif new_amount < old_amount:
+        ranked = sorted(((category, delta) for category, delta in differences.items() if delta < 0),
+                        key=lambda item: (item[1], item[0]))
+        category_note = (f"分类对比中，{ranked[0][0]}的支出减少最多。"
+                         if ranked else "分类数据未显示单项支出下降，需核对账单。")
+    else:
+        category_note = ("虽然消费总额持平，分类支出结构发生了变化。"
+                         if any(differences.values()) else "分类支出没有变化。")
+    return (headline + category_note
+            + "这只能说明支出分布变化，无法仅凭账单判断消费变化的实际原因；"
+            "可结合对应月份的交易明细进一步核对。")
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index 527a591..d78d24f 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -10,3 +10,5 @@ from app.agent.llm import LLMProvider, get_llm
 from app.agent.prompt_assembly import assemble_agent_prompt
-from app.agent.financial_summary import summarize_bill_comparison
+from app.agent.financial_summary import (
+    incomplete_bill_comparison, summarize_bill_comparison,
+)
 from app.agent.read_completion import completed_readonly_summary
@@ -125,2 +127,5 @@ class AgentLoop:
                                               for name, result in tool_results)
+                        missing_evidence = incomplete_bill_comparison(
+                            tool_results, original_request or "",
+                        )
                         if fully_supported and len(tool_results) > 1:
@@ -128,2 +133,4 @@ class AgentLoop:
                                        or f"已完成 {len(tool_results)} 项查询，结果见下方。")
+                        elif missing_evidence is not None:
+                            summary = missing_evidence
                         else:
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
