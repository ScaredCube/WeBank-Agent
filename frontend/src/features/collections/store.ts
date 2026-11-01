import { cardOriginSchema, cardSchema, type CardDescription, type CardOrigin } from '@/features/intelligent-ui/schema'

export interface RefreshSpec { kind: 'monthly_bill'; month: string; accountId: number }
export interface Snapshot { id: string; savedAt: string; card: unknown; refresh?: RefreshSpec }
interface StoredSnapshot extends Snapshot { key: string; userId: number }

function redact(value: string): string {
  return value.replace(/<[^<>]{3,}>/g, '[已隐藏]').replace(/\d{11,}/g, '[已隐藏]')
}

type SnapshotLeaf = Exclude<CardDescription['blocks'][number], { type: 'group' | 'action' }>
function sanitizeLeaf(block: SnapshotLeaf): SnapshotLeaf {
  if (block.type === 'text') return { type: 'text', text: redact(block.text) }
  if (block.type === 'metric') return { ...block, label: redact(block.label) }
  if (block.type === 'bar_chart') return { type: 'bar_chart', title: redact(block.title), rows: block.rows.map((row) => ({ label: redact(row.label), value: row.value })) }
  return { type: 'list', rows: block.rows.map((row) => ({ label: redact(row.label), value: redact(row.value) })) }
}

function sanitize(value: unknown, trustedOrigin?: CardOrigin): CardDescription {
  const card = cardSchema.parse(value)
  // The adapter supplies the association; a card description cannot attest to its own origin.
  const origin = trustedOrigin ? cardOriginSchema.parse(trustedOrigin) : undefined
  return {
    version: 1, id: redact(card.id), title: redact(card.title), source: redact(card.source), observedAt: card.observedAt,
    ...(origin ? { origin } : {}),
    blocks: card.blocks.filter((block) => block.type !== 'action').map((block) => {
      if (block.type === 'group') return { type: 'group', layout: block.layout, blocks: block.blocks.filter((item) => item.type !== 'action').map(sanitizeLeaf) }
      return sanitizeLeaf(block)
    }),
  }
}

const DEFAULT_DATABASE = 'webank-ui-snapshots'

function openDatabase(databaseName = DEFAULT_DATABASE): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1)
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore('snapshots', { keyPath: 'key' })
      store.createIndex('userId', 'userId')
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('无法打开本地收藏'))
    request.onblocked = () => reject(new Error('本地收藏被其他页面占用'))
  })
}

function run<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>, databaseName?: string): Promise<T> {
  return openDatabase(databaseName).then((database) => new Promise<T>((resolve, reject) => {
    const transaction = database.transaction('snapshots', mode)
    const request = operation(transaction.objectStore('snapshots'))
    transaction.oncomplete = () => { database.close(); resolve(request.result) }
    transaction.onerror = () => { database.close(); reject(transaction.error ?? new Error('本地收藏操作失败')) }
    transaction.onabort = () => { database.close(); reject(transaction.error ?? new Error('本地收藏操作已中止')) }
  }))
}

function requireUser(userId: number) {
  if (!Number.isSafeInteger(userId) || userId <= 0) throw new Error('无法识别当前用户')
}

export async function saveSnapshot(userId: number, value: unknown, databaseName?: string, trustedOrigin?: CardOrigin, refresh?: RefreshSpec): Promise<Snapshot> {
  requireUser(userId)
  if (refresh && (refresh.kind !== 'monthly_bill' || !/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(refresh.month) ||
      !Number.isSafeInteger(refresh.accountId) || refresh.accountId <= 0)) throw new Error('刷新来源无效')
  const snapshot: Snapshot = { id: crypto.randomUUID(), savedAt: new Date().toISOString(), card: sanitize(value, trustedOrigin), ...(refresh ? { refresh } : {}) }
  const stored: StoredSnapshot = { ...snapshot, key: `${userId}:${snapshot.id}`, userId }
  await run('readwrite', (store) => store.add(stored), databaseName)
  return snapshot
}

export async function listSnapshots(userId: number, databaseName?: string): Promise<Snapshot[]> {
  requireUser(userId)
  const rows = await run<StoredSnapshot[]>('readonly', (store) => store.index('userId').getAll(userId), databaseName)
  const prefix = `${userId}:`
  return rows.filter((row) => typeof row.key === 'string' && row.key.startsWith(prefix)).map((row) => ({
    id: row.key.slice(prefix.length),
    savedAt: typeof row.savedAt === 'string' && Number.isFinite(Date.parse(row.savedAt)) ? row.savedAt : '',
    card: row.card,
    ...(row.refresh?.kind === 'monthly_bill' && /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(row.refresh.month) && Number.isSafeInteger(row.refresh.accountId) && row.refresh.accountId > 0 ? { refresh: row.refresh } : {}),
  })).sort((a, b) => b.savedAt.localeCompare(a.savedAt))
}

export async function refreshSnapshot(userId: number, id: string, value: unknown, databaseName?: string): Promise<Snapshot> {
  requireUser(userId)
  const stored = await run<StoredSnapshot | undefined>('readonly', store => store.get(`${userId}:${id}`), databaseName)
  if (!stored || stored.userId !== userId || !stored.refresh) throw new Error('此收藏没有可用的刷新来源')
  const original = cardSchema.safeParse(stored.card)
  if (!original.success) throw new Error('原收藏无法验证，已保留')
  const updated: StoredSnapshot = { ...stored, card: sanitize(value, original.data.origin) }
  await run('readwrite', store => store.put(updated), databaseName)
  return { id, savedAt: updated.savedAt, card: updated.card, refresh: updated.refresh }
}

export async function deleteSnapshot(userId: number, id: string, databaseName?: string): Promise<void> {
  requireUser(userId)
  await run('readwrite', (store) => store.delete(`${userId}:${id}`), databaseName)
}

export async function clearSnapshots(userId: number, databaseName?: string): Promise<void> {
  requireUser(userId)
  const database = await openDatabase(databaseName)
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction('snapshots', 'readwrite')
    const store = transaction.objectStore('snapshots')
    const cursor = store.index('userId').openKeyCursor(IDBKeyRange.only(userId))
    cursor.onsuccess = () => { const item = cursor.result; if (item) { store.delete(item.primaryKey); item.continue() } }
    transaction.oncomplete = () => { database.close(); resolve() }
    transaction.onerror = () => { database.close(); reject(transaction.error ?? new Error('清空收藏失败')) }
    transaction.onabort = () => { database.close(); reject(transaction.error ?? new Error('清空收藏已中止')) }
  })
}
