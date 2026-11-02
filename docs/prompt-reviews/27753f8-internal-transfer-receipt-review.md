# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`27753f8ca8361d739b23304f652d05ed36ea60ef`
- 当前 HEAD：`27753f8ca8361d739b23304f652d05ed36ea60ef`（包含工作区内相关未提交修改）
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
| `snapshot_contract` | `snapshot_contract:2f643e31a1138fe5` |
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/schemas/tool_results.py b/backend/app/schemas/tool_results.py
index 1972486..9420ded 100644
--- a/backend/app/schemas/tool_results.py
+++ b/backend/app/schemas/tool_results.py
@@ -1,2 +1,2 @@
-"""Validated snapshots of server-issued, read-only tool results."""
+"""Validated, encrypted snapshots of server-issued bank results and receipts."""
 from typing import Literal
@@ -9,5 +9,22 @@ from app.schemas.card_results import CardStatusSnapshot

+class InternalTransferReceipt(BaseModel):
+    """Server-confirmed, executed internal transfer only (never pending action)."""
+
+    model_config = ConfigDict(extra="forbid", strict=True)
+    transfer_id: int = Field(gt=0)
+    status: Literal["completed"]
+    amount_fen: int = Field(gt=0)
+    note: str = Field(max_length=200)
+    source_name: str = Field(min_length=1, max_length=200)
+    source_masked: str = Field(min_length=1, max_length=50)
+    target_name: str = Field(min_length=1, max_length=200)
+    target_masked: str = Field(min_length=1, max_length=50)
+    balance_fen: int = Field(ge=0)
+    currency: Literal["CNY"]
+    transaction_id: int | None = Field(default=None, gt=0)
+
+
 class ToolResultItem(BaseModel):
     model_config = ConfigDict(extra="forbid", strict=True)
-    kind: Literal["monthly_bill", "card_status"]
+    kind: Literal["monthly_bill", "card_status", "internal_transfer"]
     data: dict
@@ -18,4 +35,6 @@ class ToolResultItem(BaseModel):
             self.data = MonthlyBill.model_validate(self.data).model_dump()
-        else:
+        elif self.kind == "card_status":
             self.data = CardStatusSnapshot.model_validate(self.data).model_dump()
+        else:
+            self.data = InternalTransferReceipt.model_validate(self.data).model_dump()
         return self
diff --git a/backend/app/services/chat_messages.py b/backend/app/services/chat_messages.py
index 9269f97..75ebfe1 100644
--- a/backend/app/services/chat_messages.py
+++ b/backend/app/services/chat_messages.py
@@ -25,3 +25,3 @@ def present_message(
         snapshot = session.exec(select(MessageResult).where(MessageResult.message_id == message.id)).first()
-    if not isinstance(snapshot, MessageResult) or snapshot.kind not in ("monthly_bill", "card_status", "tool_results"):
+    if not isinstance(snapshot, MessageResult) or snapshot.kind not in ("monthly_bill", "card_status", "internal_transfer", "tool_results"):
         return output
diff --git a/backend/app/services/chat_turn.py b/backend/app/services/chat_turn.py
index 255b084..6c4d75d 100644
--- a/backend/app/services/chat_turn.py
+++ b/backend/app/services/chat_turn.py
@@ -12,2 +12,3 @@ from app.schemas.bills import MonthlyBill
 from app.schemas.card_results import CardStatusSnapshot
+from app.schemas.tool_results import InternalTransferReceipt
 from app.services.audit_service import conversation_context, record_separately
@@ -115,4 +116,14 @@ async def stream_chat_turn(
                     return
+                # Executed green internal transfers must survive refresh just
+                # like trusted bill/card results. The strict receipt schema
+                # excludes pending actions and all client confirmation tokens.
+                receipt = InternalTransferReceipt.model_validate(event.data.get("data"))
+                if len(trusted_results) >= 8:
+                    advance_submission(submission_id=submission_id, state="failed")
+                    yield encode({"type": "error", "message": "本次查询结果过多，请缩小查询范围。"})
+                    return
+                saved = receipt.model_dump()
+                trusted_results.append({"kind": "internal_transfer", "data": saved})
                 yield encode({"type": "operation_result", "kind": "internal_transfer",
-                            "data": event.data.get("data") or {}})
+                              "data": saved})
             elif event.type == "card_result":
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
