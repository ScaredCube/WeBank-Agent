# 第十一批开发 · 银行卡可信结果卡

日期：2026-10-31
工作树：`feature/ip-object-workspace`（团队 `klutz-ui` 未修改）
目标：银行卡从前端对象引用形成真实只读 Tool 查询、精确状态卡与可恢复的历史金融结果。

## 体验闭环

用户在资产面板选择银行卡 → 引用进入 Chat Composer → 询问该卡状态 → Agent 使用受控账户 Token 和 card_id 查询 `get_card_status` → 经过服务端白名单脱敏和精确对象限定后，返回 `card_result` → Chat 展示独立的深绿色银行卡面、脱敏卡号、状态和资产入口 → 结果与助手消息一起加密保存 → 刷新、重新打开历史后恢复 → 隐私模式遮蔽账户名称和卡号。

- 状态来源：仅限成功的银行 GREEN Tool；用户或模型自报“正常/挂失”不会生成卡片。
- 精确对象：只读 `get_card_status` 支持 card_id 过滤。就算模型漏传 card_id，服务端在事件输出前也将结果限定为本次已校验的选中银行卡；筛选不出唯一目标时发错误事件，拒绝误展示。
- 数据最小化：Tool 原始返回可能包含 `account_token`，使用 `CardStatusSnapshot` 严格白名单，只把 card_id、account_name、masked_number、status、account_status 发给浏览器和持久化。
- 历史存储：复用现有 `MessageResult` 唯一消息 ID、Fernet 加密、密钥版本；kind 为 `card_status`，不需新增数据库表。旧月账单快照仍可恢复。
- 页面：`CardStatusResult` 显示响应式银行卡视觉和状态，提供「查看资产」入口，不直接执行挂失或转账。支持减少动态效果和隐私模式。
- 体验精简：会话标题从用户原问题生成，排除内部 `[已引用对象：...]` 的附加字段。

## 验证

- 后端定向回归：银行卡、聊天、账单、类型化对象引用，共 36/36 通过（最后一轮包含模型不按约束筛选银行卡的安全场景）。
- 前端定向回归：银行卡组件、真实聊天、SSE、引用协议、账单图表共 52/52 通过；TS/Vite 生产构建成功、Lint 0 错误（已有 1 条 WorkspacePanel 规则警告）。
- Chrome 独立端到端：1440×900 和 390×900 真实 HTTP 登录 → 选择卡 → 请求状态 → 卡片展示 → 等待 SSE 结束 → 刷新 → 结果恢复 → 隐私遮蔽 → 返回资产区。结果卡前后均 1 张；没有 pageerror 或横向溢出。
- 隔离测试使用新分支 FastAPI、Vite、独立 SQLite 与确定性模型调用替身。工具/权限/加密/存取都经过真实后端，未接入线上真实大模型或银行生产服务。
- 截图及脚本：`远程工作空间\UX验收_2026-10-31_卡片联系人联调\bank-card-*.png`、`card-status-e2e.cjs`。

## 当前边界

- 目前一个助手回复的 MessageResult 最多保存一类快照：若同一回复同时产生账单与银行卡结果，保留账单快照；完整多 Tool 多卡结果集合仍需独立演进协议。
- 历史快照记录的是查询时的状态，不代表卡片的实时状态。再次确认卡片是否可用，需要重新调用银行 Tool。任何操作仍需单独安全验证。
- 当前银行数据为模拟环境，复杂真实模型的 Tool 选择及风控 Guard 仍需另行验证。
- 继续遵守：Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.
