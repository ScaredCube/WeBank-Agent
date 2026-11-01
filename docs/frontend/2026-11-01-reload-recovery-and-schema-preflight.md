# 第十八批 · 刷新后请求恢复、异常中断收敛与数据库升级预检

时间：2026-11-01
分支：`feature/ip-object-workspace`（独立工作树）
承接：`c215268` 的 Agent request_id 去重协议

## 1. 标签页级请求恢复

前端新增 `frontend/src/features/chat/pending-request.ts` 与测试：只在本标签页 `sessionStorage` 中保存以下**非机密元数据**：`conversationId`、`requestId`、`createdAt`。最多 12 条，24 小时过期，非法/过期值自动清理。

**不会保存**对话正文、引用对象、银行数据、登录凭证、短期 Token、确认令牌或金融账户 ID。刷新后先以当前登录身份通过后端 `GET /api/chat/conversations/{id}/requests/{requestId}` 重新核验所有权，状态查询属于只读操作：

- `completed`：提示已完成、回历史查看；移除恢复线索，不再发 POST；
- `action_pending`：提示去操作记录核对，不重新获取确认令牌，移除线索；
- `processing`/`interrupted`/`failed`：提示仍不确定，保留线索，禁止自动执行；
- 404（例如用户切换或无权限访问）：清理无效线索；其他网络错误保留线索以便后续核查。

保留同标签页多个会话的恢复线索，不会因一个请求结束而清除其它请求。该机制**只核对结果**；不会自动重连或恢复执行 Agent 任务。独立浏览器标签页之间不共享恢复列表。

## 2. 后端完成状态与加密历史同一事务

`_persist_assistant` 现在能够在同一数据库事务中完成：
- 插入助手回复；
- 加密写入可信账单/银行卡结果快照（若存在）；
- 将对应 `ChatSubmission` 标记为 `completed` 并绑定该回复 ID。

任一步失败，事务不提交，以减少“助手回复已写但请求仍处理中”的不一致窗口。

已有的待确认动作仍然使用独立业务幂等机制。一次转账准备成功但服务进程在更新聊天状态前退出时，系统**不会重新准备金融操作**，用户必须去操作记录核对。这是故意保守的 fail-closed 策略，不能把无结果视为执行失败。

## 3. 服务端陈旧请求的安全收敛

在 `chat_submissions.py` 中增加仅针对超过 30 分钟、状态仍为 `processing` 的保守转换，标记为 `interrupted`。由服务启动和请求状态 GET 触发；不会重新执行 Tool 或返回确认令牌。

这是一种超时后的**状态标记**，不能准确判定外部金融工具是否已完成，更不等于真正的任务队列恢复。多实例同时执行任务、长于 30 分钟的合法任务和进程级崩溃仍需专门的分布式任务协调设计。

## 4. SQLite 数据库升级预检工具

新增 `backend/scripts/check_chat_schema.py`，默认执行**只读检查**，核对 `conversationselection` 与 `chatsubmission` 两张新增表、必须字段以及请求 ID 唯一约束；若缺少则返回非零状态，不做任何修改。

在已经存在的 SQLite 数据库上可**显式**执行 `--apply`：
1. 验证当前基础表和现有聊天表结构符合预期，结构漂移则拒绝操作；
2. 通过 SQLite 在线备份 API 生成带时间戳的整库快照；
3. 仅创建两张缺少的聊天状态表；
4. 再次检查结构与唯一约束，第二次执行不重复创建。

在 `backend` 目录使用项目已有 Python 环境：

```powershell
python scripts/check_chat_schema.py
# 维护窗口、备份路径与当前 DATABASE_URL 核实后：
python scripts/check_chat_schema.py --apply
```

**注意**：该脚本是新增表的迁移预检工具，不是完整的 Alembic 或通用数据库迁移系统；`app.db.session.init_db()` 当前仍调用 `SQLModel.metadata.create_all()`。正式上线前应先停止写入业务服务，备份并验证恢复，在批准的维护窗口中进行 schema 迁移。真实团队数据库没有被本轮脚本修改。非 SQLite 数据库不会被此脚本修改。

## 5. 实际验收

- 后端 **301/301** 全量测试通过，包括新增备份/恢复、结构漂移拒绝、并发幂等、陈旧请求不重放与旧有银行安全测试；
- 前端 **209/209** 全量测试通过。新增临时存储有效期与跨请求隔离、刷新后 completed/action_pending/processing 行为；修复测试环境 sessionStorage 隔离；
- 生产构建通过，Lint 0 错误、1 条既有 WorkspacePanel 警告。
- 使用真实 TokenDance DeepSeek + 隔离模拟银行数据，在 Chrome **1440px/390px** 完成：登录 → 引用账户 → 查询 2026-01 账单 → 模拟刷新瞬间留下的恢复线索 → 刷新 → 重新 GET 请求状态 → 恢复历史结果。两次均通过，刷新后**无额外 POST**、临时线索清理、无页面错误或横向溢出。
- 验收资料：`D:\competition\深圳国际金融创新大赛\远程工作空间\UX验收_2026-11-01_请求幂等与断线恢复\browser_reload_recovery.cjs`、`browser-recovery-1440.png`、`browser-recovery-390.png`。

## 6. 未完成边界

- 生产级事务迁移和回滚演练、非 SQLite 数据库迁移、跨设备请求恢复、长任务持久队列与精确的服务端进度状态；
- 对并发多实例还需要数据库级主键/锁约束以外的任务所有权与租约协调；
- 用户主动创建一条新的、使用新 request_id 的相同资金准备请求仍属于**新请求**，不会被本层去重。金融准备操作必须继续遵守原有风控与用户确认流程。
