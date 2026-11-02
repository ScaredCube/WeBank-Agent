# 小We · 模拟金融动作确认、验证与断线恢复审查

- **基线**：`a11ff19`（隔离分支 `klutz-runtime`）
- **日期**：2026-11-02
- **代码范围**：`frontend/src/features/actions/PendingActionDialog.tsx` 与测试；新增 `frontend/e2e/action-flow.browser.cjs`。
- **System / Guard / Recovery Prompt**：本轮未修改任何主提示词或工具调用 System Prompt。
- **金融权限与服务端业务实现**：未修改风险等级、ToolExecutor、验证接口、账户权限、转账执行与幂等服务。

## Before / After

| 场景 | 修改前 | 修改后 |
|---|---|---|
| 红色动作说明 | 文案“验证通过后仍需单独执行”，实际代码验证码验证通过后自动执行 | 文案“验证通过后会继续执行，请核对结果”；执行逻辑不变，避免误导 |
| 黄色转账确认后执行请求网络断开 | 点击“查询服务端状态”，若得到 `confirmed`，弹窗仍处于“结果不确定”，用户不能按原动作编号继续 | 查询到 `confirmed` 且原动作未到期，显示“按原动作编号重试”，**仅用户手动点击**才再次调用同一执行接口 |
| 黄色内部转账、收款发生同类中断 | 相同的 `confirmed` 状态可能缺少继续执行入口 | 允许与同类已确认操作一致地查询后人工继续；是否执行仍由服务端严格验证 |
| 红色转账或持仓转换已验证但执行结果未知 | 查询到 `verified` 时原有恢复入口有限 | 对现有允许执行的部分红色动作提供原编号人工继续入口；仍要求服务端验证通过且动作有效 |
| 服务端已实际完成，成功响应却丢失 | 原有状态查询可识别 `completed` | 保留这条路径，Chrome 测试确认直接进入完成态、**不显示重试按钮且不再 POST** |
| 服务端仍为待确认、已过期、已取消 | 原有保守处理 | 保持原路径，不自行确认或执行 |

### 代码行为变更原文（精选）

**Before**

```ts
} else if ((wealthOrder && result.status === 'verified') ||
           (subscriptionCancel && result.status === 'confirmed')) {
```

**After**

```ts
} else if ((result.status === 'verified' && action.risk_level === 'red' &&
            (wealthOrder || wealthConversion || transfer)) ||
           (result.status === 'confirmed' && action.risk_level === 'yellow' &&
            (subscriptionCancel || transfer || internalTransfer || collection))) {
```

这只是**状态查询之后的 UI 控制分支**：如果用户选择按原编号继续，仍需原有服务端接口完成风控、所有权、状态、有效期与幂等检查；不会创建新资金请求，不会自动提交下一笔。

## 为什么这样修改

用户实际操作中，网络连接断开可能发生在服务端执行业务前，也可能发生在提交后、客户端收到响应前。仅凭浏览器收到的网络错误无法判断操作是否完成。

因此保留三种明确区分：`completed` 显示完成、不允许继续；`confirmed/verified` 且动作仍有效时允许**原编号手动继续**；`pending/expired/cancelled` 或查询失败时保持保守回退。当前没有自动重试机制。

## 验证结果

1. **真实 Chrome + 完整前端 + 模拟 HTTP**：Playwright 3 项通过。黄色确认前没有执行请求；黄色转账首次模拟网络断线后查询 `confirmed`，确认只有用户再次主动点击才对同一执行 URL 发出第二次请求；红色理财验证码通过前没有执行请求，通过后仅一次；模拟服务端已提交但成功响应丢失时，状态查询 `completed` 后没有第二次执行。
2. **React 定向测试**：`PendingActionDialog.test.tsx` 与 `ActionJourney.test.tsx` 共 28 项通过，新增黄色原编号恢复与红色行为说明检查。
3. **后端实际服务端测试**：`test_transfers.py`、`test_actions.py`、`test_verification.py`、`test_wealth.py`、`test_combo_actions.py` 共 44 项通过。服务端已存在同一业务编号的幂等、状态与所有权防护，本轮未修改这些实现。
4. **构建检查**：Vite/TypeScript 生产构建成功；oxlint 0 错误、7 条既有警告，未扩大整改范围。

### 验收口径与未覆盖范围

浏览器操作测试使用**受控网络替身**来稳定覆盖成功/失败/断线时序，并没有从真实模型端触发、执行模拟资金操作。它证明浏览器的请求路径与 UI 状态；同编号操作的资金幂等性由独立后端测试支持。尚未完成黄色/红色动作从真实 Agent Tool 准备到浏览器确认再到真实合成数据库的单条全链路验收，也未验收跨设备恢复。

## 回退

恢复基线 `PendingActionDialog.tsx` 对应 UI 状态分支和描述；保留 E2E 作为回归用例时应调整预期。无需数据库迁移、Key 更新或主 Prompt 修改。
