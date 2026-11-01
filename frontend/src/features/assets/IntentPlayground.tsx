import type { PanInfo } from 'motion/react'
import { useRef, useState } from 'react'
import { makeIntent, type IntentEntity, type TransferIntent } from './intent'
import { DraggableAccount } from './DraggableAccount'

const source: IntentEntity = { type: 'account', id: 'sample-account', label: '示例工资卡 · 8899' }
const target: IntentEntity = { type: 'contact', id: 'sample-contact', label: '示例联系人 · 小林' }

export function IntentPlayground() {
  const targetRef = useRef<HTMLButtonElement>(null)
  const [selected, setSelected] = useState(false)
  const [intent, setIntent] = useState<TransferIntent | null>(null)
  const [notice, setNotice] = useState('')
  const [overTarget, setOverTarget] = useState(false)

  function chooseTarget() {
    if (!selected) { setNotice('请先选择付款账户。'); return }
    setIntent(makeIntent(source, target)); setSelected(false); setNotice('')
  }
  function isOverTarget(info: PanInfo) {
    const rect = targetRef.current?.getBoundingClientRect()
    return !!rect && info.point.x >= rect.left + window.scrollX && info.point.x <= rect.right + window.scrollX && info.point.y >= rect.top + window.scrollY && info.point.y <= rect.bottom + window.scrollY
  }
  function drop(info: PanInfo) {
    setOverTarget(false)
    if (isOverTarget(info)) {
      setIntent(makeIntent(source, target)); setSelected(false); setNotice('')
    } else setNotice('未放到可用目标，已返回原位。')
  }

  return <section className="mt-8 border-t border-line pt-6" aria-label="意图组合样例">
    <h2 className="font-medium">意图组合</h2><p className="mt-2 text-sm text-muted">合成数据 · 长按拖动，或依次选择账户和联系人</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <DraggableAccount label={source.label} onChoose={() => { setSelected(true); setNotice('已选择付款账户，请选择联系人。') }} onDrop={drop} onMove={(info) => setOverTarget(isOverTarget(info))} onCancel={() => setOverTarget(false)} />
      <button ref={targetRef} type="button" onClick={chooseTarget} className={`rounded-2xl border p-4 text-left focus-visible:outline-2 focus-visible:outline-jade-700 ${overTarget ? 'border-jade-600 bg-jade-50 ring-2 ring-jade-200' : 'border-line bg-white'}`}><span className="block text-xs text-muted">收款联系人</span><span className="mt-2 block text-sm font-medium">{target.label}</span></button>
    </div>
    {notice && <p role="status" className="mt-3 text-sm text-muted">{notice}</p>}
    {intent && <div className="mt-4 flex flex-wrap items-center gap-2 rounded-2xl bg-jade-50 p-3 text-sm text-jade-900"><span>转账</span><span>{intent.source.label}</span><span aria-hidden="true">→</span><span>{intent.target.label}</span><button type="button" onClick={() => setIntent(null)} className="ml-auto underline">移除</button></div>}
    <p className="mt-3 text-xs text-muted">仅展示本地交互，不会提交业务请求。</p>
  </section>
}
