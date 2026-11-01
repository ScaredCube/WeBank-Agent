const PREFIX = '【前置意图】'

export type ParsedIntentMessage = {
  intent: string | null
  text: string
}

/** Server-authored user message: the first paragraph is the display capsule,
 * followed by a blank line and the user's own text. Older messages without the
 * marker are returned unchanged. */
export function parseIntentMessage(content: string): ParsedIntentMessage {
  if (typeof content !== 'string' || !content.startsWith(PREFIX)) return { intent: null, text: content }
  const split = content.indexOf('\n\n')
  if (split < 0) return { intent: null, text: content }
  const line = content.slice(0, split)
  const intent = line.slice(PREFIX.length).trim()
  if (!intent || !intent.includes(' · ') || !intent.includes(' → ')) return { intent: null, text: content }
  return { intent, text: content.slice(split + 2) }
}

export function formatIntentBubble(intent: string): string {
  return `前置意图 · ${intent}`
}
