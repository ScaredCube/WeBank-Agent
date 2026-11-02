# AI 银行智能体

小We · 银行 AI Agent 比赛演示项目。前端包括对话、资产、账单、收藏和操作记录；后端提供 Agent、银行 Tool、可信结果、风险确认及审计。功能分支已通过 PR #3 合并到 `main`（提交 `007d7fb`，与 `origin/main` 一致），并已完成真实大模型与隔离模拟银行数据的只读/多工具联调；但**正式银行生产环境、跨设备收藏、实际开户、真实强验证和团队最终验收仍未完成**。当前真实进度、剩余审查项和已知限制见 `docs/项目汇报.md`，待办见 `docs/TODO.md`。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.11+ · FastAPI · Pydantic · SQLModel · uv |
| 数据库 | SQLite（当前模拟资金事务依赖 SQLite；PostgreSQL 尚未完成适配） |
| 大模型 | OpenAI 兼容接口（DeepSeek / 通义 / vLLM / Ollama），无 Key 时自动使用离线 Mock |
| 前端 | React 19 · TypeScript · Vite · Tailwind CSS v4 · shadcn/ui 风格组件 |
| 通信 | REST + SSE 流式输出 |

## 目录结构

```
bank_agent/
├─ backend/
│  ├─ app/
│  │  ├─ api/routes/        # health / auth / chat / actions / transfers / bills / cards / wealth / subscriptions / bank_data / audit / security
│  │  ├─ agent/             # LLM 适配层、AgentLoop、子 Agent 护栏、工具注册表、提示词
│  │  ├─ core/              # 配置、安全（JWT / 密码哈希）
│  │  ├─ db/                # 引擎、初始化、演示数据
│  │  ├─ risk/              # 固定代码风险分级
│  │  ├─ schemas/           # Pydantic 请求响应
│  │  ├─ services/          # 会话、转账、卡片、账单、审计、数据引用等领域逻辑
│  │  ├─ tools/             # Tool 实现与注册
│  │  └─ main.py
│  └─ tests/
├─ frontend/
│  └─ src/
│     ├─ components/        # 基础 UI、聊天组件、确认弹窗
│     ├─ features/          # 对话、资产拖拽、动作、收藏和受控卡片
│     ├─ lib/               # API 客户端、SSE 解析、鉴权
│     └─ pages/             # 登录、对话
└─ docs/                    # 赛题解析与设计思路
```

## 快速开始

### 后端

```powershell
cd backend
Copy-Item .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health
- 未配置 `LLM_API_KEY` 时自动进入 Mock 模式，可离线测试基础对话；Mock 不调用银行查询工具
- `DEMO_MULTI_ASSETS=true`（默认）会为演示用户补建第二个账户和持仓，用于资产拖拽矩阵；测试环境使用 `false` 保持单账户夹具
- 演示夜间风控默认使用北京时间 00:00–06:00；可通过 `RISK_NIGHT_START_HOUR` 和 `RISK_NIGHT_END_HOUR` 调整起止整点，具体业务时段尚待确认

### 已有数据库升级与启动门禁（SQLite）

全新、没有任何业务表的 SQLite 数据库可由首次启动自动初始化。**已经存在业务表的数据库不会再由启动流程悄悄补建 Agent 聊天表。** 更新后端代码后，请先停止旧服务，在 `backend` 目录执行显式预检：

```powershell
uv run python scripts/check_chat_schema.py
# 如果提示缺少表，先在离线环境确认升级范围与停机窗口，再执行：
uv run python scripts/check_chat_schema.py --apply
# 输出同目录 SQLite .bak 备份，升级完成后再次执行不带 --apply 的预检
uv run python scripts/check_chat_schema.py
```

迁移管理三张新增表：`conversationselection`、`chatsubmission`、`messageresult`；发现缺少约束/字段时拒绝自动修复。升级与回滚演练：

```powershell
uv run python scripts/rehearse_chat_schema.py --json
```

此工具**只支持 SQLite 的增量建表**，不覆盖其他业务表字段演进、不提供 PostgreSQL 迁移或在线无停机升级；正式部署或对团队目标数据库升级前，必须确认数据库版本、完整备份、停机窗口以及升级和回滚责任。

接入真实模型时修改 `backend/.env`：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

工具调用前护栏仅在配置真实 `LLM_API_KEY` 时启用，超时由 `GUARD_TIMEOUT_SECONDS` 控制（默认 8 秒），详见 `docs/T-202护栏说明.md`。熔断与限流阈值见 `docs/T-203熔断限流说明.md`；演示手动解锁仅在 `DEBUG=true` 时可用。

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173，演示账号 `demo / demo123`。

开发环境下 Vite 会将 `/api` 代理到 `http://127.0.0.1:8000`，无需额外配置跨域。

### Docker Compose

```powershell
# 1. 准备环境变量（生产部署必须更换 JWT_SECRET 与数据加密密钥，并设 DEBUG=false）
Copy-Item .env.example .env
# 2. 构建并启动
docker compose up -d --build
# 3. 打开 http://localhost:8080（演示账号 demo / demo123）
docker compose ps
docker compose logs -f backend
docker compose down   # 停止；SQLite 数据保留在命名卷 backend-data
```

- `backend`：Python + uv，启动时自动初始化空库与演示数据，`/api/health` 健康检查；端口仅绑定 `127.0.0.1`。
- `frontend`：Node 多阶段构建为静态产物，nginx 同源反代 `/api`（SSE 无缓冲转发）到后端。
- SQLite 数据持久化在命名卷 `backend-data`（容器内 `/app/data/bank_agent.db`）；已有旧库升级仍须先运行 `backend/scripts/check_chat_schema.py`（见上文启动门禁）。
- 该配置为打包交付物（T-503），当前只完成配置编写与 YAML 校验，未执行实际镜像构建验证。

### 测试

```powershell
cd backend
uv run pytest

cd ../frontend
npm run lint
npm run test
npm run build
```

常规前端 Playwright 用例（`e2e/chat-assets.browser.cjs`）使用隔离 API 替身，覆盖手机资产点选生成意图胶囊并提交实体 ID、桌面隐私模糊与点击临时显示；不连接真实模型。独立的 `backend/scripts/run_competition_e2e.py --live` 则显式使用本机已有真实模型配置，在全新合成 SQLite + 隔离 HTTP 端口上执行**只读**浏览器联调，不会自动确认或执行模拟转账；运行会产生模型 API 调用成本。首次安装前端 Playwright 的 Chromium：

```powershell
cd frontend
npx playwright install chromium
npm run dev
```

保持开发服务运行，在另一个终端执行 `npm run test:e2e`。默认连接 `http://127.0.0.1:5173`；如果开发服务使用其他端口，设置 `PLAYWRIGHT_BASE_URL`。若使用已安装的 Chrome，可设置 `PLAYWRIGHT_CHANNEL=chrome`。例如本机开发服务在 5174 端口时：

```powershell
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:5174'
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run test:e2e
```

正式 `/chat` 是唯一交互入口：桌面为左侧常驻资产栏 + 中间对话，手机左上角“资产”一步整屏滑入；顶栏三横线在右侧，打开“对话 / 收藏 / 操作记录”工具抽屉。资产页支持长按拖拽、点击选源和键盘操作；意图胶囊只提交实体 ID，由后端生成 token 化前置提示词。`demo/` 目录仅作为视觉与交互参考，不参与构建。

## 文档

- [CLAUDE.md](CLAUDE.md)：协作规范、开工前阅读要求与文档同步义务
- [docs/项目汇报.md](docs/项目汇报.md)：当前架构、已完成工作、验证结果与已知限制
- [docs/TODO.md](docs/TODO.md)：任务编号、优先级、验收标准与里程碑
- [docs/frontend/2026-11-01-pre-pr-engineering-review.md](docs/frontend/2026-11-01-pre-pr-engineering-review.md)：已合并分支的架构、安全、性能和团队集成审查记录；F-01～F-05 等剩余项仍未全部关闭
- [docs/frontend/2026-11-01-chat-history-performance-review.md](docs/frontend/2026-11-01-chat-history-performance-review.md)：会话历史分页、加密快照批量读取及剩余容量边界
- [docs/frontend/2026-11-01-collection-privacy-decision.md](docs/frontend/2026-11-01-collection-privacy-decision.md)：收藏的浏览器本地存储风险与后续服务端加密方案决策
- [docs/frontend/2026-11-01-pre-pr-round-two.md](docs/frontend/2026-11-01-pre-pr-round-two.md)：第二轮静态工程质量审查、真实缺陷样例及合并门槛
- [docs/frontend/2026-11-01-pr-handoff-draft.md](docs/frontend/2026-11-01-pr-handoff-draft.md)：依赖分层 PR 提交边界、审查职责与交接正文模板
- [docs/frontend/2026-11-01-mixed-intent-trust-remediation.md](docs/frontend/2026-11-01-mixed-intent-trust-remediation.md)：混合金融意图、口语省略和伪造附注的可信输出修复与剩余审查门槛
- [docs/赛题解析.md](docs/赛题解析.md)：赛题背景与强制要求
- [docs/设计思路.md](docs/设计思路.md)：零信任架构与产品设计
- [docs/设计细化.md](docs/设计细化.md)：双屏交互与数据令牌化目标设计（部分实现）
- [docs/T-106前后端接口交接.md](docs/T-106前后端接口交接.md)：当前模拟转账及确认接口
- [docs/T-201审计说明.md](docs/T-201审计说明.md)：审计事件、关联及事务边界
- [docs/T-202护栏说明.md](docs/T-202护栏说明.md)：工具调用前子 Agent 护栏、输入边界与风险升级行为
- [docs/T-205计算工具说明.md](docs/T-205计算工具说明.md)：受限 AST 计算工具的语法、限制与错误处理
- [docs/T-204注入防御说明.md](docs/T-204注入防御说明.md)：输入检测、历史遮盖与工具参数白名单
- [docs/T-203熔断限流说明.md](docs/T-203熔断限流说明.md)：用户级连续失败锁定、敏感接口限流与解锁审计
- [docs/T-207实现与兼容说明.md](docs/T-207实现与兼容说明.md)：数据引用、独立密钥及旧库副本升级
- [docs/T-206事务与幂等说明.md](docs/T-206事务与幂等说明.md)：模拟业务事务入口、准备去重、执行重查和升级兼容
- [docs/T-301前端接口说明.md](docs/T-301前端接口说明.md)：月度账单接口及统计口径（后端测试通过，待前端联调）
- [docs/T-302前端接口说明.md](docs/T-302前端接口说明.md)：模拟卡查询和挂失接口（后端测试通过，待前端联调）
- [docs/T-303理财接口说明.md](docs/T-303理财接口说明.md)：模拟理财数据接口、红色申购/赎回与接口分层（后端测试通过，待前端联调）
- [docs/T-306银行数据接口说明.md](docs/T-306银行数据接口说明.md)：负一屏账户、联系人、持仓与风险测评只读接口（后端测试通过，待前端联调）
- [docs/T-304订阅接口说明.md](docs/T-304订阅接口说明.md)：订阅查询/识别、续费提醒与黄色确认取消（后端测试通过，待前端联调）

## 已实现

- 单演示用户 JWT 登录，接口鉴权
- 会话列表 / 新建会话 / 历史消息持久化；新版聊天默认每页加载最近 50 条、按需加载更早历史，历史接口兼容 `limit` 和 `before_id` 游标；详见 `docs/frontend/2026-11-01-chat-history-performance-review.md`
- AgentLoop 对话与 SSE 协议；基础事件为 `delta` / `done` / `error` / `action_required`，另有可信结果与恢复事件 `bill_result`、`card_result`、`operation_result`、`action_warning`；当前每轮先缓冲，暂不实时逐字输出
- LLM 适配层：OpenAI 兼容接口 + 离线 Mock，自动切换
- 前端聊天界面、Markdown 渲染、流式光标、会话抽屉；正式页为响应式“对话 + 资产”双栏，手机资产整屏滑入
- 资产拖拽：六种碰撞矩阵、250 ms 长按、滚动容差、意图胶囊、点击/键盘替代、全局隐私模糊与点击临时显示
- 前置意图：前端只传动作与实体 ID，后端生成 token 化提示词并放在当轮用户原文之前，同时持久化用户可见的胶囊行；token 正文不写入历史
- 硬编码操作确认弹窗（非 Generative UI，AI 无法代为确认）
- 模拟账户余额、最近交易、月度账单和卡片状态只读工具，接入 AgentLoop；查询结果由后端固定格式输出
- 受限计算工具 `calculate`：仅支持数值与基本运算，限制长度、节点、时限和数值范围，结果由后端固定渲染
- 未调用工具时允许经过服务端输出策略检查的问候、能力说明、参数追问和纯知识解释；个人账户查询、资金操作和既往操作状态必须来自 Tool 或明确说明未核实；离线 Mock 不调用银行工具
- 固定代码风控规则已接入模拟转账后端，执行前重新检查日累计、时间和余额
- 前端已接入模拟转账、卡片挂失、理财和订阅动作的确认／验证／执行界面；红色动作模拟验证通过后自动执行，不再额外点击执行。核心只读对话及多工具查询已进行真实 LLM + 模拟银行隔离 HTTP 浏览器联调；真实模型下的转账准备已验证令牌与金额绑定，但完整转账授权的真实浏览器人工验收仍未完成
- 结构化账户／银行卡／联系人引用经服务端归属校验后绑定到工具调用，客户端伪造 ID 不能越权；前置意图采用实体 ID + 服务端 token 化提示词，模型不能改写来源、目标或金额（T-208）
- 模拟理财产品/持仓/风险测评查询，以及红色验证后的模拟申购/赎回；银行数据只读接口 `/api/bank/wealth/*` 与 Agent 操作接口 `/api/wealth/*` 分离，Tool 不经过 HTTP 数据接口
- 接口分层约定：`/api/bank/*` 仅供前端负一屏和服务层封装使用，不注册为 Agent Tool；LLM 不能直接调用银行数据接口
- 负一屏只读数据接口：账户、联系人、理财持仓、风险测评聚合；按用户隔离，不返回令牌或明文号码，联系人只读
- 六种组合动作：内部转账（≤1000 元绿色直接执行、>1000 元黄色确认）、对外转账、收款请求、申购、赎回、持仓转换；均为 SQLite 模拟业务并写审计
- 模拟订阅：查询、续费提醒、最近 6 个月重复订阅识别，以及黄色确认后的取消；只读接口 `/api/bank/subscriptions*` 与操作接口 `/api/subscriptions/*` 分离
- 模拟转账只支持 SQLite，不连接真实银行；确认令牌不会发送给模型或写入会话历史
- 红色动作分为密码/验证码和密码+模拟人脸两级：大额转账为密码，挂失与理财申购/赎回/转换为密码+人脸；最严仅到模拟人脸，不接入真实人脸接口。仅在 `DEBUG=true` 时可用（验证码默认 `123456`），`DEBUG=false` 时拒绝红色操作
- 卡片挂失后阻止关联账户准备或执行尚未完成的模拟转账
- 关键操作持久化审计及按用户隔离的只读接口 `GET /api/audit`；审计失败时模拟转账不会报告成功
- 工具调用前子 Agent 护栏：所有工具都审查服务端行为摘要，并结合北京时间与本轮历史工具调用判断夜间高风险动作、异常目标切换和重复探测；拒绝或异常不再直接拦截，而是把固定代码风险提升一档（绿→黄、黄→红、红→密码+人脸），并写审计；提示词明确只读查询在用途/风险/参数一致时应放行；需配置真实 LLM 才启用
- 注入防御：模型调用前固定规则拦截常见越狱 / 角色覆盖 / 忽略规则，历史消息在模型上下文中再次遮盖，工具参数按注册 Schema 白名单校验
- 异常熔断与限流：用户级连续失败锁定、敏感接口固定窗口限流；锁定 / 限流 / 自动解锁 / 演示手动解锁均写审计
- 模拟账户与工具调用的数据引用、认证加密；用户输入在界面和历史中原样保留，工具结果不向模型返回真实卡号，工具参数必须使用服务端令牌或脱敏字段；需配置独立密钥，详见 T-207 文档

## 后续规划

按 `docs/设计思路.md` 逐步接入：

1. Tool 层：跨场景联动与更多业务场景，按风险等级（绿 / 黄 / 红）注册
2. 风控引擎：补充定位、IP 等环境因子
3. 安全增强：数据令牌化剩余生命周期及前置意图校验
4. 工具层：统一事务 / 幂等规范
5. 任务 DAG、长期记忆、多模态账单识别、MCP 外部生态
6. Docker Compose 部署与演示材料

## 说明

本项目为比赛演示用途，业务数据与操作均为模拟，不对接真实银行系统。
