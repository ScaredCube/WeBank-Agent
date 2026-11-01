import { z } from 'zod'

const text = z.string().max(500)
const leafBlock = z.discriminatedUnion('type', [
  z.object({ type: z.literal('text'), text }),
  z.object({ type: z.literal('metric'), label: text, value: z.number().int().safe(), unit: z.literal('CNY_FEN') }),
  z.object({ type: z.literal('list'), rows: z.array(z.object({ label: text, value: text })).max(100) }),
  z.object({ type: z.literal('bar_chart'), title: text, rows: z.array(z.object({ label: text, value: z.number().int().safe().nonnegative() })).min(1).max(12) }),
  z.object({ type: z.literal('action'), action: z.enum(['open_assets', 'open_collections', 'open_activity']) }),
])
const block = z.union([leafBlock, z.object({ type: z.literal('group'), layout: z.enum(['stack', 'columns']), blocks: z.array(leafBlock).max(12) })])
export const cardOriginSchema = z.object({ conversationId: z.number().int().safe().positive(), messageId: z.number().int().safe().positive() })
export const cardSchema = z.object({ version: z.literal(1), id: z.string().min(1).max(100), title: text, source: text, observedAt: z.iso.datetime({ offset: true }), origin: cardOriginSchema.optional(), blocks: z.array(block).max(30) })
export type CardDescription = z.infer<typeof cardSchema>
export type CardOrigin = z.infer<typeof cardOriginSchema>
export type CardAction = 'open_assets' | 'open_collections' | 'open_activity'
