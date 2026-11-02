import { useMemo, useRef, useState } from 'react'
import { AlertCircle, ChevronLeft, Eye, EyeOff, Grip, PanelLeftClose, RefreshCw, X } from 'lucide-react'

import type { BankCard, BankDashboardData } from '@/lib/api'
import type { StreamEvent } from '@/lib/sse'
import { CardLossButton, type CardLossRecovery } from '@/features/actions/CardLossButton'
import { usePrivacy } from '@/features/privacy/PrivacyProvider'
import { Money } from '@/features/privacy/Money'
import { AssetBankCard, AssetContactCard, AssetHoldingCard } from './AssetCards'
import { DragGhost } from './drag/DragGhost'
import { useAssetDrag } from './drag/useAssetDrag'
import { resolveIntent, type AssetIntent, type AssetKind, type IntentEntity } from './intent'
import { cn } from '@/lib/utils'
import type { BankObjectReference } from '@/features/references/bank-object-reference'

type Detail = { kind: 'account'; id: number } | { kind: 'contact'; id: number } | { kind: 'holding'; id: number } | null

type Props = {
  token: string
  dashboard: BankDashboardData | null
  cards: BankCard[]
  loading: boolean
  dashboardError: string | null
  cardError: string | null
  actionDisabled: boolean
  cardLossRecovery: ReadonlyMap<number, CardLossRecovery>
  onCardLossRecoveryChange: (cardId: number, value: CardLossRecovery | null) => void
  onCardLossResolved: (cardId: number) => void
  onActionBusy: (busy: boolean) => void
  onActionPrepared: (event: Extract<StreamEvent, { type: 'action_required' }>) => void
  onIntent: (intent: AssetIntent) => void
  onReference: (reference: BankObjectReference) => void
  onRetry: () => void
  onClose: () => void
}

function SectionLabel({ children }: { children: string }) {
  return <div className="mb-3 mt-7 flex items-center gap-3 first:mt-1">
    <span className="text-[10px] tracking-[0.24em] text-muted">{children}</span>
    <i className="h-px flex-1 bg-line" aria-hidden="true" />
  </div>
}

export function AssetsPane({
  token, dashboard, cards, loading, dashboardError, cardError, actionDisabled,
  cardLossRecovery, onCardLossRecoveryChange, onCardLossResolved, onActionBusy,
  onActionPrepared, onIntent, onReference, onRetry, onClose,
}: Props) {
  const privacy = usePrivacy()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<IntentEntity | null>(null)
  const [notice, setNotice] = useState('')
  const [detail, setDetail] = useState<Detail>(null)

  const entities = useMemo(() => {
    const map = new Map<string, IntentEntity>()
    for (const account of dashboard?.accounts ?? []) {
      map.set(`account:${account.account_id}`, {
        kind: 'account', id: account.account_id, label: account.name,
        detail: account.masked_number,
        disabled: !account.can_transfer || account.status !== 'active' || account.card_status !== 'active',
      })
    }
    for (const contact of dashboard?.contacts ?? []) {
      map.set(`contact:${contact.contact_id}`, {
        kind: 'contact', id: contact.contact_id, label: contact.name,
        detail: `${contact.bank_name} · ${contact.masked_phone}`,
        disabled: !contact.can_transfer || contact.status !== 'active',
      })
    }
    for (const holding of dashboard?.holdings ?? []) {
      map.set(`holding:${holding.holding_id}`, {
        kind: 'holding', id: holding.holding_id, label: holding.product_name,
        detail: `${holding.category} · 风险 ${holding.risk_level}`,
        disabled: holding.status !== 'active' || holding.amount_fen <= 0,
      })
    }
    return map
  }, [dashboard])

  const drag = useAssetDrag({
    scrollRef,
    findTarget: (kind: AssetKind, id: number) => entities.get(`${kind}:${id}`) ?? null,
    onReferenceDrop: (source) => {
      onReference({kind: source.kind, id: source.id, label: source.label, detail: source.detail || ''})
      setNotice('已引用到对话')
    },
    onDrop: (source, target) => {
      if (!target) { setNotice('未放到可用目标，已返回原位。'); return }
      const intent = resolveIntent(source, target)
      if (!intent) { setNotice('暂不支持这个组合'); return }
      setNotice('')
      setSelected(null)
      onIntent(intent)
    },
    onCancel: () => setNotice(''),
  })

  function choose(entity: IntentEntity) {
    if (drag.consumeClick()) return
    if (entity.disabled) {
      setNotice('该对象当前不可用')
      return
    }
    if (selected && selected.kind === entity.kind && selected.id === entity.id) {
      setSelected(null)
      setNotice('')
      return
    }
    if (!selected) {
      setSelected(entity)
      setNotice('')
      return
    }
    const intent = resolveIntent(selected, entity)
    if (!intent) { setNotice('暂不支持这个组合'); return }
    setSelected(null)
    setNotice('')
    onIntent(intent)
  }

  const selectedKey = selected ? `${selected.kind}:${selected.id}` : null
  const accountDetail = detail?.kind === 'account' ? dashboard?.accounts.find((item) => item.account_id === detail.id) : null
  const contactDetail = detail?.kind === 'contact' ? dashboard?.contacts.find((item) => item.contact_id === detail.id) : null
  const holdingDetail = detail?.kind === 'holding' ? dashboard?.holdings.find((item) => item.holding_id === detail.id) : null
  const cardForAccount = accountDetail ? cards.find((card) => card.account_id === accountDetail.account_id) : null

  return <section aria-label="资产" className="flex h-full min-h-0 flex-col bg-workspace">
    <header className="flex h-[calc(4rem+env(safe-area-inset-top))] shrink-0 items-center gap-2 border-b border-line px-4 pt-[env(safe-area-inset-top)] sm:px-6">
      <button type="button" data-assets-close onClick={onClose} aria-label="返回对话"
        className="grid size-10 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 lg:hidden">
        <ChevronLeft size={19} />
      </button>
      <button type="button" onClick={onClose} aria-label="收起资产"
        className="hidden size-10 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 lg:grid">
        <PanelLeftClose size={18} />
      </button>
      <h2 className="min-w-0 flex-1 truncate text-[17px] font-semibold tracking-tight text-ink">资产</h2>
      <button type="button" onClick={privacy.toggle} aria-pressed={privacy.hidden}
        aria-label={privacy.hidden ? '显示金额' : '隐藏金额'}
        className="grid size-10 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
        {privacy.hidden ? <EyeOff size={17} /> : <Eye size={17} />}
      </button>
      <button type="button" onClick={onRetry} aria-label="刷新资产"
        className="grid size-10 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
        <RefreshCw size={17} />
      </button>
    </header>

    <div ref={scrollRef} className={cn('assets-scroll min-h-0 flex-1 overflow-y-auto px-4 pb-[max(2.5rem,env(safe-area-inset-bottom))] sm:px-6', drag.ghost && 'overflow-hidden')}>
      {loading && <p role="status" className="py-8 text-sm text-muted">正在读取资产…</p>}
      {dashboardError && <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-xs leading-5 text-red-800">
        <AlertCircle size={15} className="mt-0.5 shrink-0" /><span className="flex-1">账户与资产暂时无法读取：{dashboardError}</span>
        <button type="button" onClick={onRetry} className="underline">重试</button>
      </div>}
      {cardError && <p role="status" className="mt-3 text-xs text-muted">银行卡状态暂时无法读取。</p>}

      {dashboard && <>
        <SectionLabel>银行卡</SectionLabel>
        <div className="flex flex-col gap-3">
          {dashboard.accounts.map((account, index) => {
            const entity = entities.get(`account:${account.account_id}`)!
            return <AssetBankCard key={account.account_id} index={index} account={account} entity={entity}
              selected={selectedKey === `account:${account.account_id}`}
              dropActive={drag.activeTargetKey === `account:${account.account_id}` && selectedKey !== `account:${account.account_id}`}
              dragging={drag.activeSourceKey === `account:${account.account_id}`}
              settled={drag.settledKey === `account:${account.account_id}`}
              onSelect={() => choose(entity)}
              onDetails={() => setDetail({ kind: 'account', id: account.account_id })}
              onPointerDown={(event) => drag.start({ event, item: entity, element: event.currentTarget })} />
          })}
          {dashboard.accounts.length === 0 && <p className="py-5 text-sm text-muted">暂无可用银行卡</p>}
        </div>

        <SectionLabel>联系人</SectionLabel>
        <div className="grid grid-cols-3 gap-2">
          {dashboard.contacts.map((contact) => {
            const entity = entities.get(`contact:${contact.contact_id}`)!
            return <AssetContactCard key={contact.contact_id} contact={contact} entity={entity}
              selected={selectedKey === `contact:${contact.contact_id}`}
              dropActive={drag.activeTargetKey === `contact:${contact.contact_id}` && selectedKey !== `contact:${contact.contact_id}`}
              dragging={drag.activeSourceKey === `contact:${contact.contact_id}`}
              settled={drag.settledKey === `contact:${contact.contact_id}`}
              onSelect={() => choose(entity)}
              onPointerDown={(event) => drag.start({ event, item: entity, element: event.currentTarget })} />
          })}
        </div>
        {dashboard.contacts.length === 0 && <p className="py-5 text-sm text-muted">暂无联系人</p>}

        <SectionLabel>持仓</SectionLabel>
        <div className="flex flex-col gap-2">
          {dashboard.holdings.map((holding) => {
            const entity = entities.get(`holding:${holding.holding_id}`)!
            return <AssetHoldingCard key={holding.holding_id} holding={holding} entity={entity}
              selected={selectedKey === `holding:${holding.holding_id}`}
              dropActive={drag.activeTargetKey === `holding:${holding.holding_id}` && selectedKey !== `holding:${holding.holding_id}`}
              dragging={drag.activeSourceKey === `holding:${holding.holding_id}`}
              settled={drag.settledKey === `holding:${holding.holding_id}`}
              onSelect={() => choose(entity)}
              onPointerDown={(event) => drag.start({ event, item: entity, element: event.currentTarget })} />
          })}
        </div>
        {dashboard.holdings.length === 0 && <p className="py-5 text-sm text-muted">暂无持仓</p>}

        <div className="mt-8 flex items-center justify-center gap-2 text-[10px] tracking-[0.04em] text-muted">
          <Grip aria-hidden="true" size={14} />
          长按卡片，拖到一起
        </div>
        {selected && <p role="status" className="mt-3 text-center text-xs text-jade-800">已选择 {selected.label}，请选择目标</p>}
        {notice && <p role="status" className="mt-3 text-center text-xs text-muted">{notice}</p>}
        <p className="mt-5 text-center text-[10px] text-muted/70">金额已隐藏时点击金额可临时查看 3 秒</p>
      </>}
    </div>

    {detail && <div className="fixed inset-0 z-[70] grid place-items-end bg-black/30 p-0 sm:place-items-center sm:p-6" onClick={() => setDetail(null)}>
      <div role="dialog" aria-modal="true" aria-label="资产详情" onClick={(event) => event.stopPropagation()}
        className="max-h-[82dvh] w-full overflow-y-auto rounded-t-[26px] border border-line bg-panel p-5 shadow-2xl sm:max-w-md sm:rounded-3xl">
        <div className="flex items-center gap-3">
          <h3 className="flex-1 text-base font-semibold text-ink">
            {accountDetail ? '账户详情' : contactDetail ? '联系人详情' : holdingDetail ? '持仓详情' : '详情'}
          </h3>
          <button type="button" onClick={() => setDetail(null)} aria-label="关闭详情" className="grid size-9 place-items-center rounded-full bg-ink/5 text-muted"><X size={16} /></button>
        </div>
        {accountDetail && <dl className="mt-5 space-y-3 text-sm">
          <div className="flex justify-between gap-4"><dt className="text-muted">账户</dt><dd className="font-medium">{accountDetail.name}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">卡号</dt><dd className="font-mono">{accountDetail.masked_number}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">余额</dt><dd><Money fen={accountDetail.balance_fen} className="font-medium" /></dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">状态</dt><dd>{accountDetail.status === 'active' ? '正常' : '不可用'}</dd></div>
        </dl>}
        {contactDetail && <dl className="mt-5 space-y-3 text-sm">
          <div className="flex justify-between gap-4"><dt className="text-muted">姓名</dt><dd className="font-medium">{contactDetail.name}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">银行</dt><dd>{contactDetail.bank_name}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">手机号</dt><dd className="font-mono">{contactDetail.masked_phone}</dd></div>
        </dl>}
        {holdingDetail && <dl className="mt-5 space-y-3 text-sm">
          <div className="flex justify-between gap-4"><dt className="text-muted">产品</dt><dd className="font-medium">{holdingDetail.product_name}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">类别</dt><dd>{holdingDetail.category}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">持有金额</dt><dd><Money fen={holdingDetail.amount_fen} className="font-medium" /></dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">昨日收益</dt><dd><Money fen={holdingDetail.yesterday_earnings_fen} /></dd></div>
        </dl>}
        {cardForAccount && <div className="mt-5 border-t border-line pt-4">
          <p className="mb-2 text-xs text-muted">银行卡操作</p>
          <CardLossButton token={token} cardId={cardForAccount.card_id}
            disabled={actionDisabled || cardForAccount.status !== 'active' || cardForAccount.account_status !== 'active'}
            recovery={cardLossRecovery.get(cardForAccount.card_id) ?? null}
            onRecoveryChange={onCardLossRecoveryChange} onResolved={onCardLossResolved}
            onBusyChange={onActionBusy} onPrepared={onActionPrepared} />
        </div>}
      </div>
    </div>}

    <DragGhost state={drag.ghost} reduced={drag.reduced} />
  </section>
}
