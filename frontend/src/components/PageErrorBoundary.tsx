import { Component, type ReactNode } from 'react'

export class PageErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (this.state.failed) return <div role="alert" className="grid min-h-dvh place-items-center bg-canvas px-6 text-center"><div><p className="text-sm text-ink">对话页面暂时无法加载。</p><button type="button" onClick={() => window.location.reload()} className="mt-4 rounded-xl bg-jade-700 px-4 py-2 text-sm text-white">刷新页面</button></div></div>
    return this.props.children
  }
}
