# Runtime 主线集成交接（主线已推进至 2733c68）

审查时间：2026-11-02。本次以 `klutz-runtime` 的实际工作区源码进行接口对照；审查期间其更改已提交为 `2733c68`，当前主线工作区干净。本分支始终未触碰主线文件。

## 1. 不需要新架构；四个真实接线位置

### a. `agent/loop.py` 构造 system 消息处

当前 Loop 初始化 `messages=[{"role":"system","content":SYSTEM_PROMPT}]`，然后按 `required_intent_tool(intent_action)` 追加另一条 system 消息。用 `assemble_agent_prompt(verified_intent_action=intent_action).model_messages()` 替换这两处拼接。

注意：`required_intent_tool()` 当前支持的 6 种动作与本分支 `_INTENT_TOOL_NAMES` 逐一对应（transfer、internal_transfer、collect、purchase、redeem、convert）；主线已有 `ToolExecutor` 继续负责实际工具绑定和验证。**不要让 Prompt 变成 Tool 权限来源。**

### b. `api/routes/chat.py` 完成对象核验后的历史装配处

当前 Route 先构造 `display_content`/`model_content`，逐次把可信拖拽意图、手机号工具引用、金融对象说明、历史账单月份说明附加到 `model_content`，再将已入库用户消息的最后一条替换成该混合文本。

改为由 Route **负责全部可信数据读取和 Token 创建**，只将已核验的内容作为 `TrustedContextNote` 传递给 `assemble_context`：

- `original_request=payload.content`（保持原始请求用于分类与完成判断）
- `model_request=payload.content`（当前行为是向模型保留用户原文；不要未经审查就改变脱敏策略）
- `validated_intent_prefix=intent_prompt.prompt`，如存在；
- `notes`：来自 `issue_phone_tool_references` 的临时 Token 说明、账户/卡/联系人验证说明、历史账单说明等；不得未经上游核验自行构建；
- `prior_messages`：存储顺序的、最近 N 条历史，**严格排除本轮刚 append 的用户消息 ID**，不要重复添加本轮；
- `max_history=settings.llm_max_history`；装配结果包括当前一条用户消息。

原来附加在 `model_content` 中的各段说明需要改成可单独加入 `notes` 的变量；如果保留原混合 `model_content` 又设置 notes，会**重复向模型注入**。

`PreparedContext.original_request` 给完成/回复策略，`PreparedContext.model_messages()` 给 Loop；来源列表是一个**出处清单**（历史消息与当前注释来源），不是逐条 message 的一对一索引。

### c. `agent/loop.py` no-Tool 回复处

当前 Loop 从 history 末尾回查 `latest_request` 并调用 `tool_free_reply()`。主线的 `AgentLoop.stream()` 现已有 `original_request` 参数，`ChatTurn` 也已经传入它。

改为：

```python
decision = decide_no_tool_reply(
    "".join(content),
    user_request=original_request or "",
    financial_context=bool(
        verified_account_token or verified_card_id
        or verified_contact_token or has_selected_contact
    ),
)
```

- `ACCEPT`：直接输出 `decision.safe_text`，不额外调用模型。
- `QUERY_REQUIRED` / `VERIFY_STATUS`：是否补查 Tool 由 Runtime 判断；**表达恢复不能冒充已查询**。
- `CLARIFY_ACTION`：模型若已提出安全且有用的短问句，会得到 `ACCEPT`，无需第二次 API；否则可按需调用 `recover_no_tool_reply(decision, model=self.llm)`。
- `REJECT_CANDIDATE`：直接使用 `safe_text`；不要把不可信候选回复送进另一次模型。

Recovery 不要在原候选文本发送给客户端以后才执行。仍须先缓冲、审核，最后发出 `delta`；超时或格式错误保留安全后备回复。

### d. `services/chat_turn.py` 的状态持久化边界

当前 `ChatTurn` 负责 SSE 事件、账单/卡结果保存和 `ChatSubmission` 状态。保持此边界，不在 Context/Prompt 模块内创建数据库 session、金融操作、SSE 事件或 PendingAction。

`response_recovery.py` 仅生成一句附加追问，原 Tool 结果/回执仍在现有可信业务流程中；不应在 Task Controller 将这句追问视为任务完成证据。

## 2. 已核对的兼容性和边界

- `ChatTurn.original_request` 和 `AgentLoop.stream(original_request=...)` 已存在，可以直接传递，不需要新增任务表。
- Prompt 的 action 映射与当前 `ToolExecutor` 匹配，Prompt 本身不生成实际授权。
- `ConversationSelection` 的只读延续仍由 Route 重新检查账户所有权；Context 模块不进行金融验证。
- `recent_messages()` 返回最新 N 条**含当前新存储的用户消息**；必须用消息 ID 排除本轮，否则重复当前请求。
- `Response Recovery` 使用既有 `LLMProvider.stream(messages, tools=None)`，不引入外部 SDK、数据库或新的 Agent Loop。
- 审查期间主线的 `loop.py`、`read_completion.py`、`chat.py`、`chat_turn.py` 修改已提交至 `2733c68`，此后检查主线工作区为干净状态。集成前仍须重新执行 `git status`，确保没有新一轮未提交工作，不得强制覆盖或清理其工作区。
- **本次仅进行对照审查，未在主线执行集成回归。** 自有分支的模块契约测试并不等于端到端验收。

## 3. 仍然存在的限制

- `safe_action_clarification()` 是保守的问句检测，优先避免虚构执行状态；对于更长的自然解释，仍可能使用保底文本。实际自然语言体验需最终通过真实供应商测试。
- Recovery 只接收预设的非敏感场景，不知道上游哪些字段已经选择，因此有可能产生多余追问。主线可根据可信对象状态决定跳过 Recovery 或使用现有 `safe_text`，不应因此给 Recovery 发送原始账户详情。
- Context 装配目前不做长期摘要、跨会话语义检索或自动 Tool 查询；这与比赛当前开发边界一致。
- 原始 `tool_free_reply` 仍用于现有运行路径；新行为只有主线明确接入 `decide_no_tool_reply` 后才会生效。

## 4. 集成顺序和必要验证

先合入 Prompt/Context/Response 的独立模块，再让主线修改两处调用点（路由装配与 Loop 最终回复），最后对照 6 种前置意图、普通问候、转账缺失字段、余额查询失败、状态未核实、复合查询、账户引用与历史账单追问等场景做**一次重点回归**。

不能以本分支独立模块测试通过作为已经集成成功的证据。金融工具权限、SSE 与原有业务回执规则的验证仍归主线负责。
