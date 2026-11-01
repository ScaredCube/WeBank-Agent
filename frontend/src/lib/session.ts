type Listener = (expiredToken: string) => void
const listeners = new Set<Listener>()

export function subscribeUnauthorized(listener: Listener): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function notifyUnauthorized(token: string): void {
  for (const listener of listeners) listener(token)
}
