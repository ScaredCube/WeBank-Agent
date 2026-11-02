# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`5befdd913552f7f919a7d264f7c5a21c51221ae4`
- 当前 HEAD：`5befdd913552f7f919a7d264f7c5a21c51221ae4`（包含工作区内相关未提交修改）
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
| `tools` | `tools:2b40e468b5c5436a` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/frontend/src/features/chat/useChatController.ts b/frontend/src/features/chat/useChatController.ts
index dd344fe..c9a7690 100644
--- a/frontend/src/features/chat/useChatController.ts
+++ b/frontend/src/features/chat/useChatController.ts
@@ -79,2 +79,5 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
             recoveryWarning.current('此前请求已创建待确认操作，请在操作记录中核对。不会再次执行或下发确认令牌。')
+          } else if (status.state === 'failed') {
+            clearPendingChatRequest(item.requestId)
+            recoveryWarning.current('此前请求已被服务端确认失败；如涉及模拟金融操作，仍需先核对历史与操作记录，再决定是否作为新请求发起。')
           } else {
@@ -265,2 +268,48 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc

+        // An identical retry may be a second financial operation. Before
+        // issuing another POST, reconcile the existing server request ID.
+        // A terminal "failed" state still does NOT prove no write happened.
+        const signature = JSON.stringify([conversationId, content, references.map(ref => [ref.kind, ref.id]), intent ?? null])
+        const earlier = pendingRequest.current?.signature === signature ? pendingRequest.current : null
+        if (earlier) {
+          try {
+            const status = await api.submissionStatus(token, conversationId, earlier.requestId)
+            if (!isCurrent()) return
+            if (status.state === 'failed') {
+              pendingRequest.current = null
+              clearPendingChatRequest(earlier.requestId)
+              const warning = status.user_message_id === null && status.pending_action_id === null
+                ? '服务端已确认上次请求失败，未进入消息处理。已准备好新请求；请再次点击发送。'
+                : '服务端已确认上次请求失败，但无法据此排除已经发生的模拟操作。请先核对会话及操作记录；确认仍需继续后，再次点击发送会创建全新请求。'
+              setError('上次请求已结束，尚未重新发送。')
+              onActionWarning(warning)
+              return
+            }
+            if (status.state === 'completed') {
+              pendingRequest.current = null
+              clearPendingChatRequest(earlier.requestId)
+              savedReply = status.message
+              setDraft(current => current === raw ? '' : current)
+              setError(null)
+              onActionWarning('上次请求已完成，现已核对历史结果；不会再次调用 Agent。')
+              return
+            }
+            if (status.state === 'action_pending') {
+              pendingRequest.current = null
+              clearPendingChatRequest(earlier.requestId)
+              onActionWarning('待确认操作已经存在，请在操作记录中核对；不会重新生成或下发确认令牌。')
+              setError(null)
+              return
+            }
+            setError('此前请求状态尚未确定，请核对历史与操作记录。')
+            onActionWarning('此前请求仍在处理中或已中断，不能安全重复执行。请核对会话及操作记录。')
+            return
+          } catch {
+            if (!isCurrent()) return
+            setError('无法核对之前的请求状态，请稍后重试状态核对。')
+            onActionWarning('请求状态查询失败，已阻止再次发送，避免重复金融操作。')
+            return
+          }
+        }
+
         const optimistic: Message = {
@@ -278,3 +327,2 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc

-        const signature = JSON.stringify([conversationId, content, references.map(ref => [ref.kind, ref.id]), intent ?? null])
         const requestId = pendingRequest.current?.signature === signature
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
