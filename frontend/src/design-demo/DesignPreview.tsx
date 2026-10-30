import { useState } from 'react'
import { IntelligentCard } from '@/features/intelligent-ui/Renderer'
import type { CardDescription } from '@/features/intelligent-ui/schema'
import { IntentPlayground } from '@/features/assets/IntentPlayground'
import { ActivityList } from '@/features/workspace/ActivityList'
import type { AuditEntry } from '@/lib/api'
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog'

const sample: CardDescription = {
  version: 1, id: 'sample', title: '示例账单', source: '设计样例', observedAt: '2026-01-01T00:00:00Z',
  blocks: [
    { type: 'metric', label: '总支出', value: 126000, unit: 'CNY_FEN' },
    { type: 'bar_chart', title: '消费分类', rows: [{ label: '餐饮', value: 36000 }, { label: '出行', value: 12000 }] },
    { type: 'list', rows: [{ label: '消费笔数', value: '8 笔' }, { label: '账单周期', value: '2026 年 1 月' }] },
    { type: 'text', text: '本卡片使用合成数据，仅供界面检查。' },
    { type: 'action', action: 'open_assets' },
  ],
}

const sampleActivity: AuditEntry[] = [
  { id: 1, event_type: 'tool_called', tool: 'prepare_transfer', result: 'success', created_at: '2026-01-01T02:30:00Z', action_id: 12, conversation_id: 3, transfer_id: 7 },
  { id: 2, event_type: 'verification_locked', result: 'locked', created_at: '2026-01-01T02:35:00Z', action_id: 12 },
  { id: 3, event_type: 'card_loss_completed', result: 'success', created_at: '2026-01-01T03:20:00Z', action_id: 13 },
]

export default function DesignPreview() {
  const [state, setState] = useState<'normal' | 'empty' | 'error'>('normal')
  const [selectedAction, setSelectedAction] = useState('')
  const [hidden, setHidden] = useState(false)
  return <main className="min-h-dvh bg-canvas px-5 py-8 text-ink">
    <div className="mx-auto max-w-4xl">
      <header className="flex flex-wrap items-end justify-between gap-5 border-b border-line pb-6">
        <div><p className="text-xs text-jade-700">仅开发环境 · 合成数据</p><h1 className="mt-2 text-2xl font-medium">界面状态预览</h1></div>
        <nav aria-label="选择预览状态" className="flex gap-2">{(['normal', 'empty', 'error'] as const).map((item) => <button type="button" key={item} aria-pressed={state === item} onClick={() => setState(item)} className={`rounded-full px-4 py-2 text-sm ${state === item ? 'bg-jade-700 text-white' : 'border border-line bg-white text-ink'}`}>{item === 'normal' ? '正常' : item === 'empty' ? '空状态' : '异常数据'}</button>)}</nav>
      </header>
      <div className="mt-8 grid gap-8 md:grid-cols-[1fr_350px]">
        <section><h2 className="text-sm font-medium">对话</h2><div className="mt-4 space-y-5"><p className="ml-auto max-w-[85%] rounded-2xl bg-jade-700 px-4 py-3 text-sm text-white">看看我这个月的支出</p><div className="max-w-[90%] rounded-2xl border border-line bg-white px-4 py-3 text-sm leading-7">这是设计预览中的合成对话。业务结果以服务端查询为准。</div></div></section>
        <section><div className="flex items-center justify-between gap-3"><h2 className="text-sm font-medium">结构化卡片</h2><button type="button" aria-pressed={hidden} onClick={() => setHidden((value) => !value)} className="text-sm text-jade-700 underline">{hidden ? '显示卡片内容' : '隐藏卡片内容'}</button></div><div className="mt-4">{state === 'normal' ? <IntelligentCard value={sample} hidden={hidden} onAction={() => setSelectedAction('样例：打开资产工作面')} /> : state === 'error' ? <IntelligentCard value={{ version: 99 }} /> : <p className="rounded-2xl border border-line bg-white p-5 text-sm text-muted">暂无卡片</p>}{selectedAction && <p role="status" className="mt-3 text-sm text-muted">{selectedAction}</p>}</div></section>
      </div>
      <IntentPlayground />
      <section className="mt-8 border-t border-line pt-6" aria-label="操作记录样例"><h2 className="font-medium">操作记录</h2><p className="mt-2 text-sm text-muted">合成数据</p><div className="mt-2 max-w-[350px]"><ActivityList entries={sampleActivity} /></div></section>
      <section className="mt-8 border-t border-line pt-6"><Dialog><DialogTrigger className="rounded-xl border border-line bg-white px-4 py-3 text-sm">查看长内容弹窗样例</DialogTrigger><DialogContent className="p-6"><DialogTitle>长内容弹窗样例</DialogTitle><DialogDescription className="mt-2">合成数据，不连接业务操作。</DialogDescription><div className="mt-5 space-y-4">{Array.from({ length: 12 }, (_, index) => <p key={index} className="rounded-xl border border-line p-3 text-sm">核对信息 {index + 1} · 仅供布局检查</p>)}</div><p className="mt-5 text-sm">内容结束</p></DialogContent></Dialog></section>
    </div>
  </main>
}
