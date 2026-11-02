const { mkdirSync } = require('node:fs')
const path = require('node:path')
const { test, expect } = require('@playwright/test')

const fixtureToken = 'generative-ui-e2e-only-token'
const conversationId = 71
const viewId = 'generative-ui-view-e2e'
const branchViewId = `${viewId}-branch`

function screenshotPath(name) {
  const directory = path.resolve(__dirname, '..', 'output', 'playwright')
  mkdirSync(directory, { recursive: true })
  return path.join(directory, name)
}

function createConversation() {
  const now = new Date().toISOString()
  return { id: conversationId, title: '账单分析', created_at: now, updated_at: now }
}

function createView(revision, selectedCategory = null, id = viewId) {
  return {
    schema_version: 1,
    catalog_version: 1,
    view_id: id,
    revision,
    conversation_id: conversationId,
    result_refs: ['monthly-bill-fixture'],
    observed_at: '2026-11-01T10:00:00.000Z',
    spec: {
      root: 'root',
      elements: {
        root: { type: 'Stack', props: {}, children: ['categories-section'] },
        'categories-section': { type: 'Section', props: { title_key: 'categories' }, children: ['categories-list'] },
        'categories-list': { type: 'CategoryBarChart', props: { dataset_ref: 'monthly-bill-fixture:categories' } },
      },
    },
    interaction_state: {
      selected_category: selectedCategory,
      selected_ids: [],
      sort: 'default',
      filter: 'all',
    },
    allowed_actions: ['select_category'],
    trusted_data: {
      metrics: {},
      datasets: {
        'monthly-bill-fixture:categories': {
          kind: 'categories',
          title: '2026年10月支出分类',
          columns: [
            { key: 'category', label: '分类', format: 'text' },
            { key: 'amount_fen', label: '支出', format: 'currency' },
            { key: 'count', label: '笔数', format: 'number' },
          ],
          rows: [
            { id: 'food', category: '餐饮', amount_fen: 4250, count: 3 },
            { id: 'transport', category: '交通', amount_fen: 1800, count: 2 },
          ],
        },
      },
    },
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function createMessage(id, role, content, uiView) {
  return {
    id,
    role,
    content,
    created_at: new Date().toISOString(),
    ...(uiView === undefined ? {} : { ui_view: clone(uiView) }),
  }
}

async function installApiFixture(context, { malformedView = false, branchOnStaleContext = false } = {}) {
  const calls = []
  const unexpectedCalls = []
  const chatRequests = []
  const interactions = []
  const viewVersions = new Map()
  const viewReads = []
  let conversation = null
  let history = []
  let currentView = null

  await context.route('**/api/**', async (route) => {
    const request = route.request()
    const method = request.method()
    const url = new URL(request.url())
    const pathname = url.pathname
    const isLogin = method === 'POST' && pathname === '/api/auth/login'
    const isHealth = method === 'GET' && pathname === '/api/health'
    calls.push(`${method} ${pathname}`)

    if (!isLogin && !isHealth && request.headers().authorization !== `Bearer ${fixtureToken}`) {
      unexpectedCalls.push(`${method} ${pathname} (缺少测试鉴权头)`)
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '隔离浏览器样例缺少测试鉴权头' }),
      })
      return
    }

    if (isLogin) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: fixtureToken,
          token_type: 'bearer',
          user: { id: 99, username: 'generative-ui-fixture', display_name: '隔离样例' },
        }),
      })
      return
    }

    if (isHealth) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', app: 'e2e', llm: { mode: 'mock', model: 'fixture' } }),
      })
      return
    }

    if (method === 'GET' && pathname === '/api/chat/conversations') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation ? [conversation] : []) })
      return
    }
    if (method === 'POST' && pathname === '/api/chat/conversations') {
      conversation = createConversation()
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    if (method === 'GET' && pathname === `/api/chat/conversations/${conversationId}/messages`) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(history) })
      return
    }
    if (method === 'POST' && pathname === `/api/chat/conversations/${conversationId}/messages`) {
      const body = request.postDataJSON()
      chatRequests.push(body)
      const turnIndex = chatRequests.length - 1
      const userMessage = createMessage(101 + turnIndex * 2, 'user', body.content)
      let responseView

      if (turnIndex === 0) {
        responseView = createView(1)
        if (malformedView) responseView.spec.elements.root.type = 'UnsafeHtml'
        currentView = clone(responseView)
        viewVersions.set(responseView.revision, clone(responseView))
      } else {
        const requestView = body.view_context
        const staleContext = branchOnStaleContext && requestView && currentView &&
          requestView.view_id === currentView.view_id && requestView.revision < currentView.revision
        if (staleContext) {
          const sourceSnapshot = viewVersions.get(requestView.revision)
          responseView = createView(1, sourceSnapshot?.interaction_state.selected_category ?? null, branchViewId)
        } else {
          const nextRevision = (currentView?.revision ?? 1) + 1
          responseView = createView(nextRevision, currentView?.interaction_state.selected_category ?? null, currentView?.view_id ?? viewId)
        }
        currentView = clone(responseView)
        viewVersions.set(responseView.revision, clone(responseView))
      }

      const assistantMessage = createMessage(
        102 + turnIndex * 2,
        'assistant',
        turnIndex === 0 ? '已整理本月支出分类。' : '已根据所选分类继续分析。',
        responseView,
      )
      history = [...history, userMessage, assistantMessage]
      const events = [
        { type: 'ui_status', status: 'composing' },
        { type: 'ui_view', view: responseView },
        { type: 'delta', text: assistantMessage.content },
        { type: 'done', message: assistantMessage },
      ]
      await route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream; charset=utf-8' },
        body: `${events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')}`,
      })
      return
    }

    if (method === 'GET' && pathname === '/api/bank/dashboard') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          accounts: [], contacts: [], holdings: [],
          risk_profile: { risk_level: 'R1', score: 1, assessed_at: null },
          generated_at: new Date().toISOString(),
        }),
      })
      return
    }
    if (method === 'GET' && pathname === '/api/cards') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify([]) })
      return
    }
    if (method === 'GET' && pathname === '/api/views/health') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) })
      return
    }
    if (method === 'GET' && pathname === `/api/views/${viewId}`) {
      const requestedRevision = url.searchParams.has('revision')
        ? Number(url.searchParams.get('revision'))
        : undefined
      viewReads.push(requestedRevision)
      const view = requestedRevision === undefined
        ? currentView
        : viewVersions.get(requestedRevision)
      if (!view) {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: '视图版本不存在' }) })
        return
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(view) })
      return
    }
    if (method === 'POST' && pathname === `/api/views/${viewId}/interactions`) {
      const body = request.postDataJSON()
      interactions.push(body)
      if (!currentView || body.base_revision !== currentView.revision || body.action !== 'select_category' || !['food', 'transport'].includes(body.value)) {
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '视图版本或分类不匹配' }) })
        return
      }
      const updated = createView(currentView.revision + 1, body.value)
      currentView = clone(updated)
      viewVersions.set(updated.revision, clone(updated))
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(updated) })
      return
    }

    unexpectedCalls.push(`${method} ${pathname}`)
    await route.fulfill({
      status: 501,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '未配置此 Generative UI 浏览器样例接口' }),
    })
  })

  return {
    calls,
    chatRequests,
    interactions,
    viewReads,
    storedMessages: () => clone(history),
    assertNoUnexpectedCalls() {
      expect(unexpectedCalls, `未配置的 API 请求: ${unexpectedCalls.join(', ')}`).toEqual([])
    },
  }
}

async function loginToChat(page) {
  await page.goto('/chat')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('账号').fill('generative-ui-fixture')
  await page.getByRole('textbox', { name: '密码' }).fill('fixture-only-not-a-real-password')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await expect(page.getByPlaceholder('说说你想办的事')).toBeVisible()
}

async function sendMessage(page, content) {
  await page.getByPlaceholder('说说你想办的事').fill(content)
  await page.getByRole('button', { name: '发送' }).click()
}

test('当前工作区可自然语言续问、保存分类后推进视图且旧历史快照不变', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 1280, height: 900 } })
  const fixture = await installApiFixture(context)
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  try {
    await loginToChat(page)
    await sendMessage(page, '查询本月账单并分析主要支出分类')

    const firstReply = page.locator('[data-message-id="102"]')
    await expect(firstReply.getByText('已整理本月支出分类。')).toBeVisible()
    await expect(firstReply.getByText('2026年10月支出分类')).toBeVisible()
    await expect(firstReply.getByRole('button', { name: '打开工作区' })).toBeVisible()
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 1280)

    await firstReply.getByRole('button', { name: '打开工作区' }).click()
    const workspace = page.getByRole('region', { name: '分析工作区' })
    await expect(workspace).toBeVisible()
    await expect(workspace.getByText(/历史版本 1/)).toBeVisible()
    await expect(page.getByText(/基于工作区版本 1 继续分析/)).toBeVisible()

    // Desktop keeps the workspace open while the user asks the agent a natural-language follow-up.
    await sendMessage(page, '请基于当前工作区再解释一次主要支出')
    await expect(page.locator('[data-message-id="104"]')).toContainText('已根据所选分类继续分析。')
    await expect(workspace.getByText(/历史版本 2/)).toBeVisible()
    await expect(page.getByText(/基于工作区版本 2 继续分析/)).toBeVisible()
    expect(fixture.chatRequests).toHaveLength(2)
    expect(fixture.chatRequests[0].view_context).toBeUndefined()
    expect(fixture.chatRequests[1].view_context).toEqual({ view_id: viewId, revision: 1 })

    const food = workspace.getByRole('button', { name: '餐饮', exact: true })
    await expect(food).toHaveAttribute('aria-pressed', 'false')
    await food.click()
    await expect(food).toHaveAttribute('aria-pressed', 'true')
    await expect.poll(() => fixture.interactions.length).toBe(1)
    expect(fixture.interactions[0]).toMatchObject({ base_revision: 2, action: 'select_category', value: 'food' })
    await expect(workspace.getByText(/历史版本 3/)).toBeVisible()
    await expect(page.getByText(/基于工作区版本 3 继续分析/)).toBeVisible()
    await expect(page.getByText('已选餐饮')).toBeVisible()

    // The latest message can reopen the exact message snapshot separately from the current saved view.
    const secondReply = page.locator('[data-message-id="104"]')
    await workspace.getByRole('button', { name: '返回对话' }).click()
    await secondReply.getByRole('button', { name: '查看原始版本' }).click()
    const originalWorkspace = page.getByRole('region', { name: '分析工作区' })
    await expect(originalWorkspace.getByText(/历史版本 2/)).toBeVisible()
    await expect(originalWorkspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'false')
    expect(fixture.viewReads).toEqual([undefined])
    await originalWorkspace.getByRole('button', { name: '返回对话' }).click()

    await secondReply.getByRole('button', { name: '打开工作区' }).click()
    let latestWorkspace = page.getByRole('region', { name: '分析工作区' })
    await expect(latestWorkspace.getByText(/历史版本 3/)).toBeVisible()
    await expect(latestWorkspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'true')
    expect(fixture.viewReads).toEqual([undefined, undefined])

    // Reload the formal route; opening its latest view message must recover the server's current revision.
    await latestWorkspace.getByRole('button', { name: '返回对话' }).click()
    await page.reload()
    await expect(page.getByPlaceholder('说说你想办的事')).toBeVisible()
    await page.locator('[data-message-id="104"]').getByRole('button', { name: '打开工作区' }).click()
    latestWorkspace = page.getByRole('region', { name: '分析工作区' })
    await expect(latestWorkspace.getByText(/历史版本 3/)).toBeVisible()
    await expect(latestWorkspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'true')
    expect(fixture.viewReads).toEqual([undefined, undefined, undefined])

    await sendMessage(page, '请进一步分析餐饮分类的支出情况')
    await expect(page.locator('[data-message-id="106"]')).toContainText('已根据所选分类继续分析。')
    await expect(latestWorkspace.getByText(/历史版本 4/)).toBeVisible()
    expect(fixture.chatRequests).toHaveLength(3)
    expect(fixture.chatRequests[2].view_context).toEqual({ view_id: viewId, revision: 3 })

    const storedHistory = fixture.storedMessages()
    expect(storedHistory[1].ui_view).toMatchObject({ revision: 1, interaction_state: { selected_category: null } })
    expect(storedHistory[3].ui_view).toMatchObject({ revision: 2, interaction_state: { selected_category: null } })
    expect(storedHistory[5].ui_view).toMatchObject({ revision: 4, interaction_state: { selected_category: 'food' } })

    // Opening an older message restores its immutable snapshot, not the latest working revision.
    await latestWorkspace.getByRole('button', { name: '返回对话' }).click()
    await firstReply.getByRole('button', { name: '打开工作区' }).click()
    const historicalWorkspace = page.getByRole('region', { name: '分析工作区' })
    await expect(historicalWorkspace.getByText(/历史版本 1/)).toBeVisible()
    await expect(historicalWorkspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'false')
    await historicalWorkspace.getByRole('button', { name: '返回对话' }).click()

    // The newest message restores the durable server revision after a browser reload.
    await page.reload()
    await expect(page.getByPlaceholder('说说你想办的事')).toBeVisible()
    const latestReply = page.locator('[data-message-id="106"]')
    await latestReply.getByRole('button', { name: '打开工作区' }).click()
    latestWorkspace = page.getByRole('region', { name: '分析工作区' })
    await expect(latestWorkspace.getByText(/历史版本 4/)).toBeVisible()
    await expect(latestWorkspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'true')
    expect(fixture.viewReads).toEqual([undefined, undefined, undefined, undefined])
    await page.screenshot({ path: screenshotPath('generative-ui-desktop.png'), animations: 'disabled' })

    await page.setViewportSize({ width: 360, height: 780 })
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 360)
    await page.screenshot({ path: screenshotPath('generative-ui-mobile-360.png'), animations: 'disabled' })
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390)
    await page.screenshot({ path: screenshotPath('generative-ui-mobile-390.png'), animations: 'disabled' })

    expect(pageErrors).toEqual([])
    fixture.assertNoUnexpectedCalls()
  } finally {
    await context.close()
  }
})

test('手机工作区点“继续分析”后回到输入区并保留视图上下文', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 360, height: 780 } })
  const fixture = await installApiFixture(context)
  const page = await context.newPage()

  try {
    await loginToChat(page)
    await sendMessage(page, '查询本月账单并分析主要支出分类')
    const firstReply = page.locator('[data-message-id="102"]')
    await firstReply.getByRole('button', { name: '打开工作区' }).click()
    const workspace = page.getByRole('region', { name: '分析工作区' })
    await expect(workspace).toBeVisible()
    await expect(workspace.getByRole('button', { name: '继续分析', exact: true })).toBeVisible()

    await workspace.getByRole('button', { name: '继续分析', exact: true }).click()
    await expect(workspace).toHaveCount(0)
    await expect(page.getByText(/基于工作区版本 1 继续分析/)).toBeVisible()
    await sendMessage(page, '请解释这个消费分类')
    await expect(page.locator('[data-message-id="104"]')).toContainText('已根据所选分类继续分析。')
    expect(fixture.chatRequests[1].view_context).toEqual({ view_id: viewId, revision: 1 })
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 360)
    fixture.assertNoUnexpectedCalls()
  } finally {
    await context.close()
  }
})

test('从较早快照续问创建新 view_id 后，后续提问转接到该分支', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } })
  const fixture = await installApiFixture(context, { branchOnStaleContext: true })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  try {
    await loginToChat(page)
    await sendMessage(page, '查询本月账单并分析主要支出分类')
    const firstReply = page.locator('[data-message-id="102"]')
    await firstReply.getByRole('button', { name: '打开工作区' }).click()
    let workspace = page.getByRole('region', { name: '分析工作区' })
    await expect(workspace.getByText(/历史版本 1/)).toBeVisible()
    await workspace.getByRole('button', { name: '餐饮', exact: true }).click()
    await expect(workspace.getByText(/历史版本 2/)).toBeVisible()
    await expect(workspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'true')

    await workspace.getByRole('button', { name: '返回对话' }).click()
    await firstReply.getByRole('button', { name: '查看原始版本' }).click()
    workspace = page.getByRole('region', { name: '分析工作区' })
    await expect(workspace.getByText(/历史版本 1/)).toBeVisible()
    await expect(workspace.getByRole('button', { name: '餐饮', exact: true })).toHaveAttribute('aria-pressed', 'false')
    await workspace.getByRole('button', { name: '继续分析', exact: true }).click()
    await expect(page.getByText(/基于工作区版本 1 继续分析/)).toBeVisible()

    await sendMessage(page, '从这个历史版本继续分析')
    await expect(page.locator('[data-message-id="104"]')).toContainText('已根据所选分类继续分析。')
    const branchedHistory = fixture.storedMessages()
    expect(fixture.chatRequests[1].view_context).toEqual({ view_id: viewId, revision: 1 })
    expect(branchedHistory[1].ui_view).toMatchObject({ view_id: viewId, revision: 1, interaction_state: { selected_category: null } })
    expect(branchedHistory[3].ui_view).toMatchObject({ view_id: branchViewId, revision: 1 })

    await sendMessage(page, '请基于刚才的新分支继续分析')
    await expect(page.locator('[data-message-id="106"]')).toContainText('已根据所选分类继续分析。')
    expect(fixture.chatRequests[2].view_context).toEqual({ view_id: branchViewId, revision: 1 })
    expect(fixture.storedMessages()[3].ui_view).toMatchObject({ view_id: branchViewId, revision: 1 })
    expect(pageErrors).toEqual([])
    fixture.assertNoUnexpectedCalls()
  } finally {
    await context.close()
  }
})

test('正式对话遇到畸形 ui_view 时保留回复并回退展示', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } })
  const fixture = await installApiFixture(context, { malformedView: true })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  try {
    await loginToChat(page)
    await sendMessage(page, '查询本月账单并分析主要支出分类')

    const reply = page.locator('[data-message-id="102"]')
    await expect(reply.getByText('已整理本月支出分类。')).toBeVisible()
    await expect(reply.getByRole('status')).toContainText('此视图暂时无法展示，原始结果仍可查看。')
    await expect(reply.getByRole('button', { name: '打开工作区' })).toHaveCount(0)
    await expect(page.getByPlaceholder('说说你想办的事')).toBeVisible()
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390)
    expect(pageErrors).toEqual([])
    fixture.assertNoUnexpectedCalls()
  } finally {
    await context.close()
  }
})
