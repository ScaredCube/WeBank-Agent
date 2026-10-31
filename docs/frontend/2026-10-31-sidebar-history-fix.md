# 侧栏 IP 与历史会话定位修复 · 2026-10-31

## 问题与修复
- 收起侧栏仍然使用旧 BrandMark：改为 PenguinArt avatar，直接复用主题组件，日间黑企鹅红围巾 / 夜间浅灰企鹅蓝围巾。
- 点击最近对话后出现滚动跳变：旧滚动逻辑在历史加载完成后强制滚到末尾。现在打开历史会话从首条消息开始，发送消息仍可跟随新回复。
- 重复点击当前会话：不再重新请求已有历史，保留阅读位置。
- 选择历史时资源面板仍占据区域：从最近对话进入时先关闭资源面板，恢复对话阅读区，避免面板与对话互相挤压。
- 手机端仍通过导航栏选择历史；点击资源后需正常收起资源面板才能打开其下层导航。

## 风险边界
不修改后端 API、交易、会话数据内容与收藏来源跳转协议。只调整 UI 导航、滚动体验和头像。

## 验证
- Chrome Playwright：1440 与 390 宽度切换历史，scrollTop=0，关闭面板后会话布局正确，无 JS 错误和横向溢出。
- 1440 深色模式折叠导航：实际资源 `/ip/penguin-silver-avatar-192.webp`；浅色模式为 `penguin-charcoal-avatar-192.webp`。
- `Chat.test.tsx`、`ProductPreview.test.tsx`、`useConversationScroll.test.tsx`：43/43。
- TypeScript/Vite 构建通过；Lint 0 error，只有既有 WorkspacePanel 警告。
- 未执行全量 E2E 与真实银行服务测试，符合按变更风险验证原则。
