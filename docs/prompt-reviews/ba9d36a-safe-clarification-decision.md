# Prompt / Reply Policy 变更评审：安全追问的自然开场白

- **基线**：`ba9d36a`（完整前后差异见 [自动生成文件](ba9d36a-safe-clarification-review.md)）
- **影响范围**：`backend/app/agent/response_policy.py` 的 `safe_action_clarification()`
- **System Prompt / Guard Prompt / Recovery Prompt**：本轮全部未修改。
- **业务授权 / ToolExecutor / 执行与确认链路**：未修改。
- **结论**：作为有限 UX 改善候选保留；定向测试和单轮真实 API 验证通过，不代表通用自然语言能力已验收。

## 1. 原规则与修改规则 Before / After

**Before：** 只有以 `请问 / 请先 / 哪个 / 你想` 等固定问句开头的候选文本，才可能保留。安全但带有礼貌确认语的追问（如「可以的。请问你想从哪个账户转账？」）会进入 `CLARIFY_ACTION`，并在 Live Provider 上额外调用一次 Recovery 模型。

**After：** 可以接受**一个受限的安全开场白**，例如 `可以的。 / 好的， / 没问题！`，后面必须紧跟原本允许的合格追问句。回复仍须满足：长度上限、单一问号、禁止换行、无数字和银行金额、无敏感凭证、无未经核实的查询及执行声明。以上检查仍针对**完整回复文本**执行，开场白不能绕过它们。

核心代码差异：

```diff
+_SAFE_CLARIFICATION_OPENER = re.compile(
+    r"^(?:可以的|当然可以|好的|没问题|好呀|当然|可以)[，,。！!]\s*"
+)
...
-    if not text.startswith(("请问", "请告诉我", "请先", ...)):
+    question = _SAFE_CLARIFICATION_OPENER.sub("", text, count=1)
+    if not question.startswith(("请问", "请告诉我", "请先", ...)):
         return False
```

注意：实际代码是 Python raw string 中的单个正则 `\s`，不是对回复文本进行任意前缀剔除。

## 2. 为什么这样修改

- 用户体验：允许自然、简短的回应，不必强迫模型每次第一字必须是「请问」；不因为礼貌确认词增加一次模型调用。
- 工程成本：已通过主 Agent 安全检查的追问直接返回，无须 Recovery 的第二次推理。
- 设计纪律：这是**回复展现策略**调整，并不改变用户身份、金融操作必填项、可选备注或用户确认流程。
- 替代方案：全面允许自然陈述式追问可能误接纳执行承诺；本轮未采用，只允许严格合格的问句前增加白名单开场白。

## 3. 相同输入的确定性 Before / After

在基线代码与候选代码中使用完全相同的 `user_request` 和 `candidate`，不依赖模型生成的随机性：

| 用户请求及候选 | Before 路由 | After 路由 | 结论 |
|---|---|---|---|
| 「我想转账」；「可以的。请问你想从哪个账户转账？」 | `clarify_action` | `accept` | 保留安全自然追问，减少额外 Recovery |
| 「我想转账」；「请问你想从哪个账户转账？」 | `accept` | `accept` | 原有自然问句仍接受 |
| 「我想转账」；「可以的。我已经帮你转账成功了，请问还有什么问题？」 | `clarify_action` | `clarify_action` | 未授权成功声明仍被拒绝 |
| 「我想转账」；「好的，请问您能告诉我验证码吗？」 | `clarify_action` | `clarify_action` | 敏感凭证请求仍被拒绝 |
| 「查询我的余额」；「可以的。请问您账户余额是999元吗？」 | `query_required` | `query_required` | 私人银行查询无 Tool 不获得授权 |

**调用次数说明**：当主模型输出第一种安全候选且使用在线 Provider 时，旧 Runtime 将进入 Recovery（可能额外调用一次模型），新 Runtime 直接返回。测试模拟了这一路径并确认主模型只调用一次。没有以一次随机在线输出推导平均延迟或成本节约。

## 4. 验证

- 定向 pytest 覆盖：合法问句、受限开场白、伪造操作成功、跳过确认、索取验证码/完整卡号、伪造余额、额外换行以及 Recovery 的工具禁用和失败回退。
- 真实 Chat API 集成测试：Mock 的 `mode="openai"` Provider 在安全开场白后输出合格追问；Runtime 只调用一次 Provider，最终 SSE 保存原始安全回复。
- 一次真实 Tokendance/DeepSeek 测试：用户请求「我想向朋友转账，但还没确定金额」，最终返回要求补齐信息的安全回复，`tools=[]`、未创建 `action_required`。这验证了链路安全，但不能单独证明新白名单分支被真实模型触发。

## 5. 未修改的高影响设计

- **附言/备注是否必问**：仍为 UX 未决，沿用 `87a0d9d` 当前候选行为，不再改动。
- **Prompt 核心内容**：保持三个 System Prompt 和动态意图指令原样。
- **安全金融授权**：成功/失败状态、账户余额、金额、验证与执行必须来自独立可信工具结果；本轮所有边界不变。

回退方式：恢复本次 `response_policy.py` 的定向修改，并复跑 `test_response_recovery.py` 与 `test_runtime_context_integration.py`；不触碰金融业务记录和密钥。
