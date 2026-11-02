# 小We · Generative UI 集成验收（2026-11-02）

## 范围与分支

- 目标：`klutz-runtime`，合并前 `a8f00fb`；候选：`feature/klutz-gui-integration@1244bdb`（原始暂停工作区 `bb1bb95` 上 73 个文件的 checkpoint）。
- 原开发者的 `work/`、本机调试数据和环境密钥没有进入 Git；整合采取共同祖先三方合并，唯一冲突文件为 `frontend/src/pages/Chat.tsx`。
- 该文件同时保留 `lastSubmittedDraft`、`editablePendingDraft` 与“取消旧订单后恢复草稿、保留金融对象引用”，以及 Generative UI 的视图上下文、SSE 和会话工作区状态。切换会话时清除上一会话编辑草稿，防止跨会话混用。
- 不修改现有三套 System/Guard/Recovery Prompt、既有银行 Tool 授权和风控阈值。新增独立只读 UIComposer Prompt 见 `fixtures/generative-ui/catalog-prompt.txt`；其严格限制组件类型和可信数据引用，业务值来自服务端。行为差异见 `docs/prompt-reviews/a8f00fb-generative-ui-runtime-integration-review.md`。

## 本次定位的真实故障

此前用户交接的最后一次浏览器复验失败只有 `PLAYWRIGHT_OR_RUNTIME_ERROR`，原因无法确认。我们首先增加阶段化、无金融原文的浏览器诊断并进行真实模型重试。在两条分支合并后，真实 Chrome 明确返回：

```
CATEGORY_BUTTON_WAIT → AMBIGUOUS_LOCATOR
```

模型可能重复生成同一账单分类数据集的 CategoryBarChart / Selector，导致页面存在多个同名可点击按钮。后端 ViewSpec 原本只验证结构和可信引用，不限制重复呈现。

**解决策略**：分类选择由 ViewPanel 渲染**一个权威选择器**（基于服务端 trusted_data + allowed_actions），模型图表仍正常展示，但分类图表与模型选择器在分析工作区内不再同时生成交互按钮；没有图表时也保留选择能力。这样不依赖模型遵从“不要重复”提示词，也不改变金融权限。隐私隐藏时分类名称被匿名化；已选分类的金额和笔数来自可信视图行，按相同隐私规则隐藏。新增单测覆盖指标-only 布局、重复图表和隐私模式。

浏览器脚本增设 `CATEGORY_BUTTON_WAIT / CATEGORY_CLICK / CATEGORY_INTERACTION_RESPONSE` 阶段码，异常仅输出阶段和错误类型，不泄露银行明细、工具参数或模型原文。

## 实测证据

| 范围 | 合并后实际运行结果 |
|---|---|
| 前端完整 Vitest | **240/240 PASS**（唯一选择器修正前，修正后相关 48/48 PASS） |
| TypeScript / Vite 生产构建 | **PASS**（仍有大于 500 KB chunk 的提示） |
| 后端完整 pytest | **576 passed + 31 subtests；1 个 Prompt manifest 哈希过期** |
| Prompt manifest 更新后定向回归 | **20/20 PASS**，三套静态 Prompt 哈希未变 |
| 真实 DeepSeek + Chrome + 合成银行数据库 | **PASS**：账单 → 类别选择 → 可信分类金额/笔数续问 → 不可变历史版本刷新恢复；JS 错误 0、余额不变、无资金操作 |
| 金融授权合成 Chrome E2E | **PASS**：旧动作取消、2 元新动作、错误验证码被拒、正确验证码与模拟人脸完成后才执行；唯一新流水 |

以上最后两项都在**合并后的 `klutz-runtime`** 运行；前者使用真实 `deepseek-v4.1-flash-1017`，后者的模型 Tool 调用和 Guard 返回由固定测试替身给出。不得将单次真实模型通过理解为跨模型/多样本可靠性。生产真实资金未接入。

## 保留边界与未完成

- 本次没有修改既有 SQLite 文件，也没有执行数据库迁移；现有非空库需先只读运行 `backend/scripts/check_generative_ui_schema.py`，再按备份和审批流程迁移新增视图表。
- 订阅结果展示仍为候选组件，后端没有打通订阅的完整 `ui_view` 事件；不能声称所有 Tool 均已支持 Generative UI。
- 页面上的动态视图行为是受限 Schema + 服务端可信结果；它不能替代转账确认、交易授权和审计。
- 后续建议优先覆盖真实模型多次稳定性、UI 交互与金融操作上下文并行时的隔离、移动端工作区体验，再扩大其他 Tool 覆盖面。
