# AI 银行智能体

银行 AI 智能体参赛项目的演示骨架。已实现登录、会话持久化、模拟查询与转账后端、固定风控及关键节点持久化审计；前后端业务联调与真实验证仍未完成。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.11+ · FastAPI · Pydantic · SQLModel · uv |
| 数据库 | SQLite（可切换 PostgreSQL） |
| 大模型 | OpenAI 兼容接口（DeepSeek / 通义 / vLLM / Ollama），无 Key 时自动使用离线 Mock |
| 前端 | React 19 · TypeScript · Vite · Tailwind CSS v4 · shadcn/ui 风格组件 |
| 通信 | REST + SSE 流式输出 |

## 目录结构

```
bank_agent/
├─ backend/
│  ├─ app/
│  │  ├─ api/routes/        # health / auth / chat
│  │  ├─ agent/             # LLM 适配层、AgentLoop、工具注册表
│  │  ├─ core/              # 配置、安全（JWT / 密码哈希）
│  │  ├─ db/                # 引擎、初始化、演示用户
│  │  ├─ schemas/           # Pydantic 请求响应
│  │  ├─ services/          # 会话与消息读写
│  │  └─ main.py
│  └─ tests/
├─ frontend/
│  └─ src/
│     ├─ components/        # 基础 UI、聊天组件、确认弹窗
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
- 演示夜间风控默认使用北京时间 00:00–06:00；可通过 `RISK_NIGHT_START_HOUR` 和 `RISK_NIGHT_END_HOUR` 调整起止整点，具体业务时段尚待确认

接入真实模型时修改 `backend/.env`：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173，演示账号 `demo / demo123`。

开发环境下 Vite 会将 `/api` 代理到 `http://127.0.0.1:8000`，无需额外配置跨域。

### 测试

```powershell
cd backend
uv run pytest

cd ../frontend
npm run lint
npm run build
```

## 文档

- [CLAUDE.md](CLAUDE.md)：协作规范、开工前阅读要求与文档同步义务
- [docs/项目汇报.md](docs/项目汇报.md)：当前架构、已完成工作、验证结果与已知限制
- [docs/TODO.md](docs/TODO.md)：任务编号、优先级、验收标准与里程碑
- [docs/赛题解析.md](docs/赛题解析.md)：赛题背景与强制要求
- [docs/设计思路.md](docs/设计思路.md)：零信任架构与产品设计
- [docs/设计细化.md](docs/设计细化.md)：双屏交互与数据令牌化目标设计（部分实现）
- [docs/T-106前后端接口交接.md](docs/T-106前后端接口交接.md)：当前模拟转账及确认接口
- [docs/T-201审计说明.md](docs/T-201审计说明.md)：审计事件、关联及事务边界
- [docs/T-207实现与兼容说明.md](docs/T-207实现与兼容说明.md)：数据引用、独立密钥及旧库副本升级
- [docs/T-301前端接口说明.md](docs/T-301前端接口说明.md)：月度账单接口及统计口径（后端测试通过，待前端联调）
- [docs/T-302前端接口说明.md](docs/T-302前端接口说明.md)：模拟卡查询和挂失接口（后端测试通过，待前端联调）

## 已实现

- 单演示用户 JWT 登录，接口鉴权
- 会话列表 / 新建会话 / 历史消息持久化
- AgentLoop 对话与 SSE 协议；当前每轮先缓冲，暂不实时逐字输出
- LLM 适配层：OpenAI 兼容接口 + 离线 Mock，自动切换
- 前端聊天界面、Markdown 渲染、流式光标、移动端侧栏
- 硬编码操作确认弹窗（非 Generative UI，AI 无法代为确认）
- 模拟账户余额和交易只读工具，接入 AgentLoop；查询结果由后端固定格式输出
- 未调用工具时使用固定提示，离线 Mock 不调用银行工具
- 固定代码风控规则已接入模拟转账后端，执行前重新检查日累计、时间和余额
- Agent 可以准备模拟转账并发送待确认事件；确认与执行分开，前端尚未接入，当前界面无法完成确认
- 模拟转账只支持 SQLite，不连接真实银行；确认令牌不会发送给模型或写入会话历史
- 红色模拟转账仅在 `DEBUG=true` 时使用固定测试码（默认 `123456`）；不是生产多因素验证，`DEBUG=false` 时拒绝红色转账
- 关键操作持久化审计及按用户隔离的只读接口 `GET /api/audit`；审计失败时模拟转账不会报告成功
- 模拟账户及本轮输入号码的数据引用、认证加密与聊天入站脱敏；需配置独立密钥，详见 T-207 文档

## 后续规划

按 `docs/设计思路.md` 逐步接入：

1. Tool 层：转账、账单、卡片、理财等，按风险等级（绿 / 黄 / 红）注册
2. 风控引擎：功能分级 + 时间、定位、IP 等环境因子
3. 安全护栏：独立会话子 Agent 检查工具调用，注入防御与熔断
4. 安全增强：异常熔断、数据令牌化剩余生命周期及前置意图校验等尚未完成
5. 任务 DAG、长期记忆、多模态账单识别、MCP 外部生态
6. Docker Compose 部署与演示材料

## 说明

本项目为比赛演示用途，业务数据与操作均为模拟，不对接真实银行系统。
