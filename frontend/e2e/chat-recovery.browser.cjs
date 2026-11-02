const { test, expect } = require('@playwright/test')

const now = '2026-11-02T08:00:00Z'
const base = '/api/chat/conversations/1'
const blankDashboard = {
  accounts: [], contacts: [], holdings: [], risk_profile: null, generated_at: now,
}

async function fakeBank(context, state, config = {}) {
  // The browser runs the real UI, with simulated HTTP responses to exercise
  // actual fetch/SSE, user controls and persisted request identity.
  await context.addInitScript(() => {
    localStorage.setItem('bank_agent.token', 'synthetic-browser-token')
    localStorage.setItem('bank_agent.user', JSON.stringify({
      id: 1, username: 'demo', display_name: '演示用户',
    }))
  })
  const observed = { posts: [], statuses: 0 }
  await context.route('**/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const endpoint = url.pathname
    const method = req.method()
    if (endpoint === '/api/health') {
      return route.fulfill({json: {status:'ok',app:'e2e',llm:{mode:'mock',model:'mock'}}})
    }
    if (endpoint === '/api/bank/dashboard') return route.fulfill({json: blankDashboard})
    if (endpoint === '/api/cards') return route.fulfill({json: []})
    if (endpoint === '/api/chat/conversations' && method === 'GET') {
      return route.fulfill({json:[{id:1,title:'模拟会话',created_at:now,updated_at:now}]})
    }
    if (endpoint === '/api/chat/conversations' && method === 'POST') {
      return route.fulfill({status:201,json:{id:1,title:'模拟会话',created_at:now,updated_at:now}})
    }
    if (endpoint === base + '/messages' && method === 'GET') {
      return route.fulfill({json: []})
    }
    if (endpoint === base + '/messages' && method === 'POST') {
      observed.posts.push(JSON.parse(req.postData() || '{}'))
      if (observed.posts.length === 1) return route.abort('failed')
      return route.fulfill({
        status:200, headers:{'content-type':'text/event-stream','cache-control':'no-store'},
        body:'data: {"type":"done","message":{"id":100,"role":"assistant","content":"模拟查询完成","created_at":"2026-11-02T08:00:00Z"}}\n\n',
      })
    }
    if (endpoint.startsWith(base + '/requests/') && method === 'GET') {
      observed.statuses += 1
      if (config.initialStatusError && observed.statuses === 1) {
        return route.fulfill({status:503,json:{detail:'暂时无法核对'}})
      }
      return route.fulfill({json:{
        request_id:endpoint.split('/').pop(),state,
        user_message_id:state==='failed'?42:17,
        pending_action_id:state==='action_pending'?91:null,
        message:state==='completed'
          ? {id:100,role:'assistant',content:'模拟查询完成',created_at:now}
          : null,
      }})
    }
    return route.fulfill({json: []})
  })
  return observed
}

async function openChat(page) {
  await page.goto('/chat')
  await expect(page.getByRole('textbox',{name:'输入消息'})).toBeVisible()
  await page.getByRole('textbox',{name:'输入消息'}).fill('查询最近交易')
  await page.getByRole('button',{name:'发送'}).click()
  await expect(page.getByRole('textbox',{name:'输入消息'})).toHaveValue('查询最近交易')
  await expect(page.getByRole('button',{name:'发送'})).toBeEnabled()
}

test('browser: failed submission requires an explicit second click before a new request ID', async ({browser}) => {
  const context = await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'})
  const observed = await fakeBank(context, 'failed')
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await openChat(page)
  expect(observed.posts).toHaveLength(1)
  const initialId = observed.posts[0].request_id
  expect(initialId).toMatch(/^[0-9a-f-]{36}$/i)
  await page.getByRole('button',{name:'发送'}).click()
  await expect(page.getByRole('alert').filter({hasText:'无法据此排除'})).toBeVisible()
  expect(observed.posts).toHaveLength(1)
  expect(observed.statuses).toBeGreaterThan(1)
  await expect(page.getByRole('textbox',{name:'输入消息'})).toHaveValue('查询最近交易')

  // The actual USER chooses whether to send a new request after inspecting
  // the warning. This is intentionally not a background automatic retry.
  await page.getByRole('button',{name:'发送'}).click()
  await expect.poll(() => observed.posts.length).toBe(2)
  expect(observed.posts[1].request_id).not.toBe(initialId)
  expect(errors).toEqual([])
  await context.close()
})

for (const state of ['processing','interrupted','action_pending','completed']) {
  test('browser: ' + state + ' blocks duplicate request POST', async ({browser}) => {
    const context = await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'})
    const observed = await fakeBank(context, state, {initialStatusError:true})
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await openChat(page)
    expect(observed.posts).toHaveLength(1)
    await page.getByRole('button',{name:'发送'}).click()
    await expect.poll(() => observed.statuses).toBeGreaterThanOrEqual(2)
    expect(observed.posts).toHaveLength(1)
    if (state === 'processing' || state === 'interrupted') {
      await expect(page.getByRole('textbox',{name:'输入消息'})).toHaveValue('查询最近交易')
      await expect(page.getByRole('alert').filter({hasText:'不能安全重复执行'})).toBeVisible()
    }
    if (state === 'action_pending') {
      await expect(page.getByRole('alert').filter({hasText:'确认令牌'})).toBeVisible()
    }
    if (state === 'completed') {
      await expect(page.getByRole('alert').filter({hasText:'不会再次调用 Agent'})).toBeVisible()
    }
    expect(errors).toEqual([])
    await context.close()
  })
}
