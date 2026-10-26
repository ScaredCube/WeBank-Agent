# AI 银行智能体

银行 AI 智能体参赛项目的工程骨架。当前版本（walking skeleton）已打通登录、多轮对话、流式响应与会话持久化，业务工具、风控与审计模块按文档规划预留了扩展位置。

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
- 未配置 `LLM_API_KEY` 时自动进入 Mock 模式，可离线跑通全链路

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

## 已实现

- 单演示用户 JWT 登录，接口鉴权
- 会话列表 / 新建会话 / 历史消息持久化
- AgentLoop 多轮对话，SSE 逐字流式输出
- LLM 适配层：OpenAI 兼容接口 + 离线 Mock，自动切换
- 前端聊天界面、Markdown 渲染、流式光标、移动端侧栏
- 硬编码操作确认弹窗（非 Generative UI，AI 无法代为确认）
- 工具注册表接口骨架与 `action_required` 事件协议

## 后续规划

按 `docs/设计思路.md` 逐步接入：

1. Tool 层：转账、账单、卡片、理财等，按风险等级（绿 / 黄 / 红）注册
2. 风控引擎：功能分级 + 时间、定位、IP 等环境因子
3. 安全护栏：独立会话子 Agent 检查工具调用，注入防御与熔断
4. 审计：完整决策链路与执行日志，确认令牌服务端校验
5. 任务 DAG、长期记忆、多模态账单识别、MCP 外部生态
6. Docker Compose 部署与演示材料

## 说明

本项目为比赛演示用途，业务数据与操作均为模拟，不对接真实银行系统。
