const { test, expect } = require('@playwright/test')

const now = '2026-11-02T10:00:00Z'
const base = '/api/chat/conversations/1'
const message = {id:51,role:'assistant',content:'已取得可信账单数据（部分结果）',created_at:now,
  bill_result:{month:'2026-10',account_name:'模拟活期',masked_number:'****1234',
    currency:'CNY',consumption_fen:12300}}
const scenarios = [
  {state:'failed', alert:'可信部分结果已保存到历史', cleared:true},
  {state:'interrupted', alert:'可信部分结果已保存在历史中', cleared:false},
  {state:'completed', alert:'上一条请求已完成', cleared:true},
  {state:'action_pending', alert:'不会再次执行或下发确认令牌', cleared:true},
]

async function fixture(context, scenario) {
  await context.addInitScript(() => {
    localStorage.setItem('bank_agent.token','browser-test-token')
    localStorage.setItem('bank_agent.user',JSON.stringify({id:1,username:'demo',display_name:'演示用户'}))
  })
  const observed = {posts:[], statusGets:0}
  await context.route('**/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (path==='/api/health') return route.fulfill({json:{status:'ok',app:'e2e',llm:{mode:'mock',model:'mock'}}})
    if (path==='/api/bank/dashboard') return route.fulfill({json:{accounts:[],contacts:[],holdings:[],risk_profile:null,generated_at:now}})
    if (path==='/api/cards') return route.fulfill({json:[]})
    if (path==='/api/chat/conversations' && req.method()==='GET')
      return route.fulfill({json:[{id:1,title:'恢复演示',created_at:now,updated_at:now}]})
    if (path===base+'/messages' && req.method()==='GET')
      return route.fulfill({json:observed.posts.length>0
        ? [{id:50,role:'user',content:'分析账单',created_at:now}, ...(scenario.state==='action_pending'?[]:[message])]
        : []})
    if (path===base+'/messages' && req.method()==='POST') {
      observed.posts.push(JSON.parse(req.postData()||'{}'))
      return route.abort('failed') // actual Chromium fetch network failure
    }
    if (path.startsWith(base+'/requests/') && req.method()==='GET') {
      observed.statusGets++
      if (observed.statusGets===1) return route.fulfill({status:503,json:{detail:'临时断网，无法核对状态'}})
      const state=scenario.state
      return route.fulfill({json:{
        request_id:path.split('/').pop(),state,user_message_id:50,
        pending_action_id:state==='action_pending'?88:null,
        message:state==='completed'?message:null,
        partial_message:state==='failed'||state==='interrupted'?message:null,
      }})
    }
    return route.fulfill({json:[]})
  })
  return observed
}

for(const scenario of scenarios) {
  test('Chrome refresh recovery: '+scenario.state+' never repeats a bank request',async({browser})=>{
    const context=await browser.newContext({viewport:{width:1360,height:860},reducedMotion:'reduce'})
    const observed=await fixture(context,scenario)
    const page=await context.newPage()
    const errors=[]
    page.on('pageerror',err=>errors.push(err.message))
    await page.goto('/chat')
    const input=page.getByRole('textbox',{name:'输入消息'})
    await expect(input).toBeVisible()
    await input.fill('分析账单')
    await page.getByRole('button',{name:'发送'}).click()
    await expect.poll(()=>observed.posts.length).toBe(1)
    await expect.poll(()=>observed.statusGets).toBeGreaterThanOrEqual(1)
    const requestId=observed.posts[0].request_id
    expect(requestId).toMatch(/^[0-9a-f-]{36}$/i)
    await expect.poll(()=>page.evaluate(id=>
      JSON.parse(sessionStorage.getItem('xiaowe:chat-inflight:v1')||'[]').some(x=>x.requestId===id)
    ,requestId)).toBe(true)
    await page.reload() // rehydrate actual React app with same sessionStorage
    await expect.poll(()=>observed.statusGets).toBeGreaterThanOrEqual(2)
    await expect(page.getByRole('alert').filter({hasText:scenario.alert})).toBeVisible()
    expect(observed.posts).toHaveLength(1)
    if(scenario.state!=='action_pending') {
      await expect(page.getByText('已取得可信账单数据（部分结果）')).toBeVisible()
    }
    await expect.poll(()=>page.evaluate((id)=>
      JSON.parse(sessionStorage.getItem('xiaowe:chat-inflight:v1')||'[]').some(x=>x.requestId===id)
    ,requestId)).toBe(!scenario.cleared)
    expect(errors).toEqual([])
    await context.close()
  })
}
