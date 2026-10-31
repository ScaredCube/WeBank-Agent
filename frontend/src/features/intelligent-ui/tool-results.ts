import { z } from 'zod'
import type { Message } from '@/lib/api'

export const toolResultItemSchema = z.discriminatedUnion('kind', [
  z.object({kind:z.literal('monthly_bill'),data:z.unknown()}),
  z.object({kind:z.literal('card_status'),data:z.unknown()}),
])
export const toolResultListSchema = z.array(toolResultItemSchema).max(8)
export type ToolResultItem = z.infer<typeof toolResultItemSchema>

/** Old single-card histories remain readable with no database migration. */
export function messageToolResults(message: Message): ToolResultItem[] {
  if (message.tool_results != null) {
    const result = toolResultListSchema.safeParse(message.tool_results)
    return result.success ? result.data : []
  }
  const values: ToolResultItem[] = []
  if (message.bill_result) values.push({kind:'monthly_bill',data:message.bill_result})
  if (message.card_result) values.push({kind:'card_status',data:message.card_result})
  return values
}
