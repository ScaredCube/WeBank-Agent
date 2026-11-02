# 小We · 转账账户引用与真实 Agent Runtime / Chrome 全链路验收

基线：`3a51181`。完整自动生成 Before/After 源码 Diff：[`3a51181-source-bind-and-action-e2e-review.md`](3a51181-source-bind-and-action-e2e-review.md)。修改范围：`backend/app/agent/tool_executor.py`、`backend/tests/test_selected_transfer_source.py`，新增隔离操作 QA runner 与浏览器脚本。三套主 System/Guard/Recovery Prompt 和金融执行服务均未修改。

## Before / After

| 事件 | Before | After |
|---|---|---|
| 用户在本轮明确引用演示活期账户，收款人为临时号码 | 只有同时选择已保存的联系人时，`prepare_transfer` 才会自动获得服务端已核验的 `source_token`。临时收款号码流程要求模型自行复制账户令牌；两个账户时遗漏会导致拒绝 | `prepare_transfer` 统一使用**当前本轮已验证的付款账户**令牌。模型遗漏或伪造源账户令牌时，服务端仅绑定用户实际选择的账户 |
| 用户有两个账户，但当前没有明确选择付款账户 | 工具不能猜测账户，模型缺少来源时准备失败 | 保持原有拒绝；不会使用前一轮只读选择代替资金操作授权 |
| 模型生成正确 Tool Call，用户在真实网页确认模拟转账 | 先前只有后端集成与 Chrome 模拟 HTTP 两段相互独立的证据 | 新增确定性模型替身启动器，在真实 FastAPI/AgentLoop/ToolExecutor/Chrome/SQLite 中验证同一条完整业务路径 |
| 真实模型将手机号混入 `recipient_name` | 参数结构可能合法，但脱敏检查拒绝；通用“查询参数无效”无法帮助模型修正 | Tool Schema 明确姓名只填称呼、明文号码经本轮 `target_token` 引用传递；拒绝时返回**不包含原号码的定向反馈**。原有隐私拒绝和 Guard 均不放宽 |

## 测试环境与运行方式

`backend/scripts/run_action_e2e.py` 是独立的显式执行入口：
- `uv run python scripts/run_action_e2e.py --fixture`：确定性模型替身产生一次 `prepare_transfer` Tool Call；之后使用实际 Agent Runtime、FastAPI、浏览器 UI、服务端确认/执行、临时 SQLite 及审计。无需模型供应商。
- `uv run python scripts/run_action_e2e.py --live`：使用已有配置的真实模型，执行同一真实网页流程。**修正 Tool Schema 后，本次完整运行 PASS。**
- `uv run python scripts/run_action_e2e.py --live --diagnose`：明确启用测试专用的脱敏 Tool 参数形状记录，只保存布尔值、允许的字段名和类型；不保存真实参数值、手机号、账户令牌、模型原文或 API 密钥。诊断过程不会修改正式银行数据。

两种模式均使用回环隔离端口、独立临时数据库、随机 Vault/HMAC/JWT 密钥、模拟账户与模拟收款号码。脚本拒绝占用已存在的端口。浏览器操作仅在模拟服务端执行 1 元操作，绝不连接真实银行。

数据库强约束：两个固定种子账户最终余额精确为 499900 分和 386012 分；一条 `completed`/100 分转账、一条模拟转账流水、一条已完成黄色 PendingAction；审计包含 `action_confirmed` 和 `transfer_completed`。浏览器必须实际选中付款账户、收到服务端待确认动作，并在用户确认与执行后显示成功。任何一项不符合即 FAIL。

## 验证结果

- **确定性模型 + 真实 Agent / HTTP / Chrome / SQLite：PASS**。正确选中账户、显示待确认弹窗、执行模拟转账；数据库两个账户状态与交易/审计均通过精确断言；浏览器 JS 错误 0。
- **真实 DeepSeek（修改前）：FAIL**。网页已选账户，模型实际尝试 `prepare_transfer`；安全形状诊断确认金额为 `100` 分且 Schema 字段合法，但 `recipient_name` 中出现敏感号码，隐私检查拒绝；随后重试也未完成。失败试验没有产生待确认动作或转账记录。
- **真实 DeepSeek（修改后）：PASS（单次）**。Tool Schema 明确姓名与号码引用的职责，隐私拒绝消息改为不含明文的可修正指引；运行 `--live --diagnose` 后真实模型成功创建待确认模拟转账，Chrome 由用户控制流程确认并执行。隔离 SQLite 精确核验：两账户余额 `499900` / `386012` 分、`1` 笔 completed 转账、`1` 条 100 分模拟转账流水、黄色 PendingAction completed、审计包含 `action_confirmed` 和 `transfer_completed`；浏览器 JS 错误 `0`。这是一次实测成功，不代表跨多次调用可靠性已穷尽。Guard 与银行执行服务未修改。
- **定向服务端回归**：覆盖模型省略或伪造来源令牌、用户未选账户时不能准备、原转账幂等/验证/权限等行为。静态 System Prompt SHA 维持不变。
- 既有后端幂等测试核验相同转账编号重试不产生第二次扣款；本轮浏览器 Fixture E2E 的数据库精确断言证明该次正常执行只产生一笔，未在浏览器中重复主动触发执行接口。

## 风险判断与下一步

这次**服务端来源令牌绑定是一个权限收紧方向的确定性改进**：当前显式选择的用户账户由服务端签发且重新核验，模型不能控制实际付款账户，也不能继承上一轮只读选择来准备转账。

真实供应商先失败后成功，证明 Tool Schema 的具体用词会改变模型生成的参数质量。但目前只有一次修复后成功样本，尚未量化稳定性；不得直接称整套金融 Agent 已全面上线。后续可收集有限的隔离样本、分析风险等级与取消/断网路径，不得为提高通过率而绕过 Guard、掩盖模型错误或降低银行执行约束。

回退：恢复 `tool_executor.py` 的这段账户绑定及测试基线；新增 QA runner 可继续保留用于验证旧版失败的反例。无数据库迁移、不调整密钥与实际风控。
