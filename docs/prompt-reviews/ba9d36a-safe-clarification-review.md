# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`ba9d36aa991562b65e8da242dac88adf4c32c95d`
- 当前 HEAD：`ba9d36aa991562b65e8da242dac88adf4c32c95d`（包含工作区内相关未提交修改）
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
| `guard` | `guard:3637e17f6d8f8e21` |
| `read_completion` | `read_completion:6e2412d31ecbbedc` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/response_policy.py b/backend/app/agent/response_policy.py
index dae99d6..2a64021 100644
--- a/backend/app/agent/response_policy.py
+++ b/backend/app/agent/response_policy.py
@@ -248,2 +248,5 @@ _UNVERIFIED_PROGRESS = re.compile(
 )
+_SAFE_CLARIFICATION_OPENER = re.compile(
+    r"^(?:可以的|当然可以|好的|没问题|好呀|当然|可以)[，,。！!]\s*"
+)
 _CLARIFICATION_CUES = (
@@ -268,3 +271,7 @@ def safe_action_clarification(candidate: str) -> bool:
         return False
-    if not text.startswith((
+    # Accept a short conversational acknowledgement before an otherwise
+    # valid question. Run every financial-claim and safety check on the WHOLE
+    # text below; the prefix cannot waive those constraints.
+    question = _SAFE_CLARIFICATION_OPENER.sub("", text, count=1)
+    if not question.startswith((
         "请问", "请告诉我", "请先", "你想", "您想", "你希望", "您希望",
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
