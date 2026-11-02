import { z } from 'zod'
const subscription = z.object({ subscription_id: z.number().int().positive(), merchant: z.string(), amount_fen: z.number().int().safe(), cycle: z.string(), next_charge_date: z.string().nullable(), days_until_charge: z.number().nullable(), renewal_soon: z.boolean(), status: z.string(), can_cancel: z.boolean() })
const candidate = z.object({ merchant: z.string(), amount_fen: z.number().int().safe(), occurrences: z.number().int(), last_occurred_at: z.string(), suggested_cycle: z.string() })
const metadata = {result_ref:z.string().optional(), observed_at:z.string().optional()}
export const subscriptionResultSchema = z.discriminatedUnion('kind', [z.object({kind:z.literal('subscriptions'),data:z.array(subscription).max(200),...metadata}), z.object({kind:z.literal('subscription_candidates'),data:z.array(candidate).max(200),...metadata})])
export type SubscriptionResultData = z.infer<typeof subscriptionResultSchema>
