# 小We · Prompt 资产评审规范

> 生效范围：System / Guard / Recovery Prompt、动态意图指令、Tool Schema/Description，以及程序化回复、任务完成和操作确认条件。Prompt 属于会改变 UX 的产品资产。

## 审查顺序

1. **确定基线**：记录当前已知版本的完整 Commit（旧 Prompt）和工作区状态。查清实际模型接收的是何种动态装配结果，避免只看单一文本文件。
2. **生成 Before / After**：从 backend 目录执行以下命令，比较历史基线与候选修改。工具只读 Git 源码与静态 Prompt；不访问用户数据库、环境变量中的秘密或远程模型。

   ```powershell
   cd backend
   uv run python scripts/review_prompts.py --base <旧版commit> --output ../docs/prompt-reviews/<本次变更>.md
   ```

3. **逐条解释影响**：每项修改写出原文、候选原文、目标问题、UX 取舍、金融授权与安全不变量、可回滚方式；将修改分为「身份与沟通」「工具选择」「完成判断」「风险授权」「前端交互」。
4. **同场景行为验证**：记录相同用户输入、选中对象、数据库种子、模型及参数、两版完整工具调用轨迹和最终 SSE 回复。分别判断完整性、自然度、重复提问、响应开销、金融安全，不能用一次成功调用 Tool 取代 UX 评价。模型非确定性时需重复或说明样本不足。
5. **提交门槛**：高影响条款（例如转账确认、备注是否必须问、真实执行条件、风险判断、可接受银行事实的范围）须经产品 UX 决策明确后再修改生效 Prompt；普通文案也应交付 Diff。相关行为通过定向测试后同步更新 `current-manifest.json`，再提交到独立分支。
6. **回退**：以原 Commit 为回退单元，重新运行同一场景，不修改金融权限代码来迎合预期 Prompt 结果。

## 自动化基线

`current-manifest.json` 保存静态 System/Guard/Recovery Prompt 摘要、六个已验证意图的装配版本、完整 Tool Registry Schema/描述/风险级别摘要，以及影响模型回答的 `response_policy.py`、`response_recovery.py`、`read_completion.py`、`financial_summary.py` 和 `compound_read_summary.py` 的跨平台规范化源码摘要。它不保存客户数据、令牌或 API Key。

`backend/tests/test_prompt_review_baseline.py` 会验证实际装配与基线一致。此测试**只能提示发生变动，无法证明 UX 修改合理**。有意识修改生效 Prompt 时，必须先完成人工差异审查，再重新生成并更新基线：

```powershell
uv run python scripts/review_prompts.py --base <旧版commit> --output ../docs/prompt-reviews/<本次变更>.md --manifest-output ../docs/prompt-reviews/current-manifest.json
```

不要仅修改基线哈希来让测试转绿。此类改动的 PR/Commit 应指向对应的 Before/After 审查记录与行为证据。

## 参考实践与边界

- [Anthropic 官方 Prompting Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables)：角色、清晰指令、上下文结构与行为评估。
- [OpenAI Codex 开源 Prompt](https://github.com/openai/codex/blob/main/codex-rs/core/gpt_5_1_prompt.md)：任务角色、工具与协作规范。
- [Codex AGENTS.md 装配实现](https://github.com/openai/codex/blob/main/codex-rs/core/src/agents_md.rs)：指令作用域及来源管理。
- [OpenAI Cookbook — Iterating Development Workflows](https://github.com/openai/openai-cookbook/blob/main/examples/codex/iterating-development-workflows-with-codex.md)：阶段性可审查交付与执行记录。

第三方提取的 Claude Code 系统提示词可作为观察材料；来源真实性、版本对应和完整性无法保证时，不作为小We金融授权规则的证据，也不直接复制。系统提示词只能指导模型，最终权限仍由服务端 ToolExecutor、Guard 和业务表验证。
