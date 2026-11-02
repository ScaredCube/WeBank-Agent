import { z } from 'zod'

const key = z.string().min(1).max(120)
const scalar = z.union([z.string().max(500), z.number().finite(), z.boolean(), z.null()])
const dataset = z.object({ kind: z.enum(['categories', 'comparison', 'records', 'subscriptions', 'candidates']), title: z.string().max(200), columns: z.array(z.object({ key, label: z.string().max(200), format: z.enum(['text', 'currency', 'number', 'percent']) }).strict()).max(20), rows: z.array(z.record(z.string(), scalar).and(z.object({ id: z.string().min(1).max(160) }))).max(200) }).strict()
const envelope = z.object({
  schema_version: z.literal(1), catalog_version: z.literal(1), view_id: key, revision: z.number().int().positive(), conversation_id: z.number().int().positive(), result_refs: z.array(key).max(20), observed_at: z.string().refine(v => Number.isFinite(Date.parse(v))),
  spec: z.object({ root: key, elements: z.record(key, z.object({ type: key, props: z.record(z.string(), z.unknown()), children: z.array(key).max(40).nullish().transform(v => v ?? undefined) }).strict()) }).strict(),
  interaction_state: z.object({ selected_category: z.string().max(160).nullable(), selected_ids: z.array(z.string().min(1).max(160)).max(100), sort: z.enum(['default', 'amount_desc', 'amount_asc']), filter: z.enum(['all', 'active', 'renewal_soon']) }).strict(),
  allowed_actions: z.array(z.enum(['select_category', 'select_ids', 'set_sort', 'set_filter', 'clear_filters'])).max(5),
  trusted_data: z.object({ metrics: z.record(key, z.object({ label: z.string().max(200), value: z.number().finite().nullable(), format: z.enum(['currency', 'number', 'percent']), period: z.string().max(200).nullish().transform(v => v ?? undefined), note: z.string().max(500).nullish().transform(v => v ?? undefined) }).strict()), datasets: z.record(key, dataset) }).strict(),
}).strict()
export type ViewEnvelope = z.infer<typeof envelope>
const datasets: Record<string, string[]> = { MetricComparison: ['comparison'], CategoryBarChart: ['categories'], ComparisonTable: ['comparison'], RecordList: ['records'], SelectableList: ['subscriptions', 'candidates'], Filter: ['subscriptions', 'candidates'], Selector: ['categories'] }

/** Treat the layout as untrusted even when its data came from the server. */
export function parseView(raw: unknown): ViewEnvelope | null {
  const parsed = envelope.safeParse(raw)
  if (!parsed.success) return null
  const v = parsed.data, entries = Object.entries(v.spec.elements)
  if (Object.keys(v.trusted_data.metrics).length > 100 || Object.keys(v.trusted_data.datasets).length > 40) return null
  if (Object.values(v.trusted_data.metrics).some(m => m.format === 'currency' && m.value !== null && !Number.isSafeInteger(m.value))) return null
  for (const data of Object.values(v.trusted_data.datasets)) for (const col of data.columns) if (col.format === 'currency' && data.rows.some(row => row[col.key] !== null && !Number.isSafeInteger(row[col.key]))) return null
  if (!entries.length || entries.length > 40 || !v.spec.elements[v.spec.root]) return null
  const visited = new Set<string>()
  function visit(id: string, depth: number): boolean {
    if (depth > 6 || visited.has(id)) return false
    const node = v.spec.elements[id]
    if (!node) return false
    visited.add(id)
    const { type, props, children = [] } = node
    const keys = Object.keys(props)
    if (type === 'Stack' || type === 'Grid') { if (keys.length) return false }
    else if (type === 'Section') { if (keys.length !== 1 || typeof props.title_key !== 'string' || !['overview','categories','comparison','subscriptions','candidates','anomalies'].includes(props.title_key)) return false }
    else if (type === 'Metric') { if (keys.length !== 1 || typeof props.metric_ref !== 'string' || !Object.hasOwn(v.trusted_data.metrics, props.metric_ref)) return false }
    else if (type === 'ActionLink') { if (keys.length !== 1 || typeof props.action !== 'string' || !['open_workspace','view_source','follow_up'].includes(props.action)) return false }
    else if (datasets[type]) { if (keys.length !== 1 || typeof props.dataset_ref !== 'string' || !Object.hasOwn(v.trusted_data.datasets, props.dataset_ref) || !datasets[type].includes(v.trusted_data.datasets[props.dataset_ref].kind)) return false }
    else return false
    const ref = props.metric_ref ?? props.dataset_ref
    if (typeof ref === 'string' && !v.result_refs.includes(ref.split(':', 1)[0])) return false
    if (!['Stack','Grid','Section'].includes(type) && children.length) return false
    return children.every(child => visit(child, depth + 1))
  }
  return visit(v.spec.root, 1) && visited.size === entries.length ? v : null
}
