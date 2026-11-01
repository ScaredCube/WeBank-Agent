# 小We · 第二十批：Agent 异常恢复与金融确认边界

日期：2026-11-01
分支：`feature/ip-object-workspace`

## 问题与修复

已有聊天接口的 SSE event generator 在检测到 `request.is_disconnected()` 后使用 `break` 退出 Agent 事件循环，随后继续进入正常完成并写入 `completed`。这使“模型/金融工具可能已动作，但客户端未收到最终事件”的请求无法被安全地区分。

本轮将显式检测到的断线改为走 `asyncio.CancelledError` 分支：标记 ChatSubmission 为 `interrupted`、不会自动重发银行 Tool、不重新下发确认令牌。同一 `request_id` 的重放继续返回 409；请求状态和操作记录可供人工核对。若银行 Tool 已准备了资金操作，原来的业务 pending 记录保留、不能靠聊天重试触发第二笔准备。

**注意**：`interrupted` 只说明客户端无法确定最终状态，不意味着工具未执行，也不是自动撤销或自动恢复；用户仍需核查待确认操作。该改动只针对 **已被服务端检测到** 的断线，不能替代跨进程持久队列、代理失联检测或分布式 worker lease。

## 新增自动化验收

`backend/tests/test_agent_failure_boundaries.py` 使用 FastAPI 原有真实路由和临时 SQLite、确定性的离线模型替身：

1. 模拟模型完成但连接已断开：请求标记 `interrupted`，同 ID 409，不产生未授权的助手完成消息。
2. 模拟银行 Tool 已成功准备 1 元转账、确认事件尚未发送即断线：`interrupted`、重复请求 409，数据库恰好一笔 pending、账户余额不变，状态 API 不泄露确认令牌。
3. 模拟真实模型超时：安全错误结果、`failed`，相同 request ID 不会再次执行模型或金融 Tool。
4. 模拟 Guard 超时：不创建 PendingAction 或 TransferRequest，不扣款，也不能让模型伪造已转账成功的回复。

既有守护、提交去重、并发唯一约束、跨用户隔离、真实银行模拟金额/确认测试继续保留。每项离线测试不请求 TokenDance，也不读取 API Key。

## 验收方式

```powershell
cd backend
uv run --group dev pytest -q tests/test_agent_failure_boundaries.py tests/test_guard.py tests/test_chat_submission_idempotency.py
# 修改了全局 SSE 状态收敛逻辑，故完整后端回归适用
uv run --group dev pytest -q
```

## 安全交付边界

当前测试只操作 `pytest` 隔离 SQLite 和模型替身，不调用真实银行资金服务、不在浏览器自动确认或执行交易、不重启现有 `8000/5189`。真实 TokenDance 端到端、代理断线、多实例同一任务协调以及生产级审计和部署检查需单独处理。
