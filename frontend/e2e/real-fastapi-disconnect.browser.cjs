const { test, expect } = require('@playwright/test')
test.skip(!process.env.XIAOWE_REAL_FASTAPI_E2E, 'Requires the local synthetic FastAPI fixture on 8193 and Vite proxy on 5187')

const root = 'http://127.0.0.1:5187'
const fixtureMetrics = 'http://127.0.0.1:8193/__e2e/sse-fixture-status'

test('real Chrome + FastAPI SSE: bank bill survives browser reload without duplicate tool',async({browser})=>{
  const context = await browser.newContext({viewport:{width:1360,height:860},reducedMotion:'reduce'})
  const login = await context.request.post(root+'/api/auth/login',{
    data:{username:'demo',password:'demo123'}
  })
  expect(login.status()).toBe(200)
  const {access_token,user}=await login.json()
  const auth={Authorization:'Bearer '+access_token}
  await context.addInitScript(({access_token,user})=>{
    localStorage.setItem('bank_agent.token',access_token)
    localStorage.setItem('bank_agent.user',JSON.stringify(user))
  },{access_token,user})

  const beforeMetrics=await (await context.request.get(fixtureMetrics)).json(); const page=await context.newPage()
  const errors=[]
  page.on('pageerror',error=>errors.push(error.message))
  await page.goto(root+'/chat')
  const editor=page.getByRole('textbox',{name:'输入消息'})
  await expect(editor).toBeVisible()
  await editor.fill('查询2026-10的月度账单')
  await page.getByRole('button',{name:'发送'}).click()
  let requestId
  await expect.poll(async()=> {
    const ids=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('xiaowe:chat-inflight:v1')||'[]'))
    requestId=ids[0]?.requestId
    return !!requestId
  }).toBe(true)
  expect(requestId).toMatch(/^[0-9a-f-]{36}$/i)
  const entries=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('xiaowe:chat-inflight:v1')||'[]'))
  expect(entries).toHaveLength(1)
  const cid=entries[0].conversationId
  expect(cid).toBeGreaterThan(0)

  await expect.poll(async()=>{
    const result=await context.request.get(fixtureMetrics)
    return (await result.json()).read_bill_event_count - beforeMetrics.read_bill_event_count
  },{timeout:15000}).toBeGreaterThanOrEqual(1)
  // Disconnect the actual Chromium fetch while FastAPI is paused after
  // yielding the authenticated bill, before the assistant has completed.
  await page.reload()
  await expect.poll(async()=>{
    const status=await context.request.get(root+'/api/chat/conversations/'+cid+'/requests/'+requestId,{headers:auth})
    const body=await status.json()
    return body.state
  },{timeout:14000}).toBe('interrupted')
  const statusResult=await context.request.get(root+'/api/chat/conversations/'+cid+'/requests/'+requestId,{headers:auth})
  expect(statusResult.status()).toBe(200)
  const status=await statusResult.json()
  expect(status.state).toBe('interrupted')
  expect(status.message).toBe(null)
  expect(status.partial_message?.bill_result?.month).toBe('2026-10')
  expect(status.partial_message?.bill_result?.currency).toBe('CNY')
  expect(status.partial_message?.content).toBeTruthy()

  const hist=await context.request.get(root+'/api/chat/conversations/'+cid+'/messages',{headers:auth})
  expect(hist.status()).toBe(200)
  const rows=await hist.json()
  expect(rows.filter(x=>x.id===status.partial_message.id && x.role==='assistant' && x.bill_result?.month==='2026-10')).toHaveLength(1)

  // Matching request IDs are never re-run after disconnect.
  const replay=await context.request.post(root+'/api/chat/conversations/'+cid+'/messages',{
    headers:auth,data:{content:'查询2026-10的月度账单',request_id:requestId}
  })
  expect(replay.status()).toBe(409)
  const observed=await (await context.request.get(fixtureMetrics)).json()
  expect(observed.agent_turn_count - beforeMetrics.agent_turn_count).toBe(1)
  await expect(page.getByText('可信部分结果', {exact:false}).first()).toBeVisible()
  expect(errors).toEqual([])
  await context.close()
})
