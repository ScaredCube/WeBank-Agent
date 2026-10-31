import { useMemo, useState } from 'react'
import { CreditCard, Landmark, ChartNoAxesCombined, AlertCircle, RefreshCw } from 'lucide-react'

import type { BankAccountOverview, BankCard, BankContactOverview, BankDashboardData, WealthHoldingOverview } from '@/lib/api'
import { formatCnyFen } from '@/lib/format'
import { CardLossButton, type CardLossRecovery } from '@/features/actions/CardLossButton'
import { MonthlyBillPanel } from '@/features/intelligent-ui/MonthlyBillPanel'
import { MascotEmptyState } from '@/features/theme/MascotEmptyState'
import type { StreamEvent } from '@/lib/sse'
import { AssetSection } from './AssetSection'
import { ReferenceSource } from '@/features/references/ReferenceSource'
import type { BankObjectReference } from '@/features/references/bank-object-reference'
import { AssetSectionNavigation, type AssetSectionKey } from './AssetSectionNavigation'

function accountStatus(status: string) {
  if (status === 'active') return '正常'
  if (status === 'frozen') return '已冻结'
  return '状态未知'
}

function cardStatus(status: string) {
  if (status === 'active') return '正常'
  if (status === 'lost') return '已挂失'
  if (status === 'missing') return '未关联银行卡'
  return '状态未知'
}

function contactStatus(contact: BankContactOverview) {
  return contact.can_transfer ? '可用' : '暂不可用'
}

function formatQueryTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function Money({ fen, hidden, currency = 'CNY', className = '' }: { fen: number; hidden: boolean; currency?: string; className?: string }) {
  const formatted = currency === 'CNY' ? formatCnyFen(fen) : '金额格式暂不可用'
  return (
    <span aria-label={hidden ? '金额已隐藏' : formatted} className={`tabular-nums ${className}`}>
      {hidden ? '••••••' : formatted}
    </span>
  )
}

function AccountCard({ account, hidden, onReference }: {
  account: BankAccountOverview
  hidden: boolean
  onReference?: (reference: BankObjectReference) => void
}) {
  return (
    <ReferenceSource reference={{kind:'account',id:account.account_id,label:account.name,detail:account.masked_number}} onReference={onReference}>
    <article className="rounded-xl border border-line bg-panel px-4 py-4">
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-full bg-jade-50 text-jade-800">
          <Landmark size={20} strokeWidth={1.8} />
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-[13px] font-semibold text-ink">{account.name}</h4>
          <p className="mt-1 truncate text-xs text-muted">{account.masked_number} · {account.currency}</p>
        </div>
        <div className="shrink-0 text-right">
          <span className="block text-[11px] text-muted">余额</span>
          <Money fen={account.balance_fen} hidden={hidden} currency={account.currency} className="mt-0.5 block text-[14px] font-semibold text-ink" />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-[11px] text-muted">
        <span>{accountStatus(account.status)}</span>
      </div>
    </article>
    </ReferenceSource>
  )
}

function CardEntry({ card, token, disabled, recovery, onRecoveryChange, onResolved, onBusyChange, onPrepared, onReference }: {
  card: BankCard
  token: string
  disabled: boolean
  recovery: ReadonlyMap<number, CardLossRecovery>
  onRecoveryChange: (cardId: number, value: CardLossRecovery | null) => void
  onResolved: (cardId: number) => void
  onBusyChange: (busy: boolean) => void
  onPrepared: (event: Extract<StreamEvent, { type: 'action_required' }>) => void
  onReference?: (reference: BankObjectReference) => void
}) {
  return (
    <ReferenceSource reference={{kind:'card', id:card.card_id,label:card.account_name,detail:card.masked_number}} onReference={onReference}>
    <article className="relative overflow-hidden rounded-[18px] border border-line bg-panel px-4 py-4">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-jade-300 via-jade-500 to-jade-800 opacity-70" />
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-xl bg-jade-50 text-jade-800"><CreditCard size={18} /></span>
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-[13px] font-semibold text-ink">{card.account_name}</h4>
          <p className="mt-1 truncate text-xs text-muted">银行卡 · {card.masked_number}</p>
        </div>
        <span className="shrink-0 text-[11px] text-muted">{cardStatus(card.status)}</span>
      </div>
      <details className="mt-3 border-t border-line pt-3">
        <summary className="cursor-pointer list-none text-xs font-medium text-jade-800 focus-visible:outline-2 focus-visible:outline-jade-700">卡片操作</summary>
        <div className="mt-2">
          <CardLossButton
            token={token}
            cardId={card.card_id}
            disabled={disabled || card.status !== 'active' || card.account_status !== 'active'}
            recovery={recovery.get(card.card_id) ?? null}
            onRecoveryChange={onRecoveryChange}
            onResolved={onResolved}
            onBusyChange={onBusyChange}
            onPrepared={onPrepared}
          />
        </div>
      </details>
    </article>
    </ReferenceSource>
  )
}

function ContactRow({ contact, onReference }: { contact: BankContactOverview; onReference?: (reference: BankObjectReference) => void }) {
  return (
    <ReferenceSource reference={{kind:'contact',id:contact.contact_id,label:contact.name,detail:contact.bank_name}} onReference={onReference}>
    <div className="flex min-h-[68px] items-center gap-3 border-b border-line py-3 last:border-b-0">
      <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-[#eef4f2] text-[14px] font-semibold text-jade-800">
        {contact.name.slice(0, 1)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold text-ink">{contact.name}</p>
        <p className="mt-1 truncate text-xs text-muted">{contact.bank_name} · {contact.masked_phone}</p>
      </div>
      <span className="shrink-0 text-[11px] text-muted">{contactStatus(contact)}</span>
    </div>
    </ReferenceSource>
  )
}

function HoldingRow({ holding, hidden, onReference }: { holding: WealthHoldingOverview; hidden: boolean; onReference?: (reference: BankObjectReference) => void }) {
  return (
    <ReferenceSource reference={{kind:'holding',id:holding.holding_id,label:holding.product_name,detail:holding.category}} onReference={onReference}>
    <div className="flex min-h-[76px] items-center gap-3 border-b border-line py-3 last:border-b-0">
      <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-[#eef4f2] text-jade-800">
        <ChartNoAxesCombined size={19} strokeWidth={1.8} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold text-ink">{holding.product_name}</p>
        <p className="mt-1 truncate text-xs text-muted">{holding.category} · 风险 {holding.risk_level}</p>
        <p className="mt-1 text-[11px] text-muted">昨日收益 <Money fen={holding.yesterday_earnings_fen} hidden={hidden} /></p>
      </div>
      <div className="shrink-0 text-right">
        <span className="block text-[11px] text-muted">持有金额</span>
        <Money fen={holding.amount_fen} hidden={hidden} className="mt-0.5 block text-[13px] font-semibold text-ink" />
      </div>
    </div>
    </ReferenceSource>
  )
}

function EmptyState({ label }: { label: string }) {
  return <MascotEmptyState title={label} pose="sleep" compact />
}

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-xs leading-5 text-red-800">
      <div className="flex items-start gap-2">
        <AlertCircle size={15} className="mt-0.5 shrink-0" />
        <span className="min-w-0 flex-1">{message}</span>
      </div>
      <button type="button" onClick={onRetry} className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 text-xs font-medium hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-red-800">
        <RefreshCw size={13} />重试
      </button>
    </div>
  )
}

export function AssetWorkspace({ token, userId, dashboard, cards, loading, dashboardError, cardError, hidden, actionDisabled, cardLossRecovery, onRetry, onCardLossRecoveryChange, onCardLossResolved, onActionBusy, onActionPrepared, onReference }: {
  token: string
  userId: number
  dashboard: BankDashboardData | null
  cards: BankCard[]
  loading: boolean
  dashboardError: string | null
  cardError: string | null
  hidden: boolean
  actionDisabled: boolean
  cardLossRecovery: ReadonlyMap<number, CardLossRecovery>
  onRetry: () => void
  onCardLossRecoveryChange: (cardId: number, value: CardLossRecovery | null) => void
  onCardLossResolved: (cardId: number) => void
  onActionBusy: (busy: boolean) => void
  onActionPrepared: (event: Extract<StreamEvent, { type: 'action_required' }>) => void
  onReference?: (reference: BankObjectReference) => void
}) {
  const [activeSection, setActiveSection] = useState<AssetSectionKey>('accounts')
  const counts = useMemo(() => ({
    accounts: dashboard?.accounts.length ?? 0,
    cards: cards.length,
    contacts: dashboard?.contacts.length ?? 0,
    holdings: dashboard?.holdings.length ?? 0,
  }), [cards.length, dashboard])

  function renderAccount(account: BankAccountOverview) {
    return <AccountCard
      key={account.account_id}
      account={account}
      hidden={hidden}
      onReference={onReference}
    />
  }

  const queryTime = dashboard ? formatQueryTime(dashboard.generated_at) : null

  return (
    <div className="space-y-7">
      <AssetSectionNavigation active={activeSection} onSelect={setActiveSection} />
      <AssetSection id="asset-section-accounts" title="银行账户" count={counts.accounts}>
        {dashboardError && <SectionError message={`账户与资产暂时无法读取：${dashboardError}`} onRetry={onRetry} />}
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取账户…</p>}
        {!loading && dashboard?.accounts.length === 0 && <EmptyState label="暂无账户" />}
        {!loading && dashboard?.accounts.map(renderAccount)}
      </AssetSection>

      <AssetSection id="asset-section-cards" title="银行卡" count={counts.cards}>
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取银行卡…</p>}
        {!loading && cardError && <SectionError message={cardError} onRetry={onRetry} />}
        {!loading && !cardError && cards.length === 0 && <EmptyState label="暂无银行卡" />}
        {!loading && cards.map((card) => <CardEntry
          key={card.card_id}
          card={card}
          token={token}
          disabled={actionDisabled}
          recovery={cardLossRecovery}
          onRecoveryChange={onCardLossRecoveryChange}
          onResolved={onCardLossResolved}
          onBusyChange={onActionBusy}
          onPrepared={onActionPrepared}
          onReference={onReference}
        />)}
      </AssetSection>

      <AssetSection id="asset-section-contacts" title="联系人" count={counts.contacts}>
        {!loading && dashboardError && <p role="status" className="text-xs leading-5 text-muted">账户与资产数据不可用，联系人暂时无法显示。</p>}
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取联系人…</p>}
        {!loading && dashboard?.contacts.length === 0 && <EmptyState label="暂无联系人" />}
        {!loading && dashboard?.contacts.length ? <div className="rounded-xl border border-line bg-white px-4">{dashboard.contacts.map((contact) => <ContactRow key={contact.contact_id} contact={contact} onReference={onReference} />)}</div> : null}
      </AssetSection>

      <AssetSection id="asset-section-holdings" title="理财持仓" count={counts.holdings}>
        {!loading && dashboardError && <p role="status" className="text-xs leading-5 text-muted">账户与资产数据不可用，持仓暂时无法显示。</p>}
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取持仓…</p>}
        {!loading && dashboard?.holdings.length === 0 && <EmptyState label="暂无持仓" />}
        {!loading && dashboard?.holdings.length ? <div className="rounded-xl border border-line bg-white px-4">{dashboard.holdings.map((holding) => <HoldingRow key={holding.holding_id} holding={holding} hidden={hidden} onReference={onReference} />)}</div> : null}
      </AssetSection>

      <MonthlyBillPanel
        token={token}
        userId={userId}
        hidden={hidden}
        accounts={dashboard?.accounts ?? null}
        accountListLoading={loading && dashboard === null && dashboardError === null}
        accountListError={dashboardError}
      />

      {queryTime && <p className="pb-2 text-[11px] text-muted">查询于 {queryTime}</p>}
    </div>
  )
}
