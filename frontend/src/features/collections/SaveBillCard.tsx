import { useState } from 'react'
import { Bookmark, Check } from 'lucide-react'
import { IntelligentCard } from '@/features/intelligent-ui/Renderer'
import { billResultCard } from '@/features/intelligent-ui/bill-result-card'
import { billSchema } from '@/features/intelligent-ui/bill-data-schema'
import type { CardOrigin } from '@/features/intelligent-ui/schema'
import { api } from '@/lib/api'
import { saveSnapshot, type RefreshSpec } from './store'

/** An Agent result is saved only from a validated Tool payload + genuine message.
 * The local card may later refresh by an authenticated bank read, never model text. */
export function SaveBillCard({ value, hidden, userId, token, origin }: {
  value: unknown
  hidden: boolean
  userId: number
  token: string
  origin: CardOrigin
}) {
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [error, setError] = useState<string | null>(null)
  const card = billResultCard(value)
  if (!card) return null

  async function save() {
    if (status !== 'idle') return
    const bill = billSchema.safeParse(value)
    if (!bill.success) return
    setStatus('saving'); setError(null)
    try {
      // Resolve a refreshable account by a UNIQUE match. Do not guess which
      // account a masked number identifies; the server checks ownership again.
      let refresh: RefreshSpec | undefined
      try {
        const dashboard = await api.bankDashboard(token)
        const matches = dashboard.accounts.filter(account =>
          account.name === bill.data.account_name &&
          account.masked_number === bill.data.masked_number &&
          account.status === 'active' && account.currency === 'CNY')
        if (matches.length === 1)
          refresh = { kind: 'monthly_bill', month: bill.data.month, accountId: matches[0].account_id }
      } catch {
        // Saving a trusted historical result still works while banking is offline.
      }
      await saveSnapshot(userId, card, undefined, origin, refresh)
      setStatus('saved')
    } catch {
      setStatus('idle'); setError('收藏失败，请检查本地存储。')
    }
  }

  return <div className="space-y-2">
    <IntelligentCard value={card} hidden={hidden}/>
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" disabled={status !== 'idle'} onClick={() => void save()}
        className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-4 text-sm font-medium text-jade-800 transition-colors hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700 disabled:opacity-65">
        {status === 'saved' ? <Check size={16}/> : <Bookmark size={16}/>}
        {status === 'saved' ? '已收藏' : status === 'saving' ? '保存中…' : '收藏卡片'}
      </button>
      {status === 'idle' && <span className="text-xs text-muted">本地保存含金额，未加密，退出后仍保留</span>}
      {error && <span role="alert" className="text-xs text-red-700">{error}</span>}
    </div>
  </div>
}
