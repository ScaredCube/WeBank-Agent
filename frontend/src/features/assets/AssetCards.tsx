import { CreditCard, GripVertical, Landmark } from 'lucide-react'
import type { PointerEvent as ReactPointerEvent } from 'react'

import type { BankAccountOverview, BankContactOverview, WealthHoldingOverview } from '@/lib/api'
import { Money } from '@/features/privacy/Money'
import { cn } from '@/lib/utils'
import type { IntentEntity } from './intent'

type Common = {
  entity: IntentEntity
  selected: boolean
  dropActive: boolean
  onSelect: () => void
  onDetails?: () => void
  onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void
}

export function AssetBankCard({ account, entity, selected, dropActive, onSelect, onDetails, onPointerDown, index }: Common & {
  account: BankAccountOverview
  index: number
}) {
  const frozen = account.card_status === 'lost' || account.status !== 'active'
  const alt = index % 2 === 1
  return <article
    data-asset-kind={entity.kind}
    data-asset-id={entity.id}
    data-asset-disabled={entity.disabled ? '1' : undefined}
    aria-label={`${account.name}，尾号 ${account.masked_number}，余额${entity.disabled ? '不可用' : '可拖动'}`}
    aria-disabled={entity.disabled}
    role="button"
    tabIndex={entity.disabled ? -1 : 0}
    onClick={() => { if (!entity.disabled) onSelect() }}
    onKeyDown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect() }
    }}
    onPointerDown={onPointerDown}
    className={cn(
      'relative flex min-h-[132px] touch-pan-y select-none flex-col justify-between overflow-hidden rounded-[20px] px-5 py-4 text-left shadow-[0_16px_30px_-22px_rgba(6,40,30,.8)] transition-[transform,box-shadow,opacity]',
      alt ? 'text-[#2C2A1E]' : 'text-white',
      alt
        ? 'bg-[radial-gradient(130%_140%_at_90%_-20%,rgba(255,255,255,.66),transparent_55%),linear-gradient(140deg,#E4D7B9_0%,#DACCAA_55%,#CDBE99_100%)]'
        : 'bg-[radial-gradient(120%_130%_at_88%_-10%,rgba(126,190,156,.34),transparent_55%),linear-gradient(140deg,#1B4232_0%,#123026_48%,#0E241D_100%)]',
      selected && 'ring-2 ring-jade-500 ring-offset-2 ring-offset-workspace',
      dropActive && 'ring-2 ring-emerald-400',
      entity.disabled && 'cursor-default opacity-55 grayscale',
      !entity.disabled && 'cursor-grab active:cursor-grabbing',
    )}
  >
    <span aria-hidden="true" className="pointer-events-none absolute -bottom-16 -right-10 size-40 rounded-full border border-white/10" />
    <div className="flex items-center justify-between gap-3 text-[11px] tracking-[0.04em] opacity-80">
      <span className="truncate font-medium">{account.name}</span>
      <span className="flex shrink-0 items-center gap-2">
        {frozen && <span className="rounded-md bg-white/15 px-1.5 py-0.5 text-[9px]">已挂失</span>}
        <CreditCard size={15} className="opacity-60" />
      </span>
    </div>
    <div className="flex items-baseline gap-1.5">
      <span className="text-[11px] opacity-60">¥</span>
      <Money fen={account.balance_fen} currency={account.currency}
        peekKey={`account:${account.account_id}`}
        className="text-[22px] font-semibold tracking-[-0.03em]" />
    </div>
    <div className="flex items-center justify-between gap-3 font-mono text-[10px] tracking-[0.16em] opacity-65">
      <span>{account.masked_number}</span>
      <span className="flex items-center gap-2 font-sans tracking-normal">
        {onDetails && <button type="button" onClick={(event) => { event.stopPropagation(); onDetails() }}
          className="rounded-md px-1.5 py-1 text-[10px] hover:bg-white/10">详情</button>}
        <GripVertical size={14} aria-hidden="true" className="opacity-60" />
      </span>
    </div>
  </article>
}

export function AssetContactCard({ contact, entity, selected, dropActive, onSelect, onPointerDown }: Common & {
  contact: BankContactOverview
}) {
  return <button
    type="button"
    data-asset-kind={entity.kind}
    data-asset-id={entity.id}
    data-asset-disabled={entity.disabled ? '1' : undefined}
    disabled={entity.disabled}
    aria-pressed={selected}
    aria-label={`联系人 ${contact.name}，电话 ${contact.masked_phone}`}
    onClick={onSelect}
    onPointerDown={onPointerDown}
    className={cn(
      'flex min-h-[104px] touch-pan-y select-none flex-col items-center gap-1 rounded-[18px] border border-line-2 bg-panel px-2 pb-3 pt-4 text-center transition',
      selected && 'border-jade-500 bg-jade-50',
      dropActive && 'border-emerald-400 bg-emerald-50',
      entity.disabled ? 'cursor-default opacity-50' : 'cursor-grab hover:-translate-y-0.5 hover:shadow-md',
    )}
  >
    <span aria-hidden="true" className="grid size-10 place-items-center rounded-full bg-[#eef4f2] text-[14px] font-semibold text-jade-800">
      {contact.name.slice(0, 1)}
    </span>
    <span className="max-w-full truncate text-[12px] font-semibold text-ink">{contact.name}</span>
    <span className="max-w-full truncate font-mono text-[9px] text-muted">{contact.masked_phone}</span>
  </button>
}

export function AssetHoldingCard({ holding, entity, selected, dropActive, onSelect, onPointerDown }: Common & {
  holding: WealthHoldingOverview
}) {
  const up = holding.yesterday_earnings_fen >= 0
  return <button
    type="button"
    data-asset-kind={entity.kind}
    data-asset-id={entity.id}
    data-asset-disabled={entity.disabled ? '1' : undefined}
    disabled={entity.disabled}
    aria-pressed={selected}
    aria-label={`持仓 ${holding.product_name}，金额 ${holding.amount_fen} 分`}
    onClick={onSelect}
    onPointerDown={onPointerDown}
    className={cn(
      'flex w-full touch-pan-y select-none items-center gap-3 rounded-[16px] border border-line-2 bg-panel px-4 py-3 text-left transition',
      selected && 'border-jade-500 bg-jade-50',
      dropActive && 'border-emerald-400 bg-emerald-50',
      entity.disabled ? 'cursor-default opacity-50' : 'cursor-grab hover:-translate-y-0.5 hover:shadow-md',
    )}
  >
    <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-[#eef4f2] text-jade-800">
      <Landmark size={18} strokeWidth={1.8} />
    </span>
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[12.5px] font-semibold text-ink">{holding.product_name}</span>
      <span className="mt-0.5 block truncate text-[10px] text-muted">{holding.category} · 风险 {holding.risk_level}</span>
    </span>
    <span className="shrink-0 text-right">
      <Money fen={holding.amount_fen} peekKey={`holding:${holding.holding_id}`} className="block text-[12px] font-semibold text-ink" />
      <span className={cn('mt-0.5 block font-mono text-[9.5px]', up ? 'text-jade-700' : 'text-red-600')}>
        <Money fen={holding.yesterday_earnings_fen} peekKey={`holding-yield:${holding.holding_id}`} />
      </span>
    </span>
  </button>
}
