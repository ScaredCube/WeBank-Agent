# Generative UI 集成交接（草稿）

日期：2026-11-02
状态：待主线审阅；独立分支尚未推送或创建 PR。

## 范围与对照基线

本记录描述 `远程开发空间/klutz-gui-integration` 的 Generative UI 集成工作区。核对时目标树 HEAD 为 `bb1bb95a89186ae8d158b911fe5739b1bdc492ca`（`feature/klutz-gui-integration`），`klutz-runtime` HEAD 为 `a8f00fb9c5ab78725c4871858be54a54c2ef371e`；两者不是同一基线。目标工作区还包含多项未提交修改及新文件。

因此，本文把目标树相对自身 HEAD 的改动与两棵工作树的直接文件对照分开记录。后者用于发现共享文件的整合风险，不能直接视为 PR diff 或可原样 cherry-pick 的补丁。

## 接口与 Schema 变化

- 聊天发送接口 `POST /api/chat/conversations/{conversation_id}/messages` 增加可选 `view_context: {view_id, revision}`。后端先按用户、会话和已保存视图版本解析上下文，再交给续问流程；客户端不能通过该字段提交可信金额或账单事实。请求幂等指纹包含该上下文。
- 后端 SSE 增加 `ui_status`（`composing` / `fallback`）和 `ui_view` 事件，聊天历史消息可以带 `ui_view` 快照。前端另外预留 `subscription_result` / `subscription_results` 的解析类型；当前后端未提供该事件或消息字段，不能据此前端类型声称订阅链路已接通。原有账单、卡片及金融操作事件仍由既有聊天流程处理。
- 新增已认证视图 API：`GET /api/views/{view_id}` 读取最新版本，传 `revision` 查询指定历史版本；`POST /api/views/{view_id}/interactions` 提交 `{event_id, base_revision, action, value?}`。交互有幂等键及版本冲突检查，读取响应设置为不缓存。
- 后端 `ViewEnvelope` 与前端 Zod Schema 都采用严格、版本化的 allowlist。模型负责受限视图布局；组件、属性、数据引用、图深和大小均受校验。金额以整数分传递。后端定义 `ViewInteractionRequest`，动作范围限于分类/记录选择、排序、筛选和清除筛选等受控操作。
- 账单分类的标签、金额与笔数由服务端可信结果生成。视图选择后，工作区展示所选分类状态及对应可信金额/笔数；不从分类汇总虚构普通交易明细。生成器失败时以 `ui_status=fallback` 表示，原有可信固定结果仍可见。

主要实现位置：`backend/app/schemas/chat.py`、`backend/app/schemas/generative_ui.py`、`backend/app/api/routes/chat.py`、`backend/app/api/routes/views.py`、`backend/app/services/view_service.py`、`backend/app/services/trusted_ui_results.py`、`backend/app/agent/ui_composer.py`、`backend/app/agent/view_followup.py`；前端协议入口在 `frontend/src/lib/api.ts`、`frontend/src/lib/sse.ts` 和 `frontend/src/features/generative-ui/`。

## 数据库与依赖

新增四张 SQLite 视图表：

| 表 | 用途 |
| --- | --- |
| `uiview` | 视图归属及当前版本指针 |
| `viewrevision` | 加密、不可变的视图版本快照 |
| `viewinteraction` | 按 `(view_id, event_id)` 去重交互并记录结果版本 |
| `messageview` | 将聊天消息绑定到不可变的视图版本 |

`backend/app/db/schema_guard.py` 将视图表加入启动检查；非空旧 SQLite 库缺表或结构漂移时会拒绝启动。`backend/scripts/check_generative_ui_schema.py` 默认预检，只有显式 `--apply` 才会先备份并创建缺失视图表；漂移表不自动修复。README 说明全新空库仍可启动初始化，既有 SQLite 库须完成相应迁移。本脚本只处理 SQLite，不提供 PostgreSQL 迁移；本轮没有执行数据库迁移。

前端依赖新增并锁定 `@json-render/core@0.21.3` 与 `@json-render/react@0.21.3`（`frontend/package.json`、`frontend/package-lock.json`）。本次 Generative UI 接入没有新增后端运行时包。

## 保留的运行时边界与现有能力

- 金融工具的授权仍由 `ToolExecutor` 执行。其改动为可信结果补充服务端内部来源信息，模型输出的布局不能授权工具调用或提供可信金融数值。
- 视图上下文只携带视图 ID 和版本；服务端通过已保存的结果重新解析所选分类/记录。聊天消息历史绑定视图快照，允许读取旧消息版本并在刷新后恢复。
- 保留既有账单结果、卡片和金融操作流程。Generative UI 是只读分析路径，没有新增转账或其他资金执行；金融确认和资产拖拽未纳入本次改动目标。
- 前端仍嵌入现有 `AppShell` 与聊天消息列表。失败/重试路径释放 ViewPanel 的忙碌状态；视图收藏入口没有接入持久化存储，首轮不提供。既有账单收藏不属于本功能的持久化扩展。
- 代码中存在订阅数据 Schema 和展示组件，但首轮交付以账单分析为准；后端尚未接出订阅视图事件，尚无真实模型订阅链路验收。

## 与 `klutz-runtime` 的共享文件差异及整合风险

对两棵工作树进行的直接文件 diff 显示，以下共享文件已有明显差异。示例差异规模为参考树到目标树的文件级 diff 统计，不是单一 Generative UI 提交的行数：

| 共享文件 | 直接对照摘要 | 整合关注点 |
| --- | --- | --- |
| `frontend/src/pages/Chat.tsx` | 275 行差异（211 增、64 删） | 工作区入口、历史版本及既有聊天行为需要逐段合并 |
| `frontend/src/features/chat/useChatController.ts` | 46 行差异（38 增、8 删） | SSE 事件、请求上下文、完成/恢复状态 |
| `backend/app/api/routes/chat.py` | 54 行差异（53 增、1 删） | 聊天输入、可信上下文验证及幂等 |
| `backend/app/models.py` | 52 行差异（51 增、1 删） | 新视图模型与主线 ORM 变化 |
| `backend/app/services/chat_turn.py` | 99 行差异（90 增、9 删） | SSE 时序、生成失败保护及完成持久化 |
| `backend/app/db/schema_guard.py` | 90 行差异（79 增、11 删） | 两组 schema 门禁及迁移兼容 |
| `frontend/src/lib/api.ts`、`frontend/src/lib/sse.ts` | 分别 27、31 行差异 | 请求/消息 Schema 与事件解析 |

另外直接对照有差异的共享文件包括 `frontend/src/app/AppShell.tsx`、`frontend/src/components/chat/MessageList.tsx`、`frontend/package.json`、`backend/app/agent/tool_executor.py`、`backend/app/services/chat_messages.py`、`backend/app/schemas/chat.py`、`backend/app/main.py`、`backend/app/core/config.py`、`backend/app/agent/loop.py`、`backend/app/agent/context_assembly.py` 和 `backend/app/agent/read_completion.py`。目标工作区还包含账单工具、提交幂等、恢复和相关测试的修改，合并时应检查这些共享运行时变化的来源与主线是否已有对应演进。

建议主线按共同祖先逐文件三方整合，先确认当前主线提交与数据库状态，再处理聊天路由、轮次持久化、模型/schema 门禁、SSE 和聊天页面这些高冲突点；不要整目录覆盖。新增的生成器、可信结果、视图服务/API、前端 `features/generative-ui` 及 schema 检查脚本需要作为独立功能审阅。目标分支与参考树 HEAD 不同，因此仅凭目录对照无法确定其中每项差异的归属。

## 验证证据

| 项目 | 结果 | 证据边界 |
| --- | --- | --- |
| 前端单测：`npm run test` | 33 个文件、228 项通过 | 包括收到终止 SSE 后关闭未结束流的回归 |
| 前端 lint：`npm run lint` | 退出码 0，9 条 warning | 有 warnings，不是零告警 |
| 前端构建：`npm run build` | 通过 | Vite 提示有大于 500 kB 的 chunk |
| 浏览器 E2E：`npm run test:e2e -- --workers=4` | 15/15 通过 | 含 4 项 Generative UI 浏览器用例，但它们拦截 `/api/**` 并使用 API fixture，不等于真实服务端验收 |
| 依赖检查：`npm ls --depth=0` | 通过 | 包含上述 json-render 版本 |
| 后端测试（不含 Prompt 基线） | 571 项及 31 个 subtest 通过 | 独立临时数据库；Prompt 基线另测 4/4 通过 |
| 真实模型 API 分类场景 | 通过 | 首轮 1 次月账单工具、续问 0 次工具；分类金额/笔数、视图历史、余额不变均通过。此前样本出现多次工具调用和 Composer 超时 |
| 真实模型浏览器全流程 | 一次通过 | 隔离合成银行和真实 API；分类选择、可信续问、原始及最新版本刷新恢复通过，余额/转账状态未变，浏览器错误 0。模型非确定性仍需持续观察 |
| Prompt 行为审查 | 基准静态 Prompt 未变，基线测试 4/4 通过 | 见 `docs/prompt-reviews/2026-11-02-generative-ui-runtime-review.md`；同场景每版为单次样本 |

真实服务端浏览器脚本 `frontend/scripts/competition_generative_ui_live.cjs` 不拦截 API，通过 runner 的隔离合成库执行上述流程。运行入口为 `backend/scripts/run_competition_e2e.py --live --browser-entrypoint scripts/competition_generative_ui_live.cjs`；需使用项目 Python 环境及已配置的测试模型。runner 默认仍指向原浏览器脚本，并检查合成账户余额与转账状态。

## 尚待完成

1. 合并前对目标部署数据库运行只读迁移预检，按数据库类型决定升级方案；本轮未对现有数据库执行迁移。
2. 对照当前主线逐文件三方整合上表中的共享改动，尤其保留主线资产拖拽及金融确认流程，并在整合后的代码上重新运行测试。
3. 持续观察模型生成耗时和偶发回退；单次成功不能代表稳定性。订阅分析、视图收藏及其他未列入账单首轮验收的能力需单独确认范围和持久化方案。
4. 推送独立分支并提供相对 `klutz-runtime` 的审查入口；未经主线决定不合并。
