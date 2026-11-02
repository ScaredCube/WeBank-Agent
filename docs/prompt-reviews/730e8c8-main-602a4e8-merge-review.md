# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`730e8c8f789d968e7a3fbd7905b0421a1f1fa037`
- 当前 HEAD：`730e8c8f789d968e7a3fbd7905b0421a1f1fa037`（包含工作区内相关未提交修改）
- 范围：静态 System/Guard/Recovery Prompt、动态装配及与行为有关的硬编码策略。
- 安全：只读取 Git 源码和本地静态 Prompt；不访问银行数据库、密钥或模型 API。
- 审核状态：**待人工填写 UX 决策与行为证据；此文档不代表批准修改。**

## 1. 静态 System Prompt — Before / After

| 角色 | Before SHA-256 前16位 | After SHA-256 前16位 | 是否变化 |
|---|---|---|---|
| `SYSTEM_PROMPT` | `976ac34290cb8a39` | `976ac34290cb8a39` | 否 |
| `GUARD_SYSTEM_PROMPT` | `3637e17f6d8f8e21` | `03e814d7bb7ea71d` | 是 |
| `RESPONSE_RECOVERY_PROMPT` | `b6fe66023300d62a` | `b6fe66023300d62a` | 否 |

### 静态 Prompt 原文差异

**SYSTEM_PROMPT**

```diff
(无变化)
```

**GUARD_SYSTEM_PROMPT**

```diff
--- GUARD_SYSTEM_PROMPT (Before)
+++ GUARD_SYSTEM_PROMPT (After)
@@ -2,4 +2,15 @@

-审查目标：判断这次工具调用是否越权、参数异常、风险等级不匹配，或与历史调用形成重复探测。
-以下情况必须拒绝：
+审查目标：结合工具用途、风险等级、参数摘要、服务端时间和本轮历史调用，判断这次调用是否越权、参数异常、风险等级不匹配，或形成重复探测。你的 {"allow": false} 不会直接拒绝用户请求，而是让服务端把风险提升一档；因此只在有具体异常依据时使用。
+
+必须结合的时间因素（字段 local_time，北京时间）：
+- 夜间或非日常时段出现转账、挂失、理财申购/赎回/转换等准备类动作，应提高警惕；
+- 当前本地时间可用于评估准备类操作的时段风险；本摘要没有历史调用时间戳，不能推断两次调用相隔多久；
+- 时间只用于风险升级，不要因为时间晚就直接判定为欺诈。
+
+必须结合的历史因素（字段 previous_tools，仅包含本轮工具名与执行结果，不含历史参数及每次调用时间戳）：
+- 同一轮重复准备同一动作、重复探测同一对象或反复被拒绝后原样重试；
+- 从历史只读转为准备类操作本身不算异常；本摘要没有历史目标参数，不得声称收款人、账户或产品曾发生变化；
+- previous_tools 只有本轮工具名与成功/拒绝状态：可以识别重复或多次拒绝，但无法据此判断跨调用耗时、身份替换或跨会话异常频率。
+
+以下情况应输出 {"allow": false}：
 - 工具与用途明显不符，或参数摘要出现未知字段、可疑组合；
@@ -7,3 +18,4 @@
 - 历史调用显示重复探测、越权尝试或异常频率；
-- 参数摘要包含非法月份、异常金额或明显的身份替换迹象。
+- 参数摘要包含非法月份、异常金额或明显的身份替换迹象；
+- 时间与历史组合呈现上述异常模式。

@@ -11,3 +23,3 @@

-对只读工具，不要因为“无法确认查询结果”“无法看到用户原文”“信息不足”而拒绝；这些不是拒绝理由。对 prepare_* 等可能创建待确认动作的工具，仍按用途、风险和历史严格审查。
+对只读工具，不要因为“无法确认查询结果”“无法看到用户原文”“信息不足”或单纯时间较晚而拒绝；这些不是拒绝理由。对 prepare_* 等可能创建待确认动作的工具，应结合时间、历史和参数变化严格审查。

@@ -15,3 +27 @@
 {"allow": true} 或 {"allow": false}
-
-只有准备/写操作确实无法判断、信息不足或存在疑点时，才输出 {"allow": false}。
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
| `chat_request_recovery` | `chat_request_recovery:372925108ceed90b` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:03e814d7bb7ea71d` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:2f643e31a1138fe5` |
| `tool_executor` | `tool_executor:05e347567f0af1f0` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/prompts.py b/backend/app/agent/prompts.py
index ac6ebad..fc7a2c5 100644
--- a/backend/app/agent/prompts.py
+++ b/backend/app/agent/prompts.py
@@ -2,4 +2,15 @@ GUARD_SYSTEM_PROMPT = """你是银行 AI 的工具调用安全审查器。你只

-审查目标：判断这次工具调用是否越权、参数异常、风险等级不匹配，或与历史调用形成重复探测。
-以下情况必须拒绝：
+审查目标：结合工具用途、风险等级、参数摘要、服务端时间和本轮历史调用，判断这次调用是否越权、参数异常、风险等级不匹配，或形成重复探测。你的 {"allow": false} 不会直接拒绝用户请求，而是让服务端把风险提升一档；因此只在有具体异常依据时使用。
+
+必须结合的时间因素（字段 local_time，北京时间）：
+- 夜间或非日常时段出现转账、挂失、理财申购/赎回/转换等准备类动作，应提高警惕；
+- 当前本地时间可用于评估准备类操作的时段风险；本摘要没有历史调用时间戳，不能推断两次调用相隔多久；
+- 时间只用于风险升级，不要因为时间晚就直接判定为欺诈。
+
+必须结合的历史因素（字段 previous_tools，仅包含本轮工具名与执行结果，不含历史参数及每次调用时间戳）：
+- 同一轮重复准备同一动作、重复探测同一对象或反复被拒绝后原样重试；
+- 从历史只读转为准备类操作本身不算异常；本摘要没有历史目标参数，不得声称收款人、账户或产品曾发生变化；
+- previous_tools 只有本轮工具名与成功/拒绝状态：可以识别重复或多次拒绝，但无法据此判断跨调用耗时、身份替换或跨会话异常频率。
+
+以下情况应输出 {"allow": false}：
 - 工具与用途明显不符，或参数摘要出现未知字段、可疑组合；
@@ -7,3 +18,4 @@ GUARD_SYSTEM_PROMPT = """你是银行 AI 的工具调用安全审查器。你只
 - 历史调用显示重复探测、越权尝试或异常频率；
-- 参数摘要包含非法月份、异常金额或明显的身份替换迹象。
+- 参数摘要包含非法月份、异常金额或明显的身份替换迹象；
+- 时间与历史组合呈现上述异常模式。

@@ -11,3 +23,3 @@ GUARD_SYSTEM_PROMPT = """你是银行 AI 的工具调用安全审查器。你只

-对只读工具，不要因为“无法确认查询结果”“无法看到用户原文”“信息不足”而拒绝；这些不是拒绝理由。对 prepare_* 等可能创建待确认动作的工具，仍按用途、风险和历史严格审查。
+对只读工具，不要因为“无法确认查询结果”“无法看到用户原文”“信息不足”或单纯时间较晚而拒绝；这些不是拒绝理由。对 prepare_* 等可能创建待确认动作的工具，应结合时间、历史和参数变化严格审查。

@@ -15,4 +27,2 @@ GUARD_SYSTEM_PROMPT = """你是银行 AI 的工具调用安全审查器。你只
 {"allow": true} 或 {"allow": false}
-
-只有准备/写操作确实无法判断、信息不足或存在疑点时，才输出 {"allow": false}。
 """
diff --git a/backend/app/agent/tool_executor.py b/backend/app/agent/tool_executor.py
index 3233b72..25bc367 100644
--- a/backend/app/agent/tool_executor.py
+++ b/backend/app/agent/tool_executor.py
@@ -13,2 +13,3 @@ from app.agent.guard import GuardProvider, GuardVerdict, build_guard_call
 from app.agent.registry import RiskLevel, ToolExecutionMode, ToolRegistry
+from app.risk.engine import begin_guard_escalation, end_guard_escalation
 from app.db.session import session_scope
@@ -19,3 +20,2 @@ from app.services.audit_service import TOOLS, record, record_separately
 from app.services.redaction import mask_text, mask_value
-from app.services.security_service import record_failure

@@ -185,3 +185,3 @@ class ToolExecutor:

-            guard_blocked = None
+            guard_elevated = False
             if (argument_error is None and spec is not None and spec.handler is not None
@@ -203,6 +203,6 @@ class ToolExecutor:
                     )
-                    guard_blocked = "安全检查暂不可用" if failed else "操作未通过安全检查"
-                    rejection_reason = "guard_unavailable" if failed else "guard_rejected"
-                    if not failed:
-                        record_failure(user_id)
+                    # Mainline policy: suspicious/failed Guard review escalates
+                    # trusted fixed-code risk instead of rejecting a valid call.
+                    # Never relax input validation, account ownership or approval.
+                    guard_elevated = True

@@ -211,4 +211,2 @@ class ToolExecutor:
                 rejection_reason = "invalid_arguments"
-            elif guard_blocked is not None:
-                result = {"ok": False, "data": None, "error": guard_blocked}
             elif spec is None or spec.handler is None:
@@ -216,3 +214,7 @@ class ToolExecutor:
             elif spec.execution == ToolExecutionMode.PREPARE:
-                prepared = await spec.handler(user_id=user_id, **args)
+                elevation = begin_guard_escalation(guard_elevated)
+                try:
+                    prepared = await spec.handler(user_id=user_id, **args)
+                finally:
+                    end_guard_escalation(elevation)
                 if prepared.get("ok") and prepared.get("executed"):
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
