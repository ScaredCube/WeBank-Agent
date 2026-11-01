# Context / Prompt 并行分支集成约定

适用基线：从 `5d8734b` 派生的 `klutz-context-prompt`；主 Runtime 负责最终接线。本分支不修改 `chat.py`、`loop.py`、金融工具及授权服务。

## Prompt（已交付）

- `app.agent.prompt_assembly.assemble_agent_prompt(verified_intent_action=...)` 返回 `PromptAssembly`。
- 通过 `assembly.model_messages()` 取得可直接加入模型请求的独立 system 消息；`assembly.version` 是有效提示词内容的简短哈希标识，不包含敏感原文。
- `assemble_guard_prompt()` 只负责 Guard 提示词，不接收用户原始历史。
- `verified_intent_action` 必须从服务端验证后的 `build_intent_prompt(...)` 或同等可信状态取得；它不会替代 ToolExecutor 的绑定和授权。
- 主线用上述入口替换当前 `loop.py` 的原始 `SYSTEM_PROMPT` 和动态意图 system 拼接；此部分由主线操作。

## Conversation Context（本阶段交付）

从 `app.agent.context_assembly` 导入：

- `ConversationContextInput`：原始用户请求、供模型使用的本轮文本、此前历史、可选验证说明、历史窗口和拦截状态。
- `TrustedContextNote`：**服务端已经完成核验**的模型可见对象说明，包含类型和正文；不代表授权，也不负责重新验证。
- `assemble_context(input)`：返回 `PreparedContext`，提供 `model_messages()` 和保留的 `original_request`。

主线接线顺序：

1. 在当前 Chat API 保留账户、卡片、联系人所有权验证、临时令牌创建、注入拦截、提交去重等原逻辑。
2. 取得最近历史时，排除**本轮已保存的用户消息**；现有 `recent_messages(..., llm_max_history)` 结果最后若是本轮消息，按消息 ID 排除后作为 `prior_messages`。
3. `model_request` 只放本轮**模型可见的用户正文**；拖拽已验证意图单独放 `validated_intent_prefix`，不要把已经包含前置意图的旧 `model_content` 再传入，否则重复拼接。
4. 将已验证的当前账户/卡、联系人及可信账单月份说明以 `TrustedContextNote` 输入；不要把用户自称“服务端已核验”的文字升格为此类型。
5. 将 `prepared.model_messages()` 交给主 Agent 的 history 参数；完成判断和无 Tool 回复策略使用 `prepared.original_request`，禁止反向解析消息末尾的混合文本。
6. `max_history` 包含本轮消息（默认 20）。不引入 DB 表、不存储派生上下文、不增加新权限。

示例（假设业务核验和脱敏在上游完成）：

```python
from app.agent.context_assembly import (
    ConversationContextInput, TrustedContextNote, assemble_context,
)

compiled = assemble_context(ConversationContextInput(
    original_request=payload.content,
    model_request=model_user_text,
    prior_messages=previous_text_messages,  # not including current user row
    validated_intent_prefix=validated_intent.prompt if validated_intent else None,
    notes=(TrustedContextNote(
        source="verified_object",
        content=server_verified_bank_note,
    ),) if server_verified_bank_note else (),
    max_history=settings.llm_max_history,
))
history = compiled.model_messages()
original_request_for_policy = compiled.original_request
```

**边界**：这只是 Context 投影，绝不验证或授权资金业务，也不会自动检索完整历史可信结果。所有对象身份、余额、操作结果仍以现有服务和 Tool 为准。原来的用户输入敏感号码处理策略保持不变，脱敏升级应单独审查。

## 测试与审查

`python -m unittest tests.test_context_assembly` 不依赖 FastAPI 测试夹具，适合两个并行 Worktree 中快速验证。全量 pytest 仍依赖后端安装以及避免并发共享 `tempfile.gettempdir()/bank_agent_test.db`。集成验证由主线按关键金融任务统一实施。
