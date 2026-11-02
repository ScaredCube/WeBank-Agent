// Node 24 runs the project's pure TypeScript Catalog without an extra runtime.
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { catalog } from '../frontend/src/features/generative-ui/catalog.ts';

const target = new URL('../fixtures/generative-ui/catalog-prompt.txt', import.meta.url);
const { z } = createRequire(new URL('../frontend/package.json', import.meta.url))('zod');
// The library's default prompt enables JSONL and mutable application state.
// Generate our restricted application vocabulary from the same Catalog instead.
const components = Object.fromEntries(Object.entries(catalog.data.components).map(
  ([name, definition]) => [name, z.toJSONSchema(definition.props)],
));
const prompt = 'Generate a read-only XiaoWe UI as ONE JSON object: '
  + '{"root":"id","elements":{"id":{"type":"ComponentName","props":{},"children":[]}}}.\n'
  + 'Only Stack, Grid and Section can contain children. Use a connected tree, at most 40 nodes and depth 6.\n'
  + 'Component props schemas generated from the frontend Catalog:\n'
  + JSON.stringify(components, null, 2) + '\n'
  + 'Use only issued metric_ref/dataset_ref. Do not output JSONL, patches, state, expressions, events, code, sample data or financial values.\n';
if (process.argv.includes('--check')) {
  const current = await readFile(target, 'utf8').catch(() => '');
  if (current.replaceAll('\r\n', '\n') !== prompt.replaceAll('\r\n', '\n')) {
    throw new Error('Catalog drift: run node scripts/generate-ui-catalog.mjs');
  }
  console.log('Catalog prompt is up to date');
} else {
  await writeFile(target, prompt, 'utf8');
  console.log('Generated ' + fileURLToPath(target));
}
