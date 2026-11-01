# 视觉对齐 · 圆形主题揭幕 · 跟手反馈

时间：2026-10-31
分支：`feature/ip-object-workspace`；本次只在独立 worktree 修改，未直接修改团队主工作树与后端。

## 实现清单
1. **视觉对齐**：`WorkspacePanelFrame` 的头部内边距与内容统一为 20/28px；`AssetSectionNavigation` 的负外边距与面板断点一致；`WorkspaceHeader` 的响应式间距对齐。同屏三栏稳定布局为 nav 308px / asset 500px / agent 620px（1440px 视口，未手动调节时）。两条分隔线保留可调整能力。
2. **主题切换**：`ThemeToggle` 获取按钮右下角坐标，传给 `ThemeProvider` 的 `toggle(origin)`。用 `document.startViewTransition` + `ReactDOM.flushSync` 让暗/亮主题和企鹅素材同时进入新快照，`document.documentElement.animate` 对 `::view-transition-new(root)` 做从 0px 到覆盖最远视口角的 clip-path 圆形动画；720ms，ease-out。没有圆形能力或偏好减少动态效果时同步切换；快速连点期间保护过渡序列。
3. **跟手**：`MascotStage` 的企鹅按鼠标位置偏移（最大 ±8px、±6px、±3.6deg），使用 MotionValue + Spring，离开归位；没有事件驱动 React render；触控和减少动态效果不跟随。主题按钮、对象引用入口、发送按钮与引用胶囊采用轻量弹簧，输入框拖放时有接纳反馈。
4. **无业务逻辑变化**：后端 Tool、风控确认、会话协议和银行转账逻辑没有修改。

## 浏览器真实验证
Chrome 本地预览 `http://127.0.0.1:5189/product-preview?state=empty`。
- 1440×900px：圆心实际为 (1400,41.5)；新主题根快照有 clipPath 从 `circle(0px at 1400px 41.5px)` 到 `circle(1642.26px at 1400px 41.5px)` 的正在播放动画。中途截图看到明显弧形边界，反向切换后恢复 light。
- 390×844px：圆心 (358,41.5)，覆盖半径 878.732px，切换后无横向溢出或 JS 错误。
- `prefers-reduced-motion: reduce`：切换主题无圆形伪元素动画。
- 鼠标进入首页企鹅：CSS transform 非 identity（位移+旋转），鼠标离开为 `none`；减少动态效果情况下始终为 `none`。
- 1440px 三栏稳定后 panel 宽 500px、chat 宽 620px，composer 宽 540px，未横向溢出；面板头部、正文 paddingLeft 均为 28px；分隔键盘右键由 500 到 516px。

## 自动化验证与限制
- TypeScript / Vite build 已通过。构建警告：主包有 >500kB chunk（打包优化可在阶段性性能工作中处理）。
- 定向测试：7 个文件，共 **59/59** 通过（主题、对象引用、消息显示、预览、正式聊天、面板）。
- Lint 本轮相关代码无新错误；保留 `WorkspacePanel.tsx` 已有的 `react(set-state-in-effect)` 警告。
- 本次为视觉动效任务，未执行无关的后端或银行业务全量回归。截图与复现脚本放在工作区 QA 文件夹，非产品源码。
