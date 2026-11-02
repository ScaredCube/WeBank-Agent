const { test, expect } = require('@playwright/test')

const now = new Date().toISOString()
const dashboard = {
  accounts: [
    { account_id: 1, name: '工资卡', masked_number: '**** 0001', currency: 'CNY', balance_fen: 500000, status: 'active', card_status: 'active', can_transfer: true },
    { account_id: 2, name: '零钱账户', masked_number: '**** 0002', currency: 'CNY', balance_fen: 386012, status: 'active', card_status: 'active', can_transfer: true },
  ],
  contacts: [
    { contact_id: 7, name: '张三', bank_name: '招商银行', masked_phone: '138****0001', status: 'active', can_transfer: true },
  ],
  holdings: [
    { holding_id: 9, product_id: 1, product_name: '稳稳盈 90 天', category: '稳健理财', risk_level: 'R1', expected_rate_bps: 280, amount_fen: 100000, yesterday_earnings_fen: 80, status: 'active' },
  ],
  risk_profile: { risk_level: 'R2', score: 4, assessed_at: now },
  generated_at: now,
}

async function installFixture(context, requests) {
  await context.addInitScript(() => {
    localStorage.setItem('bank_agent.token', 'e2e-token')
    localStorage.setItem('bank_agent.user', JSON.stringify({ id: 1, username: 'demo', display_name: '演示用户' }))
  })
  await context.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok', app: 'test', llm: { mode: 'mock', model: 'mock' } } })
    if (path === '/api/bank/dashboard') return route.fulfill({ json: dashboard })
    if (path === '/api/cards') return route.fulfill({ json: [
      { card_id: 1, account_id: 1, account_name: '工资卡', masked_number: '**** 0001', status: 'active', account_status: 'active' },
      { card_id: 2, account_id: 2, account_name: '零钱账户', masked_number: '**** 0002', status: 'active', account_status: 'active' },
    ] })
    if (path === '/api/chat/conversations' && method === 'GET') return route.fulfill({ json: [] })
    if (path === '/api/chat/conversations' && method === 'POST') return route.fulfill({ json: { id: 1, title: '新对话', created_at: now, updated_at: now } })
    if (path.startsWith('/api/chat/conversations/1/messages') && method === 'GET') return route.fulfill({ json: [] })
    if (path === '/api/chat/conversations/1/messages' && method === 'POST') {
      requests.push(JSON.parse(request.postData() || '{}'))
      return route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-store' },
        body: 'data: {"type":"done","message":{"id":9,"role":"assistant","content":"已收到","created_at":"2026-01-01T00:00:00Z"}}\n\n',
      })
    }
    return route.fulfill({ status: 200, json: [] })
  })
}

async function openAssets(page) {
  const region = page.getByRole('region', { name: '资产' })
  const opener = page.getByRole('button', { name: '打开资产' })
  await Promise.race([
    region.waitFor({ state: 'visible' }).catch(() => {}),
    opener.waitFor({ state: 'visible' }).catch(() => {}),
  ])
  if (!(await region.isVisible().catch(() => false))) {
    await opener.click()
  }
  await expect(region).toBeVisible()
  await page.waitForTimeout(350)
}

test('mobile: asset selection creates a capsule and submits entity IDs', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const requests = []
  await installFixture(context, requests)
  const page = await context.newPage()
  await page.goto('/chat')
  await openAssets(page)
  await page.screenshot({ path: 'test-results/mobile-assets.png' })
  await page.getByRole('button', { name: /工资卡/ }).click()
  await page.getByRole('button', { name: /联系人 张三/ }).click()
  await expect(page.getByRole('button', { name: '移除前置意图' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '输入消息' })).toHaveValue(/800 元/)
  await page.screenshot({ path: 'test-results/mobile-capsule.png' })
  await page.getByRole('button', { name: '发送' }).click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0].intent).toEqual({
    action: 'transfer',
    source: { kind: 'account', id: 1 },
    target: { kind: 'contact', id: 7 },
  })
  expect(requests[0].references).toEqual([])
  await context.close()
})

test('desktop: privacy blurs amounts and reveals on click', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 860 } })
  await installFixture(context, [])
  const page = await context.newPage()
  await page.goto('/chat')
  await openAssets(page)
  await page.getByRole('button', { name: '隐藏金额' }).first().click()
  const amount = page.locator('[aria-label="金额已隐藏"]').first()
  await expect(amount).toBeVisible()
  const before = await page.locator('[aria-label="金额已隐藏"]').count()
  await amount.click()
  await expect.poll(() => page.locator('[aria-label="金额已隐藏"]').count()).toBeLessThan(before)
  await page.screenshot({ path: 'test-results/desktop-assets.png' })
  await context.close()
})

test('desktop: assets stay on the left and the utility drawer opens on the right', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 860 } })
  await installFixture(context, [])
  const page = await context.newPage()
  await page.goto('/chat')

  const assets = page.getByRole('region', { name: '资产' })
  await expect(assets).toBeVisible()
  const assetsBox = await assets.boundingBox()
  expect(assetsBox).not.toBeNull()
  expect(assetsBox.x).toBeLessThan(40)

  await page.getByRole('button', { name: '打开导航和会话列表' }).click()
  const drawer = page.locator('#utility-sidebar')
  await expect(drawer).toBeVisible()
  const drawerBox = await drawer.boundingBox()
  expect(drawerBox).not.toBeNull()
  expect(drawerBox.x + drawerBox.width).toBeGreaterThan(1240)

  await drawer.getByRole('button', { name: '收藏' }).click()
  await expect(drawer.getByText('我的智能卡片')).toBeVisible()
  await drawer.getByRole('button', { name: '操作记录' }).click()
  await expect(drawer.getByText('最近的操作与审计记录')).toBeVisible()
  await page.screenshot({ path: 'test-results/desktop-utility-drawer.png' })
  await context.close()
})
