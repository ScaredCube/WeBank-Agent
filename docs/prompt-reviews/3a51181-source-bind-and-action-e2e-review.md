# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`3a51181d41c7be88e245ebbe84ccbb07151be126`
- 当前 HEAD：`3a51181d41c7be88e245ebbe84ccbb07151be126`（包含工作区内相关未提交修改）
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
| `chat_request_recovery` | `chat_request_recovery:372925108ceed90b` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:3637e17f6d8f8e21` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:2f643e31a1138fe5` |
| `tool_executor` | `tool_executor:7fe56c120f9de3d5` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/tool_executor.py b/backend/app/agent/tool_executor.py
index 7cedebd..3233b72 100644
--- a/backend/app/agent/tool_executor.py
+++ b/backend/app/agent/tool_executor.py
@@ -102,4 +102,9 @@ class ToolExecutor:
         events: list[ToolClientEvent] = []
+        sensitive_recipient_name = False
         try:
             args = json.loads(function["arguments"])
+            if (spec is not None and spec.name == "prepare_transfer"
+                    and isinstance(args, dict)
+                    and isinstance(args.get("recipient_name"), str)):
+                sensitive_recipient_name = mask_value(args["recipient_name"]) != args["recipient_name"]
             if (not isinstance(args, dict) or "session" in args or "user_id" in args
@@ -109,3 +114,6 @@ class ToolExecutor:
             rejection_reason = "invalid_arguments"
-            result = {"ok": False, "data": None, "error": "查询参数无效"}
+            result = {"ok": False, "data": None,
+                      "error": ("收款人姓名不能包含手机号或其他敏感号码；请只填写姓名或称呼，"
+                                "使用服务端提供的 target_token 引用传递手机号。"
+                                if sensitive_recipient_name else "查询参数无效")}
         else:
@@ -165,2 +173,10 @@ class ToolExecutor:

+            if (argument_error is None and spec is not None
+                    and spec.name == "prepare_transfer"
+                    and context.verified_account_token is not None):
+                # The user's current explicit account selection is owned and
+                # validated by Chat. Rebind it here rather than expecting the
+                # model to copy an opaque token, including phone-recipient turns.
+                args["source_token"] = context.verified_account_token
+
             if (argument_error is None and context.context_readonly_only and spec is not None
diff --git a/backend/app/tools/transfer_tools.py b/backend/app/tools/transfer_tools.py
index 42fa548..cc56163 100644
--- a/backend/app/tools/transfer_tools.py
+++ b/backend/app/tools/transfer_tools.py
@@ -13,5 +13,13 @@ class TransferArguments(BaseModel):
     model_config = ConfigDict(extra="forbid", strict=True)
-    source_token: str | None = None
-    recipient_name: str = Field(min_length=1, max_length=80)
-    target_token: str | None = None
+    source_token: str | None = Field(
+        default=None, description="付款账户由服务端绑定本轮用户明确选择的账户；未选择时不猜测账户或令牌。"
+    )
+    recipient_name: str = Field(
+        min_length=1, max_length=80,
+        description="只填收款人的姓名或称呼，如「模拟收款人」；绝不能附加手机号、银行卡号或其他数字联系方式。手机号只能用 target_token 传递。",
+    )
+    target_token: str | None = Field(
+        default=None,
+        description="用户输入手机号时，填写服务端在本轮上下文提供的 PHONE_TMP 临时引用；绝不填写明文手机号、猜测号码或拼接到收款人姓名。",
+    )
     recipient_contact_token: str | None = None
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
