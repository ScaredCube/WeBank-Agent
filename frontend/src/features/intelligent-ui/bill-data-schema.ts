import { z } from 'zod'

const fen = z.number().int().safe().nonnegative()
const count = z.number().int().safe().nonnegative()
export const billSchema = z.object({
  month: z.string().regex(/^[0-9]{4}-(0[1-9]|1[0-2])$/),
  account_name: z.string().max(200),
  masked_number: z.string().max(100),
  currency: z.literal('CNY'),
  income_fen: fen,
  expense_fen: fen,
  consumption_fen: fen,
  consumption_count: count,
  transfer_out_fen: fen,
  transfer_out_count: count,
  transfer_in_fen: fen,
  transfer_in_count: count,
  investment_out_fen: fen,
  investment_out_count: count,
  investment_in_fen: fen,
  investment_in_count: count,
  categories: z.array(z.object({ category: z.string().max(200), amount_fen: fen, count })).max(100),
  anomalies: z.array(z.object({ status: z.literal('需核对').optional(), reason: z.string().max(200), counterparty: z.string().max(200), amount_fen: fen, occurred_at: z.iso.datetime({ offset: true }), previous_occurred_at: z.iso.datetime({ offset: true }) })).max(100),
  ignored_count: count,
})
