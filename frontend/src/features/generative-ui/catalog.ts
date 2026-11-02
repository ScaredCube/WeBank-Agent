import { defineCatalog } from '@json-render/core'
import { schema } from '@json-render/react/schema'
import { z } from 'zod'

const empty = z.object({}).strict()
const ref = z.object({ dataset_ref: z.string() }).strict()
export const catalog = defineCatalog(schema, { components: {
  Stack: { props: empty }, Grid: { props: empty }, Section: { props: z.object({ title_key: z.enum(['overview','categories','comparison','subscriptions','candidates','anomalies']) }).strict() },
  Metric: { props: z.object({ metric_ref: z.string() }).strict() },
  MetricComparison: { props: ref }, CategoryBarChart: { props: ref }, ComparisonTable: { props: ref }, RecordList: { props: ref }, SelectableList: { props: ref }, Filter: { props: ref }, Selector: { props: ref },
  ActionLink: { props: z.object({ action: z.enum(['open_workspace','view_source','follow_up']) }).strict() },
}, actions: {} })
