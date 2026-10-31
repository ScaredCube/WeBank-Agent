# 对象引用 → 可信账单结果：第八批开发记录

日期：2026-10-31
分支：`feature/ip-object-workspace`
状态：本地分支已实现并验证；未推送、未合并团队分支。

## 产品工作流
用户在资产区选择一个人民币状态正常的账户（点击“询问此项”或拖放）→ Chat Composer 保留引用胶囊 → 输入自然语言账单问题 → 前端发送结构化账户 ID → 服务端确认引用归属/状态 → 由后端生成用户绑定的 Vault token → 模型可调用现有 `get_monthly_bill` GREEN Tool → 工具结果以 `bill_result` 可信 SSE 事件传到前端 → 通过账单 schema 校验后生成真实结果卡并附于本次助手消息。原交易确认流程未改变。

## 改动与边界
- `backend/app/schemas/chat.py`：`ChatRequest.references` 仅允许一个 `kind=account` 且 `id>0` 的引用；其他 kind 暂不作为已授权的后端对象。
- `backend/app/api/routes/chat.py`：在创建新用户消息前查验 `Account.user_id`、active、CNY，拒绝失效/越权引用；Vault mint 在服务端完成，token 不返回给浏览器，且不写入展示历史。
- `backend/app/agent/loop.py`：仅由成功的 `get_monthly_bill` 工具执行发出 `bill_result`；模型文本不能制造该事件。
- `frontend/src/lib/sse.ts`、`lib/bank-references.ts`：引用类型与 SSE 收发，客户端只发送 account id，服务器按类型再次校验。
- `frontend/src/features/references/bank-object-reference.ts`：真实账户从旧文本桥接中独立出来；只有模拟产品预览才保留合成账户的文本描述；同一会话最多一个活动账户，可随时替换。
- `frontend/src/features/chat/useChatController.ts`、`pages/Chat.tsx`：可信账单事件绑定到服务端确认的助手消息，显示图表。账户首次发送后仍随当前会话保留供继续追问；新建会话时正确迁移选中的上下文；400/422 拒绝时恢复用户草稿。
- `frontend/src/features/intelligent-ui/bill-data-schema.ts`、`bill-result-card.ts`：从既有月度账单面板提取共享 schema，复用银行账单的明细口径生成结果卡；隐私隐藏功能保持有效。

## 验证
- 用团队已有 Python venv 作为**只读解释器环境**运行独立 worktree 的后端测试；74/74 通过，包含 Chat/MonthlyBill/Vault/VaultSecurity/Injection/Guard/Security。没有改变原团队 Python 环境或服务进程。
- 前端定向七组测试共 74/74 通过，包括发送引用类型、实时账单数据格式、ChatPage 真正接收事件并显示可隐藏的图表、模拟预览与现有月账单。
- TypeScript/Vite 构建通过；Lint 0 errors、1 条历史 `WorkspacePanel` 警告。
- Chrome 在 1440×900 / 390×900 通过合成预览交互：账户选择→输入框引用→发送→消息中显示引用，无 pageerror 或横向溢出。截图位于 `远程工作空间\UX验收_2026-10-31_真实对象链路`。
- 后端 FakeLLM 调用已验证工具查询、可信事件、敏感 token 不外泄与非法账户拒绝；并未声称连接真实大模型线上完成一次端到端任务。

## 尚未完成（真实能力边界）
1. 结构化引用本轮**仅支持账户**；银行卡 `card_id` 与账户、联系人和持仓需要独立权限/引用契约，当前仍是旧文本定位线索。
2. 可信结果卡目前附于内存中的已完成消息，**刷新网页后不能直接从会话历史恢复同一张卡**；历史文本照常保存。后续应设计受控持久化的结果元数据/来源索引（需后端迁移与检索接口）。
3. 实际使用的 LLM 必须选择并成功调用 `get_monthly_bill`，才会生成账单卡；Mock LLM 不会假装调用工具。
4. 复杂多账户比较、多次工具调用的结果归档、完整任务中心及 @ 全域搜索仍待后续迭代。
5. 需要连接运行中的本功能分支后端做一次真实浏览器联调；本批端到端协议由后端 TestClient + 前端组件集成测试覆盖。

## 设计原则
减少次级说明；围绕对象、对话和真实结果形成自然空间关系；从工具获取金额，不从模型文本猜测金融事实。
