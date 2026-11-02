# 小We · 待确认操作的安全编辑回路（2026-11-02）

基线：`klutz-runtime@0972e43`。本轮只修改前端确认弹窗、聊天页及对应定向测试；金融 Tool、后端执行权限、Guard、系统提示词均未修改。Generative UI 并行线独立保留。

## Before / After

| 行为 | Before | After |
| --- | --- | --- |
| Agent 准备转账后用户发现金额需要修改 | 弹窗仅允许确认、取消或关闭；用户必须手动重新组织一条请求 | 在仍待审核且有原始草稿的动作上出现「修改信息」，先调用服务端 `cancel`，收到 `cancelled` 后才恢复原文、账户和联系人绑定 |
| 用户修改草稿时清空文本 | 清空草稿的 effect 也清空了拖拽胶囊，二次提交丢失结构化来源/目标 | 仅在一次发送结束且草稿确实为空时自动清理意图；手动清空输入不取消对象绑定 |
| 取消操作失败 / 状态无法确定 | 不存在专门的安全编辑路径 | 不恢复编辑状态，保留可查询原动作的页面及失败说明 |
| 来自资产页的独立挂失等操作 | 无对应聊天草稿 | 不显示「修改信息」按钮，避免假装能还原来源对象 |
| 退出登录 / 完成操作 | 上次提交的文本可能残留在聊天组件引用 | 清除本地可编辑草稿快照 |

## 交互与权限语义

这不是对已签发确认令牌的订单直接改字段。原订单必须先由服务端确认为取消；新文本再次发送时，仍经过前置意图核验、ToolExecutor、风控和新的操作准备，原确认令牌不得重用。只对**当前会话由聊天输入产生的可溯源草稿**提供编辑入口。已确认、验证中、执行中和已完成的订单不允许进入这一回路。

## 验证与未覆盖范围

- 定向 React / Vitest：待确认弹窗与聊天页 **65/65**，覆盖取消成功才可编辑、取消失败阻止编辑、用户清空并修改金额后仍发送相同结构化来源/目标。
- TypeScript 与 Vite 生产构建成功；仍存在原先大于 500KB 的 Chunk 警告。
- 此次未执行真实浏览器 + 真实 Agent + 合成数据库的完整取消/重准备验收，尚不能称为完整线上验证。
- 外部 Generative UI `feature/klutz-gui-integration` 工作区存在大量未提交修改，本轮没有触碰其文件或变更其职责。之后合并要重点核对并行线也修改过的 `Chat.tsx`。

回退路径：撤销本轮四个前端文件变更即可恢复旧行为，无数据库结构变化。

## 2026-11-02 · 真正的浏览器 + Agent + 合成 SQLite 端到端验收

本阶段新增 `frontend/scripts/competition_action_edit_e2e.cjs`，将隔离启动器 `backend/scripts/run_action_e2e.py` 扩展为显式 `--fixture --edit` 模式；测试模型仍经过**真实 AgentLoop、ToolExecutor、金融 Tool 和 FastAPI**，仅模型决定性的工具调用被固定为可复现的模拟输入。旧路径 `--fixture` 保持不变。

**执行方式**（在隔离开发 worktree 的 `backend` 目录，且前端已安装依赖）：

```powershell
uv run python scripts/run_action_e2e.py --fixture --edit
uv run python scripts/run_action_e2e.py --fixture
```

**真实可复现的浏览器操作**：选择演示活期账户 → 提交 1 元模拟转账 → 后端创建第一笔待确认动作 → 页面点击「修改信息」并调用服务端取消 → 恢复原始用户请求与已选账户引用 → 将金额改为 2 元后重新提交 → Agent 调用新的 `prepare_transfer` → 第二笔动作经用户确认与执行。

**隔离数据库硬断言**：恰好两条不同的 `TransferRequest / PendingAction`；第一笔 100 分 `pending`（业务请求记录尚在）且对应动作 `cancelled`、无交易流水；第二笔 200 分 `completed` 且动作 `completed`；仅有一条 200 分模拟转账流水；付款余额恰好 499800 分，另一个演示账户保持 386012 分；审计包含取消、确认及执行完成。任何一项不符均 FAIL。真实资金操作为 0。

**本轮实际结果**：编辑 E2E `PASS`；原单笔转账 E2E `PASS`；相关后端测试 `26 passed`。上一阶段的 React 定向测试 `65/65` 和构建通过记录仍有效，本轮未改产品前端源码。

**尚未覆盖**：红色二阶段模拟验证、真实 DeepSeek 多次稳定性、跨设备待办恢复。不能由确定性 E2E 推断这些能力已经全部跑通。

## 2026-11-02 · 红色转账编辑与验证 + 并行 E2E 隔离

**目标**：在主线已经支持的资金操作体系内，验收风险等级为 RED 的模拟转账能安全完成「取消 1 元准备动作 → 保留对象上下文修改为 2 元 → 重新准备 → 验证 → 执行」，并检查错误验证码不能越过安全门禁。不增加新的风控策略或真实支付能力。

**变更范围**：
- `backend/scripts/run_action_e2e.py`：新增 `--red`（只能与 `--fixture --edit` 同用）；仅在启动器创建的临时合成银行进程中配置本地小时范围以触发 RED，银行正式风险规则不变。检查两笔操作的风险都是 RED，旧动作取消、新动作验证后完成；拒绝错误验证码并在审计中有验证失败记录。
- `frontend/scripts/competition_action_edit_e2e.cjs`：RED 下先输入错误的模拟验证码并确认 HTTP 拒绝、执行 POST 为零；随后输入正确验证码，真实浏览器验证后自动执行，最终所有路径都仅有一次执行请求；检查业务响应 completed。
- **多线程并行运行**：新增可选 `--backend-port` / `--frontend-port`，覆盖启动器临时环境的 CORS 与 Vite Proxy，并向本 E2E 浏览器传入独立的前端地址。严格拒绝端口已占用。此次发现 8022/5222 正由其他工作区服务使用，未关闭这些进程，改在独立的 8042/5242 运行。

**复现命令**（从该 worktree 的 backend 目录）：

```powershell
uv run python scripts/run_action_e2e.py --fixture --edit --red --backend-port 8042 --frontend-port 5242
uv run python scripts/run_action_e2e.py --fixture --edit --backend-port 8042 --frontend-port 5242
```

**验证**：RED 浏览器全链路 PASS；黄色编辑链路独立回归 PASS；后端 `test_verification.py`、`test_actions.py`、`test_transfers.py` 共 29 项 PASS。数据库精确核验两笔不同准备动作、首笔取消、第二笔完成、唯一 200 分交易流水；RED 验证审计包含 started / failed / succeeded。真实资金操作 0，未改生产库、Guard、Prompt、业务执行模块，也未修改 Generative UI 协作者的工作区。

**仍待验证**：红色 `password_face` 专属业务、真实 DeepSeek 多样本，以及跨设备/会话失效恢复。本轮使用固定模型 Tool 调用，不应据此宣称模型在所有自然语言输入上稳定。默认隔离端口不变，仅在显式命令行指定时改用其他端口。

## 2026-11-02 · password_face 双阶段验证实际端到端验收

**测试路径**：真实 Chrome + FastAPI + AgentLoop/ToolExecutor + 服务端 Guard 风险升级 + VerificationSession + 临时 SQLite。只在独立 E2E 进程中注入一个返回拒绝的模拟 Guard，以验证原有服务端风险引擎是否把红色转账升级为 `password_face`；主 Guard、Prompt、风控阈值及业务执行源码未更改。命令：

```powershell
uv run python scripts/run_action_e2e.py --fixture --edit --red --face --backend-port 8042 --frontend-port 5242
```

**Before / After（测试能力）**：

- 原 `--red` 场景只检查验证码验证后执行；新增 `--face`（必须同时有 `--fixture --edit --red`），构造真实调用链中的风险升级，并要求双阶段验证。
- Chrome 先提交错误验证码，HTTP 拒绝且没有执行 POST；提交正确验证码后进入人脸阶段，**依旧没有执行 POST**；明确点击模拟人脸验证并返回成功后才发生唯一一次执行。
- SQLite 严格检查：首笔 100 分准备动作已取消，新笔 200 分动作已完成，唯一 200 分流水；两个动作均为红色且 `details.verification=password_face`，验证会话为 `verified` 且仅一次错误尝试，审计含 Guard 拒绝、验证失败、两次验证成功与转账完成。

**验证结果**：`--face` 完整测试 PASS；原黄色编辑 E2E PASS、红色仅验证码编辑 E2E PASS；`test_verification.py`、`test_guard.py`、`test_actions.py` 共 **24 passed**。独立端口测试，不改动 GUI 并行线。无真实资金/正式数据。

**严格边界**：这是固定模型 Tool 调用及模拟 Guard 返回值的受控验收；并不等同于真实 DeepSeek 在不同意图下稳定触发升级，也不代表模拟人脸具有真实身份识别能力。真实模型多样本和 Generative UI 历史恢复的集成仍是独立未完成事项。
