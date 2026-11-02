# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`b8b3f306f2356941075a9c5c3d8d2297d9c5ab96`
- 当前 HEAD：`b8b3f306f2356941075a9c5c3d8d2297d9c5ab96`（包含工作区内相关未提交修改）
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
| `read_goal_plan` | `read_goal_plan:6737e56704df52e2` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:beadee78807f200f` |
| `tool_executor` | `tool_executor:a81d6bf1bf077af4` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/read_goal_plan.py b/backend/app/agent/read_goal_plan.py
index a517b65..8bda1b3 100644
--- a/backend/app/agent/read_goal_plan.py
+++ b/backend/app/agent/read_goal_plan.py
@@ -9,2 +9,4 @@ from __future__ import annotations
 from dataclasses import dataclass
+from datetime import timedelta, timezone
+import re
 from typing import Any
@@ -14,2 +16,3 @@ from pydantic import ValidationError
 from app.agent.compound_read_summary import _valid_rows
+from app.core.time import utcnow
 from app.schemas.bills import MonthlyBill
@@ -32,6 +35,7 @@ _ACTION = (
 _SKIP = ("不要", "不用", "无需", "不必", "别查", "暂不", "只查", "仅查")
-_ALLOWED_EXTRA = frozenset()  # Don't broaden a three-part request by inferred goals.
+_ALLOWED_EXTRA = frozenset()  # Do not broaden a read request by inferred goals.
+_EXPLICIT_MONTH = re.compile(r"(?<!\d)(20\d{2})[-/年](0?[1-9]|1[0-2])(?:月)?(?!\d)")


-def _trusted(name: str, result: dict[str, Any]) -> bool:
+def _trusted(name: str, result: dict[str, Any], *, expected_month: str | None) -> bool:
     if not isinstance(result, dict) or result.get("ok") is not True:
@@ -40,4 +44,4 @@ def _trusted(name: str, result: dict[str, Any]) -> bool:
         try:
-            MonthlyBill.model_validate(result.get("data"))
-            return True
+            bill = MonthlyBill.model_validate(result.get("data"))
+            return expected_month is None or bill.month == expected_month
         except (ValidationError, TypeError, ValueError):
@@ -54,2 +58,3 @@ class ReadGoalPlan:
     goals: tuple[str, ...] = _GOALS
+    expected_month: str | None = None

@@ -57,3 +62,3 @@ class ReadGoalPlan:
         return tuple(goal for goal in self.goals
-                     if any(name == goal and _trusted(name, res)
+                     if any(name == goal and _trusted(name, res, expected_month=self.expected_month)
                             for name, res in results))
@@ -63,3 +68,3 @@ class ReadGoalPlan:
             name not in self.goals and name not in _ALLOWED_EXTRA
-            or not _trusted(name, result)
+            or not _trusted(name, result, expected_month=self.expected_month)
             for name, result in results
@@ -74,3 +79,3 @@ class ReadGoalPlan:
         valid = {name: res for name, res in results
-                 if name in self.goals and _trusted(name, res)}
+                 if name in self.goals and _trusted(name, res, expected_month=self.expected_month)}
         if not valid:
@@ -127,2 +132,18 @@ def build_read_goal_plan(request: str) -> ReadGoalPlan | None:
         return None
-    return ReadGoalPlan()
+    dates = _EXPLICIT_MONTH.findall(request)
+    # Two explicit months require comparison-aware reasoning, not a single
+    # monthly bill result repackaged as a completed multi-goal plan.
+    if len(dates) > 1 or any(term in request for term in (
+            "下个月", "近两个月", "最近两个月", "过去两个月", "近三个月",
+            "最近三个月", "每个月", "逐月", "各个月", "连续三个月")):
+        return None
+    relative = [term for term in ("本月", "上个月") if term in request]
+    if (len(relative) > 1 or (relative and dates)):
+        return None
+    expected_month = (f"{dates[0][0]}-{int(dates[0][1]):02d}" if dates else None)
+    if relative:
+        local_date = utcnow().astimezone(timezone(timedelta(hours=8)))
+        if relative[0] == "上个月":
+            local_date = local_date.replace(day=1) - timedelta(days=1)
+        expected_month = local_date.strftime("%Y-%m")
+    return ReadGoalPlan(expected_month=expected_month)
diff --git a/backend/app/agent/tool_executor.py b/backend/app/agent/tool_executor.py
index 54d2fb0..e9c7b57 100644
--- a/backend/app/agent/tool_executor.py
+++ b/backend/app/agent/tool_executor.py
@@ -153,3 +153,9 @@ class ToolExecutor:
             if (argument_error is None and context.verified_account_token is not None
-                    and spec is not None and spec.name == "get_monthly_bill"):
+                    and spec is not None and spec.name in {
+                        "get_account_balance", "get_monthly_bill",
+                        "list_recent_transactions",
+                    }):
+                # A server-verified selected account is the scope of all
+                # account-specific READ tools. The model cannot omit or replace
+                # it with an unverified account token.
                 args["account_token"] = context.verified_account_token
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。

## 4. 本轮人工补充：月份证据、账户范围与真实模型验证

**问题与行为依据。** 原版本只检查 `get_monthly_bill` 是否返回合法账单，未比较它的 `month` 与用户明确要求的月份。三目标完成摘要因此可能把 2026-09 的账单当作 2026-10 的查询完成。另一个真实模型验收问题是：DeepSeek 确实并行请求了月度账单、最近交易和疑似订阅，但两个模拟账户共存时，`list_recent_transactions` 缺少账户参数，Tool 失败，导致整个任务无法完成。

**新决策。** 只读计划在创建时标准化 `YYYY-MM`、`YYYY/MM`、`YYYY年M月`、北京时间 `本月`/`上个月`。只有经 Pydantic 校验且月份匹配的账单结果才能计入对应目标。包含多个明确月份、未来月份或多月范围的请求退出单月计划，沿用原有 Agent 工具路径。对服务端已核验的账户选择，`get_account_balance`、`get_monthly_bill`、`list_recent_transactions` 在同一 ToolExecutor 边界统一覆盖模型提供或遗漏的 `account_token`；所有权与风险控制仍由服务端检查，不修改写操作授权。

**测试证据。** 新增错误月份的真实工具链集成用例：模型查询 2026-09，但用户要求 2026-10；最终回答明确标记账单目标未完成，不能宣称三个目标全部完成。另有双模拟账户用例，验证模型即使携带其他账户引用，余额与交易查询也只能作用于本轮选择的账户。相关测试通过，前序两目标续查回归继续保留。

**真实模型验收。** 在全新临时 SQLite、模拟银行账户、临时加密密钥环境中，真实 `deepseek-v4.1-flash-1017` 先前四轮测试的三目标请求返回部分结果。只打印模型请求的工具名称后定位到交易工具缺少服务端账户绑定。修复后重新测试：模型一次请求三个 READ 工具，三目标可信覆盖通过，最终回复正常持久化并产生账单卡片和生成式 UI。测试没有打印密钥、账户数字或 Tool 原始明细。

**剩余边界。** 完成判定只适用于当前明确声明的三个只读目标；时间范围仍各自独立，不意味着交易列表与订阅识别可逐笔对应。这不是普适任务规划、跨会话完整状态快照或生产隐私安全认证。静态 SYSTEM/GUARD/RECOVERY 文本未修改，动态规则的来源与版本由当前 manifest 追踪。

**跨轮一致性补充。** `ConversationTask` 记录未指定账户的月度只读任务时，现在会将 `上个月`、`本月` 统一落为北京时间的具体 `YYYY-MM`；两个月份同现或明确多月范围不压缩为一个单月待办。下一轮用户补充账户后恢复的是先前保存的具体月份，而非再次解释相对时间。最后改动后已针对 TaskState、三目标规划和版本快照重新验证 18/18 项通过。
