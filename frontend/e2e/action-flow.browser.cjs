const {test,expect}=require('@playwright/test')
const created='2026-11-02T08:00:00Z', expiry='2030-01-01T00:00:00Z'
const transfer={type:'action_required',confirmation_token:'synthetic-confirmation',
 transfer_id:42,action:{id:3,action_type:'transfer',risk_level:'yellow',
 status:'pending',expires_at:expiry,details:{account_masked:'**** 8899',
 recipient_name:'模拟收款人',amount_fen:1250,currency:'CNY'}}}
const investment={type:'action_required',confirmation_token:'synthetic-verification',
 order_id:21,action:{id:8,action_type:'wealth_subscribe',risk_level:'red',
 status:'pending',expires_at:expiry,details:{order_type:'subscribe',product_id:2,
 product_name:'模拟理财',product_category:'固收',product_risk_level:'R2',
 expected_rate_bps:275,term_days:90,account_id:1,account_masked:'**** 5566',
 amount_fen:20000,note:'模拟',currency:'CNY'}}}
const sse=(v)=>'data: '+JSON.stringify(v)+'\n\n'
async function setup(context, event, disconnect=false, committedBeforeDisconnect=false){
 await context.addInitScript(()=>{
  localStorage.setItem('bank_agent.token','synthetic-browser-test')
  localStorage.setItem('bank_agent.user',JSON.stringify({id:1,username:'demo',display_name:'演示用户'}))
 })
 const observed={chat:0,confirmed:0,started:0,verified:0,executed:0,checked:0,status:'pending'}
 await context.route('**/api/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname,method=request.method()
  if(path==='/api/health')return route.fulfill({json:{status:'ok',app:'test',llm:{mode:'mock',model:'mock'}}})
  if(path==='/api/bank/dashboard')return route.fulfill({json:{accounts:[],contacts:[],holdings:[],risk_profile:null,generated_at:created}})
  if(path==='/api/cards')return route.fulfill({json:[]})
  if(path==='/api/chat/conversations'&&method==='GET')return route.fulfill({json:[{id:1,title:'模拟会话',created_at:created,updated_at:created}]})
  if(path==='/api/chat/conversations'&&method==='POST')return route.fulfill({status:201,json:{id:1,title:'模拟会话',created_at:created,updated_at:created}})
  if(path==='/api/chat/conversations/1/messages'&&method==='GET')return route.fulfill({json:[]})
  if(path==='/api/chat/conversations/1/messages'&&method==='POST'){
   observed.chat++
   return route.fulfill({status:200,headers:{'content-type':'text/event-stream'},
    body:sse(event)+sse({type:'done',message:{id:90,role:'assistant',content:'已生成待确认操作',created_at:created}})})
  }
  if(path==='/api/actions/'+event.action.id+'/confirm'&&method==='POST'){
   observed.confirmed++;observed.status='confirmed'
   return route.fulfill({json:{id:event.action.id,status:'confirmed',message:'已确认'}})
  }
  if(path==='/api/actions/'+event.action.id+'/verification/start'&&method==='POST'){
   observed.started++;return route.fulfill({json:{status:'pending',message:'已开始'}})
  }
  if(path==='/api/actions/'+event.action.id+'/verification/verify'&&method==='POST'){
   observed.verified++;observed.status='verified'
   return route.fulfill({json:{status:'verified',message:'已验证'}})
  }
  if(path==='/api/actions/'+event.action.id&&method==='GET'){
   observed.checked++;return route.fulfill({json:{id:event.action.id,action_type:event.action.action_type,expires_at:expiry,status:observed.status}})
  }
  if((path==='/api/transfers/42/execute'||path==='/api/wealth/orders/21/execute')&&method==='POST'){
   observed.executed++
   if(disconnect&&observed.executed===1){
    if(committedBeforeDisconnect)observed.status='completed'
    return route.abort('failed')
   }
   observed.status='completed'
   return route.fulfill({json:event.action.risk_level==='red'
    ? {order_id:21,order_type:'subscribe',status:'completed',transaction_id:51,
       balance_fen:480000,holding_fen:20000,message:'模拟理财操作已完成。'}
    : {status:'completed',message:'模拟转账已完成'}})
  }
  return route.fulfill({json:[]})
 })
 return observed
}

async function openAction(page){
 await page.goto('/chat')
 await expect(page.getByRole('heading',{name:'今天，想完成什么？'})).toBeVisible()
 const input=page.getByRole('textbox',{name:'输入消息'})
 await expect(input).toBeVisible()
 await input.fill('办理模拟操作')
 await expect(input).toHaveValue('办理模拟操作')
 const send=page.getByRole('button',{name:'发送'})
 await expect(send).toBeEnabled()
 await send.click()
 const dialog=page.getByRole('dialog')
 await expect(dialog).toBeVisible()
 return dialog
}
test('yellow: no execution before confirmation; recover after network loss using same action',async({browser})=>{
 const context=await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'})
 const calls=await setup(context,transfer,true),page=await context.newPage()
 const dialog=await openAction(page)
 expect(calls.executed).toBe(0)
 await dialog.getByRole('button',{name:'确认',exact:true}).click()
 await expect(dialog.getByText('已确认，操作尚未执行。')).toBeVisible()
 expect(calls.confirmed).toBe(1)
 expect(calls.executed).toBe(0)
 await dialog.getByRole('button',{name:'执行操作'}).click()
 await expect(dialog.getByText(/请求结果暂不确定/)).toBeVisible()
 expect(calls.executed).toBe(1)
 await expect(dialog.getByRole('button',{name:'查询服务端状态'})).toBeEnabled()
 await dialog.getByRole('button',{name:'查询服务端状态'}).click()
 await expect(dialog.getByRole('button',{name:'按原动作编号重试'})).toBeVisible()
 expect(calls.checked).toBe(1)
 expect(calls.executed).toBe(1)
 await dialog.getByRole('button',{name:'按原动作编号重试'}).click()
 await expect(dialog.getByText('模拟转账已完成')).toBeVisible()
 expect(calls.executed).toBe(2)
 expect(calls.chat).toBe(1)
 await context.close()
})
test('red: verification required, no operation until successful code; then exactly one execution',async({browser})=>{
 const context=await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'})
 const calls=await setup(context,investment),page=await context.newPage()
 const dialog=await openAction(page)
 await expect(dialog.getByText(/验证通过后会继续执行/)).toBeVisible()
 expect(calls.executed).toBe(0)
 await dialog.getByRole('button',{name:'开始模拟验证'}).click()
 await expect(dialog.getByRole('button',{name:'验证',exact:true})).toBeVisible()
 expect(calls.started).toBe(1)
 expect(calls.executed).toBe(0)
 await dialog.getByLabel('模拟验证码').fill('123456')
 await dialog.getByRole('button',{name:'验证',exact:true}).click()
 await expect(dialog.getByText('模拟理财操作已完成。')).toBeVisible()
 expect(calls.verified).toBe(1)
 expect(calls.executed).toBe(1)
 expect(calls.chat).toBe(1)
 await context.close()
})

test('yellow: lost successful response reconciles completed state without second execution',async({browser})=>{
 const context=await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'})
 const calls=await setup(context,transfer,true,true),page=await context.newPage()
 const dialog=await openAction(page)
 await dialog.getByRole('button',{name:'确认',exact:true}).click()
 await dialog.getByRole('button',{name:'执行操作'}).click()
 await expect(dialog.getByText(/请求结果暂不确定/)).toBeVisible()
 expect(calls.executed).toBe(1)
 await expect(dialog.getByRole('button',{name:'查询服务端状态'})).toBeEnabled()
 await dialog.getByRole('button',{name:'查询服务端状态'}).click()
 await expect(dialog.getByText(/服务端状态：已完成/)).toBeVisible()
 await expect(dialog.getByRole('button',{name:'按原动作编号重试'})).toHaveCount(0)
 expect(calls.checked).toBe(1)
 expect(calls.executed).toBe(1)
 await context.close()
})
