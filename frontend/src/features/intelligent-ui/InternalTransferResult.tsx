import { z } from 'zod'
import { Check } from 'lucide-react'

import { Money } from '@/features/privacy/Money'

export const internalTransferResultSchema = z.object({
  transfer_id: z.number().int().safe().positive(),
  status: z.literal('completed'),
  amount_fen: z.number().int().safe().positive(),
  note: z.string().max(120),
  source_name: z.string().min(1).max(80),
  source_masked: z.string().min(1).max(40),
  target_name: z.string().min(1).max(80),
  target_masked: z.string().min(1).max(40),
  balance_fen: z.number().int().safe().nonnegative(),
  currency: z.string().max(8),
  transaction_id: z.number().int().safe().positive().nullable(),
})

export function InternalTransferResult({ value }: { value: unknown }) {
  const parsed = internalTransferResultSchema.safeParse(value)
  if (!parsed.success) return null
  const result = parsed.data
  return <article aria-label="内部转账结果" className="flex items-start gap-3 rounded-2xl border border-jade-200 bg-jade-50/60 px-4 py-4">
    <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-jade-100 text-jade-800"><Check size={17} /></span>
    <div className="min-w-0 flex-1">
      <p className="text-[12px] text-muted">内部转账完成</p>
      <p className="mt-0.5 text-[22px] font-semibold tracking-tight text-ink">
        <Money fen={result.amount_fen} peekKey={`internal:${result.transfer_id}`} />
      </p>
      <p className="mt-1 break-words text-[11px] leading-5 text-muted">
        {result.source_name} {result.source_masked} → {result.target_name} {result.target_masked}
        {result.note ? ` · ${result.note}` : ''}
      </p>
      <p className="mt-1 text-[10.5px] text-muted">来源账户余额 <Money fen={result.balance_fen} peekKey={`internal-balance:${result.transfer_id}`} /></p>
    </div>
  </article>
}
