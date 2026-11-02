import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, X } from 'lucide-react'

import { api, type AuditEntry } from '@/lib/api'
import { ActivityList } from './ActivityList'

export function ActivityPane({ token, onClose, embedded = false }: { token: string; onClose?: () => void; embedded?: boolean }) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const generation = useRef(0)

  const load = useCallback(async (afterId?: number) => {
    const id = ++generation.current
    setLoading(true); setError(null)
    try {
      const data = await api.audit(token, afterId ?? 0)
      if (generation.current !== id) return
      setEntries((current) => afterId === undefined ? data : [...current, ...data.filter(item => !current.some(old => old.id === item.id))])
      setHasMore(data.length === 50)
    } catch (err) {
      if (generation.current === id) setError(err instanceof Error ? err.message : '操作记录加载失败')
    } finally {
      if (generation.current === id) setLoading(false)
    }
  }, [token])

  useEffect(() => { void load() }, [load])

  return <section aria-label="操作记录" className={embedded ? 'flex min-h-0 flex-col' : 'flex h-full min-h-0 flex-col bg-workspace'}>
    {embedded
      ? <div className="flex shrink-0 items-center gap-2 pb-2">
          <p className="flex-1 text-xs text-muted">最近的操作与审计记录</p>
          <button type="button" onClick={() => void load()} aria-label="刷新操作记录" className="grid size-9 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink"><RefreshCw size={16} /></button>
        </div>
      : <header className="flex h-16 shrink-0 items-center gap-2 border-b border-line px-4">
          <button type="button" onClick={onClose} aria-label="返回对话" className="grid size-10 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink"><X size={18} /></button>
          <h2 className="flex-1 text-[17px] font-semibold tracking-tight text-ink">操作记录</h2>
          <button type="button" onClick={() => void load()} aria-label="刷新操作记录" className="grid size-10 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink"><RefreshCw size={17} /></button>
        </header>}
    <div className={embedded ? 'min-h-0 flex-1' : 'min-h-0 flex-1 overflow-y-auto px-4 py-4'}>
      {error && <p role="alert" className="mb-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      {!loading && !error && entries.length === 0 && <p className="py-8 text-sm text-muted">暂无操作记录</p>}
      <ActivityList entries={entries} />
      {hasMore && <button type="button" disabled={loading} onClick={() => void load(entries[entries.length - 1]?.id)} className="mt-4 w-full rounded-xl border border-line bg-panel px-4 py-3 text-sm disabled:opacity-50">{loading ? '加载中…' : '加载更多'}</button>}
    </div>
  </section>
}
