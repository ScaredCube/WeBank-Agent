const { test, expect } = require('@playwright/test')

const fixtureToken = 'e2e-only-token'

function createConversation() {
  const now = new Date().toISOString()
  return { id: 1, title: '新对话', created_at: now, updated_at: now }
}

function createMessages(userContent) {
  const now = new Date().toISOString()
  return [
    { id: 101, role: 'user', content: userContent, created_at: now },
    { id: 102, role: 'assistant', content: '请核对这笔模拟转账。', created_at: now },
  ]
}

function createTransferEvent() {
  return {
    type: 'action_required',
    confirmation_token: 'e2e-only-confirmation',
    transfer_id: 42,
    action: {
      id: 7,
      action_type: 'transfer',
      risk_level: 'yellow',
      status: 'pending',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      details: {
        account_masked: '日常账户 · ****8899',
        recipient_name: '林小姐',
        recipient_phone_masked: '138****0000',
        amount_fen: 1250,
        currency: 'CNY',
        note: 'browser fixture',
      },
    },
  }
}

async function installApiFixture(context, { rejectLogin = false } = {}) {
  const calls = []
  const unexpectedCalls = []
  let conversation = null
  let history = []

  await context.route('**/api/**', async (route) => {
    const request = route.request()
    const method = request.method()
    const pathname = new URL(request.url()).pathname
    const isLoginRequest = method === 'POST' && pathname === '/api/auth/login'
    const isHealthCheck = method === 'GET' && pathname === '/api/health'
    calls.push(`${method} ${pathname}`)

    if (!isLoginRequest && !isHealthCheck &&
        request.headers().authorization !== `Bearer ${fixtureToken}`) {
      unexpectedCalls.push(`${method} ${pathname} (缺少测试鉴权头)`)
      await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: '测试请求缺少鉴权' }) })
      return
    }

    if (isLoginRequest) {
      if (rejectLogin) {
        await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: '账号或密码错误' }) })
      } else {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            access_token: fixtureToken,
            token_type: 'bearer',
            user: { id: 9, username: 'browser-fixture', display_name: '浏览器样例' },
          }),
        })
      }
      return
    }

    if (isHealthCheck) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', app: 'e2e', llm: { mode: 'mock', model: 'fixture' } }) })
      return
    }

    if (pathname === '/api/chat/conversations' && method === 'GET') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation ? [conversation] : []) })
      return
    }
    if (pathname === '/api/chat/conversations' && method === 'POST') {
      conversation = createConversation()
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversation) })
      return
    }
    if (pathname === '/api/chat/conversations/1/messages' && method === 'GET') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(history) })
      return
    }
    if (pathname === '/api/chat/conversations/1/messages' && method === 'POST') {
      const userContent = request.postDataJSON().content
      history = createMessages(userContent)
      const events = [
        createTransferEvent(),
        { type: 'done', message: history[1] },
      ]
      const body = `${events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')}`
      await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream; charset=utf-8' }, body })
      return
    }
    if (method === 'GET' && pathname === '/api/bank/dashboard') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          accounts: [{ account_id: 11, name: '日常账户', masked_number: '****8899', currency: 'CNY', balance_fen: 23860, status: 'active', card_status: 'active', can_transfer: true }],
          contacts: [],
          holdings: [],
          risk_profile: { risk_level: 'R1', score: 1, assessed_at: null },
          generated_at: new Date().toISOString(),
        }),
      })
      return
    }
    if (method === 'GET' && pathname === '/api/cards') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{ card_id: 21, account_name: '日常账户', masked_number: '****8899', status: 'active', account_status: 'active' }]),
      })
      return
    }
    if (method === 'GET' && pathname === '/api/audit') {
      await route.fulfill({ contentType: 'application/json', body: '[]' })
      return
    }
    if (method === 'POST' && pathname === '/api/actions/7/confirm') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 7, status: 'confirmed', message: '已记录确认，操作尚未执行。' }) })
      return
    }
    if (method === 'POST' && pathname === '/api/transfers/42/execute') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'completed', message: '模拟转账已完成（浏览器样例）。' }) })
      return
    }

    unexpectedCalls.push(`${method} ${pathname}`)
    await route.fulfill({ status: 501, contentType: 'application/json', body: JSON.stringify({ detail: '未配置此浏览器样例接口' }) })
  })

  return {
    calls,
    assertNoUnexpectedCalls() {
      expect(unexpectedCalls, `未配置的 API 请求: ${unexpectedCalls.join(', ')}`).toEqual([])
    },
  }
}

test('正式对话路由完成模拟登录、资产读取及确认后执行的转账流程', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } })
  const fixture = await installApiFixture(context)
  const page = await context.newPage()

  try {
    await page.goto('/chat')
    await expect(page).toHaveURL(/\/login$/)
    await page.getByLabel('账号').fill('browser-fixture')
    await page.getByLabel('密码').fill('fixture-not-a-real-password')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/chat$/)
    await expect(page.getByPlaceholder('说说你想办的事')).toBeVisible()

    await page.getByRole('button', { name: '打开导航和会话列表' }).click()
    await page.getByRole('button', { name: '资产', exact: true }).click()
    await expect(page.getByRole('region', { name: '资产' })).toBeVisible()
    await expect(page.locator('#asset-section-accounts').getByRole('heading', { name: '日常账户' })).toBeVisible()
    await expect(page.getByText('¥238.60', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '收起资产区' }).click()

    await page.getByPlaceholder('说说你想办的事').fill('给林小姐转 12.50 元')
    await page.getByRole('button', { name: '发送' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('heading', { name: '确认模拟转账' })).toBeVisible()
    await expect(dialog.getByText('¥12.50')).toBeVisible()
    await dialog.getByRole('button', { name: '确认' }).click()
    await expect(dialog.getByText('已确认，操作尚未执行。')).toBeVisible()
    await dialog.getByRole('button', { name: '执行操作' }).click()
    await expect(dialog.getByText('模拟转账已完成（浏览器样例）。')).toBeVisible()

    expect(fixture.calls).toContain('POST /api/chat/conversations/1/messages')
    expect(fixture.calls).toContain('POST /api/actions/7/confirm')
    expect(fixture.calls).toContain('POST /api/transfers/42/execute')
    expect(fixture.calls.indexOf('POST /api/actions/7/confirm')).toBeLessThan(fixture.calls.indexOf('POST /api/transfers/42/execute'))
    fixture.assertNoUnexpectedCalls()
  } finally {
    await context.close()
  }
})

test('正式登录页展示服务端拒绝并保留可重试入口', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } })
  const fixture = await installApiFixture(context, { rejectLogin: true })
  const page = await context.newPage()

  try {
    await page.goto('/login')
    await page.getByLabel('账号').fill('browser-fixture')
    await page.getByLabel('密码').fill('fixture-not-a-real-password')
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page.getByRole('alert')).toHaveText('账号或密码错误')
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('button', { name: '登录' })).toBeEnabled()
    fixture.assertNoUnexpectedCalls()
  } finally {
    await context.close()
  }
})
