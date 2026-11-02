# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`9a8bbb82a6654f151db3d18bc3f7afe14a3d1ca2`
- 当前 HEAD：`9a8bbb82a6654f151db3d18bc3f7afe14a3d1ca2`（包含工作区内相关未提交修改）
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
| `compound_read_summary` | `compound_read_summary:f4906cfc1c5ae4eb` |
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
index 0286c1a..e2bee65 100644
--- a/backend/app/agent/compound_read_summary.py
+++ b/backend/app/agent/compound_read_summary.py
@@ -84,2 +84,32 @@ def summarize_transaction_subscription_review(
     detection = verified.get(_DETECTION_TOOL)
+    if transactions is not None and detection is not None:
+        # Only server-issued Tool observations can establish query scope;
+        # never infer that the latest transaction list and the rolling
+        # detector scanned the same financial records.
+        tx_scope = next(
+            (result.get("scope") for name, result in results
+             if name == _TRANSACTION_TOOL and _valid_rows(name, result) is not None),
+            None,
+        )
+        detect_scope = next(
+            (result.get("scope") for name, result in results
+             if name == _DETECTION_TOOL and _valid_rows(name, result) is not None),
+            None,
+        )
+        if (isinstance(tx_scope, dict) and tx_scope.get("kind") == "single_account"
+                and type(tx_scope.get("max_rows")) is int
+                and 1 <= tx_scope["max_rows"] <= 50
+                and isinstance(detect_scope, dict)
+                and detect_scope.get("kind") == "all_user_accounts"
+                and detect_scope.get("lookback_days") == 186):
+            descriptions.append(
+                "查询范围说明：最近交易来自单个模拟账户的有限条记录；"
+                "疑似周期性扣费识别覆盖本人所有模拟账户近186天的支出流水。"
+                "两者并非相同的交易样本，不能直接逐笔对应。"
+            )
+        else:
+            descriptions.append(
+                "本轮无法核验两个查询的账户与时间范围是否完全一致，"
+                "不能直接把疑似订阅线索归因到本次交易列表。"
+            )
     if transactions is not None:
@@ -92,6 +122,6 @@ def summarize_transaction_subscription_review(
             descriptions.append(
-                f"从近六个月的支出流水中识别到 {len(detection)} 项疑似周期性扣费线索。"
+                f"从近186天的支出流水中识别到 {len(detection)} 项疑似周期性扣费线索。"
             )
         else:
-            descriptions.append("本轮未从近六个月的支出流水中识别到疑似周期性扣费线索。")
+            descriptions.append("本轮未从近186天的支出流水中识别到疑似周期性扣费线索。")
     elif requested_both:
diff --git a/backend/app/services/subscription_service.py b/backend/app/services/subscription_service.py
index 840fd0b..d6efecf 100644
--- a/backend/app/services/subscription_service.py
+++ b/backend/app/services/subscription_service.py
@@ -65,7 +65,12 @@ def detect_candidates(session: Session, user_id: int, months: int = 6) -> list[d
         ~Transaction.category.in_(["模拟转账", "理财申购", "理财赎回"]))).all()
-    grouped: dict[tuple[str, int], list[datetime]] = {}
+    # Periodicity must be proven within ONE account. Grouping only by
+    # merchant + amount can create false candidates by combining payments
+    # from different accounts on different months.
+    grouped: dict[tuple[int, str, int], list[datetime]] = {}
     for entry in rows:
-        grouped.setdefault((entry.counterparty, entry.amount_fen), []).append(entry.occurred_at)
+        grouped.setdefault(
+            (entry.account_id, entry.counterparty, entry.amount_fen), [],
+        ).append(entry.occurred_at)
     candidates = []
-    for (merchant, amount_fen), times in grouped.items():
+    for (_, merchant, amount_fen), times in grouped.items():
         times.sort()
diff --git a/backend/app/tools/account_tools.py b/backend/app/tools/account_tools.py
index 48b073a..f86ea5c 100644
--- a/backend/app/tools/account_tools.py
+++ b/backend/app/tools/account_tools.py
@@ -70,3 +70,3 @@ async def list_recent_transactions(session: Session, user_id: int, **arguments:
         return _result(user_id, tool, error="账户不存在")
-    return _result(user_id, tool, data=[
+    result = _result(user_id, tool, data=[
         {"reference": entry.reference, "direction": entry.direction, "amount_fen": entry.amount_fen,
@@ -76 +76,4 @@ async def list_recent_transactions(session: Session, user_id: int, **arguments:
     ])
+    # Server-issued scope metadata; do not expose internal account IDs/tokens.
+    result["scope"] = {"kind": "single_account", "max_rows": args.limit}
+    return result
diff --git a/backend/app/tools/subscription_tools.py b/backend/app/tools/subscription_tools.py
index 0185fe7..7054f02 100644
--- a/backend/app/tools/subscription_tools.py
+++ b/backend/app/tools/subscription_tools.py
@@ -40,3 +40,9 @@ async def detect_subscriptions(session: Session, user_id: int, **arguments: obje
         SubscriptionArguments.model_validate(arguments)
-        return {"ok": True, "data": detect_candidates(session, user_id), "error": None}
+        return {
+            "ok": True, "data": detect_candidates(session, user_id), "error": None,
+            # The detector scans all accounts owned by this user over a
+            # rolling six * 31 day lookback. It does not inspect just the
+            # selected account or just the latest transaction list.
+            "scope": {"kind": "all_user_accounts", "lookback_days": 6 * 31},
+        }
     except ValidationError:
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
