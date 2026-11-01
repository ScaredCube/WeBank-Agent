import { z } from 'zod'

const statusRow = z.object({
  card_id: z.number().int().safe().positive(),
  account_name: z.string().max(120),
  masked_number: z.string().max(90),
  status: z.string().max(30),
  account_status: z.string().max(30),
})
export const cardStatusSnapshotSchema = z.object({
  cards: z.array(statusRow).max(30),
})
