/* Live Generative UI browser check. Uses only the runner's isolated synthetic DB.
   No API interception, operation confirmation, screenshots, or financial output. */
const { chromium } = require('../node_modules/playwright')

const BASE = 'http://127.0.0.1:5222'
const API_BASE = 'http://127.0.0.1:8022'
const CHAT_TIMEOUT = 180000
const UI_TIMEOUT = 30000
const CHAT_POST = /\/api\/chat\/conversations\/\d+\/messages$/

function insist(condition, code) {
  if (!condition) throw new Error(code)
}

function isChatResponse(response) {
  return response.request().method() === 'POST' && CHAT_POST.test(new URL(response.url()).pathname)
}

function readChatRequest(response) {
  insist(response.ok(), 'CHAT_REQUEST_REJECTED')
  const url = new URL(response.url())
  const match = url.pathname.match(/\/api\/chat\/conversations\/(\d+)\/messages$/)
  const authorization = response.request().headers().authorization
  insist(match, 'CHAT_ENDPOINT_MISMATCH')
  insist(typeof authorization === 'string' && authorization.startsWith('Bearer '), 'CHAT_AUTH_HEADER_MISSING')
  return {
    conversationId: Number(match[1]),
    authorization,
    body: response.request().postDataJSON(),
  }
}

async function waitForMessage(page, api, authorization, conversationId, requestId) {
  insist(typeof requestId === 'string' && requestId.length >= 8, 'REQUEST_ID_MISSING')
  const deadline = Date.now() + CHAT_TIMEOUT
  while (Date.now() < deadline) {
    const response = await api.get(`${API_BASE}/api/chat/conversations/${conversationId}/requests/${encodeURIComponent(requestId)}`, {
      headers: { authorization },
    })
    if (response.status() === 429) {
      await new Promise(resolve => setTimeout(resolve, 3000))
      continue
    }
    insist(response.ok(), `REQUEST_STATUS_FAILED_${response.status()}`)
    const status = await response.json()
    if (status.state === 'completed') {
      const found = status.message
      insist(found?.role === 'assistant', 'PERSISTED_MESSAGE_MISSING')
      insist(found.ui_view, 'PERSISTED_VIEW_MISSING')
      const element = page.locator(`[data-message-id="${found.id}"]`)
      await element.getByRole('button', { name: '打开工作区', exact: true }).waitFor({ timeout: UI_TIMEOUT })
      return found
    }
    insist(!['failed', 'interrupted', 'action_pending'].includes(status.state), 'REQUEST_NOT_COMPLETED')
    await new Promise(resolve => setTimeout(resolve, 2000))
  }
  throw new Error('REQUEST_STATUS_TIMEOUT')
}

function categoryDataset(view) {
  return Object.values(view?.trusted_data?.datasets ?? {}).find(dataset => dataset.kind === 'categories') ?? null
}

function formatFen(fen) {
  const absolute = Math.abs(fen)
  const yuan = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(Math.floor(absolute / 100))
  return `¥${fen < 0 ? '-' : ''}${yuan}.${String(absolute % 100).padStart(2, '0')}`
}

function answerHasAmount(text, amountFen) {
  const candidates = []
  for (const match of text.matchAll(/[¥￥]\s*(-?[\d,]+(?:\.\d{1,2})?)/gu)) candidates.push(match[1])
  for (const match of text.matchAll(/(-?[\d,]+(?:\.\d{1,2})?)\s*元/gu)) candidates.push(match[1])
  for (const match of text.matchAll(/(-?[\d,]+\.\d{2})(?!\d)/gu)) candidates.push(match[1])
  return candidates.some(value => Math.round(Number(value.replace(/,/g, '')) * 100) === amountFen)
}

function answerHasCount(text, count) {
  const digits = String(count)
  return new RegExp(`(?:^|[^0-9])${digits}\\s*笔|笔数\\s*[:：为]?\\s*${digits}(?![0-9])`).test(text)
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.getByLabel('账号').fill('demo')
  await page.getByRole('textbox', { name: '密码' }).fill('demo123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL(url => url.pathname === '/chat', { timeout: UI_TIMEOUT })
  await page.getByRole('heading', { name: '今天，想完成什么？' }).waitFor({ timeout: UI_TIMEOUT })
}

async function main() {
  let stage = 'BROWSER_LAUNCH'
  const setStage = name => {
    stage = name
    console.error(`E2E_STAGE ${name}`)
  }
  let browser
  let pageErrors = 0
  try {
    console.error(`E2E_STAGE ${stage}`)
    browser = await chromium.launch({ channel: 'msedge', headless: true })
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
    const page = await context.newPage()
    const api = context.request
    page.on('pageerror', () => { pageErrors += 1 })

    setStage('DEMO_LOGIN')
    await login(page)

    setStage('ACCOUNT_PICKER')
    const initialPrompt = '请查询 2026-01 月的消费账单，按支出分类汇总金额和笔数，并生成交互式分类分析。'
    const editor = page.getByRole('textbox', { name: '输入消息' })
    await editor.fill('请查看@账户')
    await page.getByRole('listbox', { name: '选择金融对象' }).waitFor({ timeout: UI_TIMEOUT })
    await page.getByRole('option').filter({ hasText: '演示活期账户' }).first().click()
    setStage('INITIAL_CHAT_REQUEST')
    await editor.fill(initialPrompt)
    const send = page.getByRole('button', { name: '发送' })
    const initialResponsePromise = page.waitForResponse(isChatResponse, { timeout: CHAT_TIMEOUT })
    await send.click({ timeout: UI_TIMEOUT })
    const initialResponse = await initialResponsePromise
    const initialRequest = readChatRequest(initialResponse)
    insist(typeof initialRequest.body.content === 'string' && initialRequest.body.content.includes('2026-01'), 'INITIAL_QUERY_NOT_EXPLICIT')
    insist(initialRequest.body.view_context == null, 'INITIAL_QUERY_HAS_VIEW_CONTEXT')
    insist(initialRequest.body.references?.some(reference => reference.kind === 'account'), 'INITIAL_ACCOUNT_REFERENCE_MISSING')
    setStage('INITIAL_HISTORY_READ')
    const initialMessage = await waitForMessage(page, api, initialRequest.authorization,
      initialRequest.conversationId, initialRequest.body.request_id)
    const initialTurn = { message: initialMessage, view: initialMessage.ui_view }
    setStage('INITIAL_VIEW_ASSERT')
    insist(initialTurn.view && initialTurn.message?.role === 'assistant' && Number.isSafeInteger(initialTurn.message.id), 'INITIAL_UI_VIEW_MISSING')
    insist(initialTurn.view.conversation_id === Number(new URL(initialResponse.url()).pathname.match(/conversations\/(\d+)/)?.[1]), 'INITIAL_VIEW_CONVERSATION_MISMATCH')
    const initialDataset = categoryDataset(initialTurn.view)
    insist(initialDataset && initialDataset.rows.length > 0, 'INITIAL_CATEGORY_DATA_MISSING')

    const firstMessage = page.locator(`[data-message-id="${initialTurn.message.id}"]`)
    await firstMessage.getByRole('button', { name: '打开工作区', exact: true }).waitFor({ timeout: UI_TIMEOUT })
    await firstMessage.getByRole('button', { name: '打开工作区', exact: true }).click()
    const workspace = page.getByRole('region', { name: '分析工作区' })
    await workspace.waitFor({ state: 'visible', timeout: UI_TIMEOUT })
    await workspace.getByText(new RegExp(`历史版本\\s*${initialTurn.view.revision}`)).waitFor({ timeout: UI_TIMEOUT })

    setStage('CATEGORY_SELECTION')
    const revealAmounts = page.getByRole('button', { name: '显示金额', exact: true })
    if (await revealAmounts.count()) await revealAmounts.first().click()
    const labelColumn = initialDataset.columns.find(column => column.format === 'text')
    const amountColumn = initialDataset.columns.find(column => column.key === 'amount_fen' && column.format === 'currency')
    const countColumn = initialDataset.columns.find(column => column.key === 'count' && column.format === 'number')
    insist(labelColumn && amountColumn && countColumn, 'CATEGORY_TRUSTED_COLUMNS_MISSING')
    insist(initialTurn.view.interaction_state?.selected_category == null, 'INITIAL_CATEGORY_ALREADY_SELECTED')
    const sourceRow = initialDataset.rows[0]
    insist(sourceRow, 'CATEGORY_TRUSTED_VALUES_MISSING')
    const categoryLabel = String(sourceRow[labelColumn.key])
    insist(sourceRow && Number.isSafeInteger(sourceRow[amountColumn.key]) && Number.isSafeInteger(sourceRow[countColumn.key]), 'CATEGORY_TRUSTED_VALUES_MISSING')
    const categoryButton = workspace.getByRole('button', { name: categoryLabel, exact: true })
    setStage('CATEGORY_BUTTON_WAIT')
    await categoryButton.waitFor({ state: 'visible', timeout: UI_TIMEOUT })
    insist(await categoryButton.getAttribute('aria-pressed') === 'false', 'INITIAL_CATEGORY_BUTTON_STATE_MISMATCH')

    const interactionResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && /\/api\/views\/[^/]+\/interactions$/.test(url.pathname)
    }, { timeout: UI_TIMEOUT })
    setStage('CATEGORY_CLICK')
    await categoryButton.click()
    setStage('CATEGORY_INTERACTION_RESPONSE')
    const interactionResponse = await interactionResponsePromise
    insist(interactionResponse.ok(), 'CATEGORY_INTERACTION_REJECTED')
    const selectedView = await interactionResponse.json()
    const interactionBody = interactionResponse.request().postDataJSON()
    insist(interactionBody.action === 'select_category' && interactionBody.value === sourceRow.id, 'CATEGORY_INTERACTION_MISMATCH')
    insist(interactionBody.base_revision === initialTurn.view.revision, 'CATEGORY_BASE_REVISION_MISMATCH')
    insist(selectedView.view_id === initialTurn.view.view_id && selectedView.revision > initialTurn.view.revision, 'CATEGORY_REVISION_NOT_ADVANCED')
    insist(selectedView.interaction_state?.selected_category === sourceRow.id, 'CATEGORY_SELECTION_NOT_SAVED')

    const selectedRow = categoryDataset(selectedView)?.rows.find(row => row.id === sourceRow.id)
    insist(selectedRow && selectedRow[amountColumn.key] === sourceRow[amountColumn.key] && selectedRow[countColumn.key] === sourceRow[countColumn.key], 'SELECTED_TRUSTED_VALUES_CHANGED')
    const amountFen = selectedRow[amountColumn.key]
    const transactionCount = selectedRow[countColumn.key]
    const selectedStatus = workspace.locator('[role="status"]').filter({ hasText: `已选${categoryLabel}` }).first()
    await selectedStatus.waitFor({ state: 'visible', timeout: UI_TIMEOUT })
    const selectionText = await selectedStatus.innerText()
    insist(selectionText.includes(formatFen(amountFen)) && selectionText.includes(`${transactionCount} 笔`), 'SELECTED_SUMMARY_MISSING_TRUSTED_VALUES')
    insist(await categoryButton.getAttribute('aria-pressed') === 'true', 'CATEGORY_UI_SELECTION_MISSING')

    setStage('VIEW_CONTEXT_FOLLOW_UP')
    const followUpPrompt = `请基于当前工作区，只分析我选中的“${categoryLabel}”分类，并说明金额和笔数。`
    await editor.fill(followUpPrompt)
    const followUpResponsePromise = page.waitForResponse(isChatResponse, { timeout: CHAT_TIMEOUT })
    await send.click({ timeout: UI_TIMEOUT })
    const followUpResponse = await followUpResponsePromise
    const followUpRequest = readChatRequest(followUpResponse)
    insist(followUpRequest.body.view_context?.view_id === selectedView.view_id && followUpRequest.body.view_context?.revision === selectedView.revision, 'FOLLOW_UP_VIEW_CONTEXT_MISMATCH')
    setStage('FOLLOW_UP_HISTORY_READ')
    const followUpMessage = await waitForMessage(page, api, followUpRequest.authorization,
      followUpRequest.conversationId, followUpRequest.body.request_id)
    insist(followUpMessage.id > initialTurn.message.id
      && followUpMessage.ui_view?.view_id === selectedView.view_id
      && followUpMessage.ui_view?.revision === selectedView.revision, 'FOLLOW_UP_SNAPSHOT_MISMATCH')
    const followUpTurn = { message: followUpMessage, view: followUpMessage.ui_view }
    insist(followUpTurn.view && followUpTurn.message?.role === 'assistant' && Number.isSafeInteger(followUpTurn.message.id), 'FOLLOW_UP_UI_VIEW_MISSING')
    insist(followUpTurn.view.conversation_id === selectedView.conversation_id, 'FOLLOW_UP_CONVERSATION_MISMATCH')
    insist(followUpTurn.view.interaction_state?.selected_category === sourceRow.id, 'FOLLOW_UP_CATEGORY_NOT_PRESERVED')
    const answer = followUpTurn.message.content
    insist(typeof answer === 'string' && answer.includes(categoryLabel), 'ANSWER_MISSING_SELECTED_CATEGORY')
    insist(answerHasAmount(answer, amountFen), 'ANSWER_MISSING_TRUSTED_AMOUNT')
    insist(answerHasCount(answer, transactionCount), 'ANSWER_MISSING_TRUSTED_COUNT')

    setStage('HISTORY_RESTORE')
    const followUpMessageElement = page.locator(`[data-message-id="${followUpTurn.message.id}"]`)
    await followUpMessageElement.getByRole('button', { name: '打开工作区', exact: true }).waitFor({ timeout: UI_TIMEOUT })
    await workspace.getByRole('button', { name: '返回对话', exact: true }).click()
    await firstMessage.getByRole('button', { name: '查看原始版本', exact: true }).click()
    const historicalWorkspace = page.getByRole('region', { name: '分析工作区' })
    await historicalWorkspace.getByText(new RegExp(`历史版本\\s*${initialTurn.view.revision}`)).waitFor({ timeout: UI_TIMEOUT })
    await historicalWorkspace.getByRole('button', { name: categoryLabel, exact: true }).waitFor({ state: 'visible', timeout: UI_TIMEOUT })
    insist(await historicalWorkspace.getByRole('button', { name: categoryLabel, exact: true }).getAttribute('aria-pressed') === 'false', 'HISTORICAL_SELECTION_CHANGED')

    await historicalWorkspace.getByRole('button', { name: '返回对话', exact: true }).click()
    await page.reload({ waitUntil: 'domcontentloaded' })
    const restoredFirstMessage = page.locator(`[data-message-id="${initialTurn.message.id}"]`)
    const restoredFollowUpMessage = page.locator(`[data-message-id="${followUpTurn.message.id}"]`)
    await restoredFirstMessage.getByRole('button', { name: '查看原始版本', exact: true }).waitFor({ timeout: UI_TIMEOUT })
    await restoredFollowUpMessage.getByRole('button', { name: '打开工作区', exact: true }).waitFor({ timeout: UI_TIMEOUT })

    await restoredFirstMessage.getByRole('button', { name: '查看原始版本', exact: true }).click()
    const restoredHistoricalWorkspace = page.getByRole('region', { name: '分析工作区' })
    await restoredHistoricalWorkspace.getByText(new RegExp(`历史版本\\s*${initialTurn.view.revision}`)).waitFor({ timeout: UI_TIMEOUT })
    insist(await restoredHistoricalWorkspace.getByRole('button', { name: categoryLabel, exact: true }).getAttribute('aria-pressed') === 'false', 'REFRESHED_HISTORICAL_SNAPSHOT_CHANGED')
    await restoredHistoricalWorkspace.getByRole('button', { name: '返回对话', exact: true }).click()

    const latestReadPromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'GET'
        && url.pathname === `/api/views/${encodeURIComponent(followUpTurn.view.view_id)}`
        && !url.searchParams.has('revision')
    }, { timeout: UI_TIMEOUT })
    await restoredFollowUpMessage.getByRole('button', { name: '打开工作区', exact: true }).click()
    const latestResponse = await latestReadPromise
    insist(latestResponse.ok(), `LATEST_VIEW_READ_FAILED_${latestResponse.status()}`)
    const latestView = await latestResponse.json()
    insist(latestView.revision === followUpTurn.view.revision, 'LATEST_VIEW_REVISION_NOT_RECOVERED')
    insist(latestView.interaction_state?.selected_category === sourceRow.id, 'LATEST_VIEW_SELECTION_NOT_RECOVERED')
    const latestWorkspace = page.getByRole('region', { name: '分析工作区' })
    await latestWorkspace.getByText(new RegExp(`历史版本\\s*${followUpTurn.view.revision}`)).waitFor({ timeout: UI_TIMEOUT })
    insist(pageErrors === 0, 'BROWSER_PAGE_ERROR')

    console.log(JSON.stringify({
      result: 'PASS',
      real_api: true,
      real_persisted_ui_view: true,
      category_interaction: true,
      view_context_follow_up: true,
      answer_matches_trusted_category_amount_count: true,
      original_message_snapshot_restored: true,
      latest_history_revision_restored: true,
      browser_errors: 0,
    }))
    await context.close()
  } catch (error) {
    const candidate = error instanceof Error ? error.message : ''
    const code = /^[A-Z][A-Z0-9_]{0,80}$/.test(candidate) ? candidate
      : error?.name === 'TimeoutError' ? 'PLAYWRIGHT_TIMEOUT'
      : candidate.includes('strict mode violation') ? 'AMBIGUOUS_LOCATOR'
      : 'PLAYWRIGHT_OR_RUNTIME_ERROR'
    // Only stage and error class: no page contents, account data or model output.
    console.error(JSON.stringify({ result: 'FAIL', stage, code, error_type: error?.name || 'unknown', page_errors: pageErrors }))
    process.exitCode = 1
  } finally {
    if (browser) await browser.close().catch(() => {})
  }
}

void main()
