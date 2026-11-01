import { useMemo, useState, type FormEvent } from 'react'
import { CreditCard, Landmark, ChartNoAxesCombined, AlertCircle, RefreshCw, Plus } from 'lucide-react'

import { api, type BankAccountOverview, type BankCard, type BankContactOverview, type BankDashboardData, type WealthHoldingOverview } from '@/lib/api'
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
    <article className="min-h-[132px] rounded-2xl border border-line bg-panel px-5 py-5 pb-12 transition-shadow hover:shadow-[0_12px_26px_-20px_rgba(0,38,29,.32)]">
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
      <details className="mt-4 border-t border-line pt-3 text-xs">
        <summary className="w-fit cursor-pointer list-none font-medium text-jade-800 focus-visible:outline-2 focus-visible:outline-jade-700">账户详情</summary>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl bg-canvas/50 p-3">
          <div><dt className="text-muted">账户状态</dt><dd className="mt-1 font-medium text-ink">{accountStatus(account.status)}</dd></div>
          <div><dt className="text-muted">关联银行卡</dt><dd className="mt-1 font-medium text-ink">{cardStatus(account.card_status)}</dd></div>
          <div><dt className="text-muted">币种</dt><dd className="mt-1 font-medium text-ink">{account.currency}</dd></div>
          <div><dt className="text-muted">模拟转账</dt><dd className="mt-1 font-medium text-ink">{account.can_transfer ? '可准备操作' : '暂不可用'}</dd></div>
        </dl>
      </details>
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
    <article className="relative min-h-[196px] overflow-hidden rounded-[22px] border border-jade-700/30 bg-gradient-to-br from-[#15483e] via-[#236353] to-[#0e3f36] px-5 py-5 pb-14 text-white shadow-[0_18px_35px_-25px_rgba(5,47,34,.64)]">
      <div aria-hidden="true" className="pointer-events-none absolute -right-12 -top-20 size-48 rounded-full border border-white/10 bg-white/[0.04]" />
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/15 text-amber-200"><CreditCard size={18} /></span>
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-[14px] font-semibold text-white">WeBank · 模拟银行卡</h4>
          <p className="mt-1 truncate text-xs text-white/70">{card.account_name}</p>
        </div>
        <span className="shrink-0 rounded-lg border border-white/25 px-2 py-1 text-[11px] text-white/85">{cardStatus(card.status)}</span>
      </div>
      <div className="mt-5 h-3.5 w-6 rounded-[4px] bg-amber-200/85" aria-hidden="true" />
      <p className="mt-3 font-mono text-[20px] font-semibold tracking-[0.18em] text-white">{card.masked_number}</p>
      <details className="mt-4 border-t border-white/20 pt-3">
        <summary className="cursor-pointer list-none text-xs font-medium text-white/90 focus-visible:outline-2 focus-visible:outline-jade-700">卡片操作</summary>
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
    <div className="flex min-h-[104px] items-center gap-3 border-b border-line py-3 pb-12 last:border-b-0">
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
    <div className="flex min-h-[106px] items-center gap-3 border-b border-line py-3 pb-12 last:border-b-0">
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

export function AssetWorkspace({ token, userId, dashboard, cards, loading, dashboardError, cardError, hidden, actionDisabled, cardLossRecovery, onRetry, onCardLossRecoveryChange, onCardLossResolved, onActionBusy, onActionPrepared, onReference, onAccountCreated }: {
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
  onAccountCreated?: () => void
}) {
  const [activeSection, setActiveSection] = useState<AssetSectionKey>('accounts')
  const [showAddInfo, setShowAddInfo] = useState(false)
  const [newAccountName, setNewAccountName] = useState('')
  const [creatingAccount, setCreatingAccount] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
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

  async function createAccount(event: FormEvent) {
    event.preventDefault()
    if (creatingAccount) return
    setCreatingAccount(true); setCreateError(null)
    try {
      await api.createDemoAccount(token, newAccountName.trim())
      setShowAddInfo(false); setNewAccountName('')
      onAccountCreated?.()
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : '创建失败，请稍后重试。')
    } finally { setCreatingAccount(false) }
  }

  const queryTime = dashboard ? formatQueryTime(dashboard.generated_at) : null

  return (
    <div className="space-y-7">
      <AssetSectionNavigation active={activeSection} onSelect={setActiveSection} />
      <div role="tabpanel" aria-labelledby={`asset-tab-${activeSection}`} id={`asset-panel-${activeSection}`}>
      {activeSection === 'accounts' && <AssetSection id="asset-section-accounts" title="银行账户" count={counts.accounts}>
        <div className="mb-4 flex justify-end"><button type="button" onClick={() => setShowAddInfo(true)} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-3 text-sm font-medium text-jade-800 hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700"><Plus size={16} />新增模拟账户</button></div>
        {dashboardError && <SectionError message={`账户与资产暂时无法读取：${dashboardError}`} onRetry={onRetry} />}
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取账户…</p>}
        {!loading && dashboard?.accounts.length === 0 && <EmptyState label="暂无账户" />}
        {!loading && dashboard?.accounts.map(renderAccount)}
      </AssetSection>}

      {activeSection === 'cards' && <AssetSection id="asset-section-cards" title="银行卡" count={counts.cards}>
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
      </AssetSection>}

      {activeSection === 'contacts' && <AssetSection id="asset-section-contacts" title="联系人" count={counts.contacts}>
        {!loading && dashboardError && <p role="status" className="text-xs leading-5 text-muted">账户与资产数据不可用，联系人暂时无法显示。</p>}
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取联系人…</p>}
        {!loading && dashboard?.contacts.length === 0 && <EmptyState label="暂无联系人" />}
        {!loading && dashboard?.contacts.length ? <div className="rounded-xl border border-line bg-white px-4">{dashboard.contacts.map((contact) => <ContactRow key={contact.contact_id} contact={contact} onReference={onReference} />)}</div> : null}
      </AssetSection>}

      {activeSection === 'holdings' && <AssetSection id="asset-section-holdings" title="理财持仓" count={counts.holdings}>
        {!loading && dashboardError && <p role="status" className="text-xs leading-5 text-muted">账户与资产数据不可用，持仓暂时无法显示。</p>}
        {loading && <p role="status" className="rounded-xl border border-line bg-white px-4 py-5 text-xs text-muted">正在读取持仓…</p>}
        {!loading && dashboard?.holdings.length === 0 && <EmptyState label="暂无持仓" />}
        {!loading && dashboard?.holdings.length ? <div className="rounded-xl border border-line bg-white px-4">{dashboard.holdings.map((holding) => <HoldingRow key={holding.holding_id} holding={holding} hidden={hidden} onReference={onReference} />)}</div> : null}
      </AssetSection>}

      {activeSection === 'bill' && <MonthlyBillPanel
        token={token}
        userId={userId}
        hidden={hidden}
        accounts={dashboard?.accounts ?? null}
        accountListLoading={loading && dashboard === null && dashboardError === null}
        accountListError={dashboardError}
      />}
      </div>
      {showAddInfo && <div role="dialog" aria-modal="true" aria-label="新增模拟账户" onKeyDown={(event) => { if (event.key === 'Escape' && !creatingAccount) { event.preventDefault(); event.stopPropagation(); setShowAddInfo(false); setCreateError(null) } }} className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-6">
        <form onSubmit={(event) => void createAccount(event)} className="w-full max-w-sm rounded-2xl border border-line bg-panel p-6 shadow-xl">
          <h3 className="text-lg font-semibold text-ink">新增模拟账户</h3>
          <p className="mt-2 text-sm leading-6 text-muted">创建一个余额为零、无关联银行卡的演示账户，不涉及真实开户或资金。</p>
          <label htmlFor="new-account-name" className="mt-5 block text-sm font-medium text-ink">账户名称</label>
          <input id="new-account-name" autoFocus required minLength={2} maxLength={24} value={newAccountName} onChange={event => setNewAccountName(event.target.value)} placeholder="例如：我的备用账户" className="mt-2 min-h-11 w-full rounded-xl border border-line bg-canvas px-3 text-base text-ink focus-visible:outline-2 focus-visible:outline-jade-700" />
          {createError && <p role="alert" className="mt-3 text-sm text-red-700">{createError}</p>}
          <div className="mt-5 flex justify-end gap-2"><button type="button" disabled={creatingAccount} onClick={() => {setShowAddInfo(false);setCreateError(null)}} className="min-h-10 rounded-xl border border-line px-4 text-sm text-ink">取消</button>
          <button type="submit" disabled={creatingAccount || newAccountName.trim().length < 2} className="min-h-10 rounded-xl bg-jade-700 px-4 text-sm font-semibold text-white disabled:opacity-50">{creatingAccount ? '创建中…' : '创建账户'}</button></div>
        </form>
      </div>}

      {queryTime && <p className="pb-2 text-[11px] text-muted">查询于 {queryTime}</p>}
    </div>
  )
}
