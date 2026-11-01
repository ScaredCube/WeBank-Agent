# 第十批 · 银行卡与联系人结构化引用

> 历史状态说明（2026-11-01 补充）：本文改动已随 PR #3 合入 `main`（`007d7fb`）；“未推送、未合并”为撰写时状态。

日期：2026-10-31
分支：`feature/ip-object-workspace`（已合并）
基于：`0008d4f`；后续随 PR #3 合并。

## 本轮真实用户体验

账户、银行卡、联系人现在以各自的 `kind + id` 传递，服务器逐项重新校验归属和可用性。银行卡通过实际 Card.account_id 关联所属账户，无需前端猜测掩码或卡号；模型调用 `get_card_status` 时使用服务器为该账户生成的受控 Token。

选择联系人时，服务器核实 Contact.user_id 和 active 状态，并提供用户绑定的 `recipient_contact_token`。若用户明确要求模拟转账，`prepare_transfer` 可使用 Token 再次核验并覆盖模型随意填写的收款人姓名。此流程只创建待确认动作，不执行扣款。后续用户确认与转账执行沿用已有风险检查、请求幂等、账户及卡状态校验。

每条会话最多选择一个账户、一个银行卡、一个联系人；同时引用银行卡与账户时，二者必须属于同一个真实账户。持仓对象保持上一版的明示「待核验文本线索」机制，尚未假装支持服务端类型化引用。当前会话的引用在发送后继续保留，用户可自行移除。历史消息展示由服务端确认过的对象标签，不暴露 Token。

## 技术边界

- `ChatRequest.references`：判别联合类型 account/card/contact，最多 3 项，各 kind 唯一。ID 必须为有效正整数，非法/不归属用户的对象直接拒绝，且不写入用户消息。
- 卡片：允许查询已关联账户的卡片状态；已挂失卡仍受到现有挂失/转账工具约束，引用卡不等于挂失授权。
- 联系人：数据库只保存脱敏手机号，新增 Token 仅证明服务器验证过的联系人身份，不尝试推断或重建手机号。绑定转账时使用服务端联系人姓名和 token；不能同时选择受控联系人及临时收款电话。
- 转账执行再次验证绑定的联系人 Token 和当前联系人状态；联系人失效后，即使此前创建了待确认操作，也不能扣款。
- 用户对话继续遵守“确认之前不执行交易”。本批未替换原风险引擎、模拟验证码和确认流程。
- `@对象` 全域搜索、银行卡独立可信结果卡、持仓授权协议与真实模型选择 Tool 的稳定性尚需后续完成。

## 代码

- `backend/app/schemas/chat.py`：typed reference 验证及同类去重。
- `backend/app/api/routes/chat.py`：逐项校验所有权、卡到账户映射、联系人的真实姓名和 Token；向 Agent 注入服务器确认的信息；向历史消息追加安全展示标签。
- `backend/app/services/vault.py`：联系人持久化用户绑定 Token，解析时验证未撤销、用户归属及联系人有效状态。
- `backend/app/tools/transfer_tools.py`、`services/transfer_service.py`：`recipient_contact_token` 对接现有 prepare/execute 双阶段流程，执行前再次校验。
- `frontend/src/lib/sse.ts`、`features/references/bank-object-reference.ts`：发送类型化对象 ID，移除旧的卡/联系人文本桥接，支持显示多类服务端确认标签。
- `frontend/src/pages/Chat.tsx`：已选对象保留到当前会话中，便于继续追问。

## 验证

- 后端：10 个针对性测试文件共 **105/105**，覆盖金融对象所有权、卡映射、联系人失效、联系人 Token、错误收款人覆盖、受控待确认转账、原有转账/挂失/账单/Vault/安全防护。
- 前端：5 个定向测试文件共 **63/63**；生产 Vite/TS 构建通过，Lint 0 error、1 条历史 WorkspacePanel 警告。后续会再次校验最终状态。
- 新版隔离 FastAPI（8011）+ Vite（5194）浏览器验收：桌面 1440px / 手机 390px 各自完成登录、引用真实卡、查询状态、创建新对话、同时引用卡+联系人、请求 1 元模拟转账准备、查看确认面板；无 JS pageerror 与横向溢出。
- 隔离 SQLite QA 数据审查：账户余额始终 500000 分；3 条请求为 `pending`，收款人均为服务端真实联系人姓名，未产生 completed 转账。
- 真实浏览器验收由确定性测试模型触发真实 Tool，**没有验证真实线上大模型**，未使用真实银行业务数据。

## 后续建议
先做好正式环境迁移和多对象引用的持续历史恢复，再实现 `@` 全域对象搜索与银行卡可信结果卡。UI 保持简洁，“Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.”
