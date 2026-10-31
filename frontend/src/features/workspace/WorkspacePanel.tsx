import { useEffect, useRef, useState } from 'react'

import { api, type AuditEntry, type BankCard, type BankDashboardData } from '@/lib/api'
import { CollectionPanel } from '@/features/collections/CollectionPanel'
import type { CardLossRecovery } from '@/features/actions/CardLossButton'
import { AssetWorkspace } from '@/features/assets/AssetWorkspace'
import type { BankObjectReference } from '@/features/references/bank-object-reference'
import { ActivityList } from './ActivityList'
import { WorkspacePanelFrame } from './WorkspacePanelFrame'
import type { CardOrigin } from '@/features/intelligent-ui/schema'
import type { StreamEvent } from '@/lib/sse'

type Panel = 'assets' | 'activity' | 'collections'

export function WorkspacePanel({ token, userId, panel, onClose, hidden, onTogglePrivacy, focusOnMount = true, refreshSignal = 0, actionDisabled = false, onActionBusy = () => {}, onActionPrepared = () => {}, cardLossRecovery = new Map<number, CardLossRecovery>(), onCardLossRecoveryChange = () => {}, onCardLossResolved = () => {}, onOpenSource, sourceDisabled = false, onReference }: { token: string; userId: number; panel: Panel; onClose: () => void; hidden: boolean; onTogglePrivacy: () => void; focusOnMount?: boolean; refreshSignal?: number; actionDisabled?: boolean; onActionBusy?: (busy: boolean) => void; onActionPrepared?: (event: Extract<StreamEvent, { type: 'action_required' }>) => void; cardLossRecovery?: ReadonlyMap<number, CardLossRecovery>; onCardLossRecoveryChange?: (cardId: number, recovery: CardLossRecovery | null) => void; onCardLossResolved?: (cardId: number) => void; onOpenSource?: (origin: CardOrigin) => void; sourceDisabled?: boolean; onReference?: (reference: BankObjectReference) => void }) {
  const [cards, setCards] = useState<BankCard[]>([])
  const [dashboard, setDashboard] = useState<BankDashboardData | null>(null)
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dashboardError, setDashboardError] = useState<string | null>(null)
  const [cardError, setCardError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [revision, setRevision] = useState(0)
  const [loadedSignal, setLoadedSignal] = useState(refreshSignal)
  const requestGeneration = useRef(0)
  const isLoading = loading || loadedSignal !== refreshSignal

  useEffect(() => {
    let active = true
    const tracker = requestGeneration
    const generation = ++tracker.current
    const cleanup = () => { active = false; if (tracker.current === generation) tracker.current++ }
    setLoading(panel !== 'collections')
    setError(null)
    setDashboardError(null)
    setCardError(null)
    if (panel === 'collections') return cleanup

    async function loadPanel() {
      if (panel === 'assets') {
        const [dashboardResult, cardsResult] = await Promise.allSettled([
          api.bankDashboard(token),
          api.cards(token),
        ])
        if (!active) return

        if (dashboardResult.status === 'fulfilled') setDashboard(dashboardResult.value)
        else setDashboardError(dashboardResult.reason instanceof Error ? dashboardResult.reason.message : '账户与资产暂时无法读取。')

        if (cardsResult.status === 'fulfilled') setCards(cardsResult.value)
        else setCardError(cardsResult.reason instanceof Error ? cardsResult.reason.message : '银行卡暂时无法读取。')
      } else {
        try {
          const data = await api.audit(token)
          if (active) { setEntries(data); setHasMore(data.length === 50) }
        } catch (err) {
          if (active) setError(err instanceof Error ? err.message : '操作记录加载失败')
        }
      }

      if (active) { setLoadedSignal(refreshSignal); setLoading(false) }
    }

    void loadPanel()
    return cleanup
  }, [token, panel, revision, refreshSignal])

  async function loadMore() {
    if (isLoading || entries.length === 0) return
    const generation = requestGeneration.current
    setLoading(true)
    setError(null)
    try {
      const next = await api.audit(token, entries[entries.length - 1].id)
      if (requestGeneration.current !== generation) return
      setEntries((previous) => [...previous, ...next.filter((item) => !previous.some((old) => old.id === item.id))])
      setHasMore(next.length === 50)
    } catch (err) {
      if (requestGeneration.current === generation) setError(err instanceof Error ? err.message : '加载失败')
    } finally { if (requestGeneration.current === generation) setLoading(false) }
  }

  function refreshPanel() {
    requestGeneration.current++
    setLoading(true)
    setError(null)
    setDashboardError(null)
    setCardError(null)
    setDashboard(null)
    setCards([])
    setEntries([])
    setHasMore(false)
    setRevision((value) => value + 1)
  }

  return (
    <WorkspacePanelFrame panel={panel} onClose={onClose} hidden={hidden} onTogglePrivacy={onTogglePrivacy} focusOnMount={focusOnMount} onRefresh={panel === 'collections' ? undefined : refreshPanel}>
        {error && <div role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        {panel !== 'collections' && isLoading && <p className="text-sm text-muted" role="status">加载中…</p>}
        {hidden && <p className="mb-4 text-xs text-muted">金额已隐藏；姓名、卡片尾号与对话文字仍会显示。</p>}
        {panel === 'collections' && <CollectionPanel userId={userId} hidden={hidden} onOpenSource={onOpenSource} sourceDisabled={sourceDisabled} />}
        {panel === 'assets' && <AssetWorkspace
          token={token}
          userId={userId}
          dashboard={dashboard}
          cards={cards}
          loading={isLoading}
          dashboardError={dashboardError}
          cardError={cardError}
          hidden={hidden}
          actionDisabled={actionDisabled}
          cardLossRecovery={cardLossRecovery}
          onRetry={refreshPanel}
          onCardLossRecoveryChange={onCardLossRecoveryChange}
          onCardLossResolved={onCardLossResolved}
          onActionBusy={onActionBusy}
          onActionPrepared={onActionPrepared}
          onReference={onReference}
        />}
        {panel === 'activity' && <>
          {(entries.length > 0 || (!isLoading && !error)) && <ActivityList entries={entries} />}
          {entries.length > 0 && <p className="mt-4 text-xs text-muted">显示已加载记录，按发生顺序排列</p>}
          {hasMore && <button type="button" disabled={isLoading} onClick={() => void loadMore()} className="mt-4 w-full rounded-xl border border-line bg-white px-4 py-3 text-sm disabled:opacity-50">{isLoading ? '加载中…' : '加载更多'}</button>}
        </>}
    </WorkspacePanelFrame>
  )
}
