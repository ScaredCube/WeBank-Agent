/* Isolated browser QA for a simulated bank. Credentials and tokens are never logged. */
const {chromium}=require('../node_modules/playwright')
const BASE='http://127.0.0.1:5222'
function requireTrue(condition, reason){if(!condition) throw Error(reason)}
async function login(page){
 await page.goto(BASE+'/login',{waitUntil:'domcontentloaded'})
 await page.locator('#login-username').fill('demo')
 await page.locator('#login-password').fill('demo123')
 await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.waitForURL('**/chat',{timeout:20000})
}
async function run(){
 const browser=await chromium.launch({channel:'chrome',headless:true})
 const errors=[]
 try{
  const context=await browser.newContext({viewport:{width:1365,height:850},reducedMotion:'reduce'})
  const page=await context.newPage()
  page.on('pageerror',e=>errors.push(e.message))
  await login(page)
  // The new home creates its conversation lazily on first message send.
  // Do not click the new-chat button or wait for a premature POST.
  const input=page.getByRole('textbox',{name:'输入消息'})
  await input.fill('@')
  const suggestions=page.getByRole('listbox',{name:'选择金融对象'})
  await suggestions.waitFor({timeout:16000})
  await suggestions.getByRole('option').filter({hasText:'演示活期账户'}).first().click()
  const selected=page.locator('[aria-label="已引用的金融对象"]')
  await selected.waitFor({timeout:10000})
  requireTrue((await selected.innerText()).includes('演示活期账户'),'Source account not referenced')
  await input.fill('从所引用的演示活期账户向模拟收款人 13812345678 转账1元。请只准备模拟转账，待我在网页核对并执行，备注留空。')
  const originalRequest=await input.inputValue()
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&/\/api\/chat\/conversations\/\d+\/messages$/.test(r.url()),{timeout:16000})
  await page.getByRole('button',{name:'发送'}).click()
  requireTrue((await response).status()===200,'Agent message was rejected')
  await page.getByRole('button',{name:'停止接收'}).waitFor({state:'hidden',timeout:90000})
  const dialog=page.getByRole('dialog')
  await dialog.waitFor({timeout:25000})
  const title=await dialog.getByRole('heading').first().innerText()
  requireTrue(title.includes('转账'),'Agent produced an unexpected operation type')
  requireTrue((await dialog.innerText()).includes('¥1.00'),'Original amount incorrect')
  const cancelResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/cancel'),{timeout:16000})
  await dialog.getByRole('button',{name:'修改信息'}).click()
  requireTrue((await cancelResponse).status()===200,'Original action cancel failed')
  await dialog.waitFor({state:'hidden',timeout:13000})
  requireTrue((await input.inputValue()).includes('转账1元'),'Original draft not restored')
  requireTrue((await selected.innerText()).includes('演示活期账户'),'Original account reference missing')
  await input.fill(originalRequest.replace('转账1元','转账2元'))
  const editedResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/messages'),{timeout:16000})
  await page.getByRole('button',{name:'发送'}).click()
  requireTrue((await editedResponse).status()===200,'Edited Agent request rejected')
  await page.getByRole('button',{name:'停止接收'}).waitFor({state:'hidden',timeout:90000})
  await dialog.waitFor({timeout:25000})
  requireTrue((await dialog.innerText()).includes('¥2.00'),'Edited amount missing from new action')
  await dialog.getByRole('button',{name:'确认',exact:true}).click()
  await dialog.getByText('已确认，操作尚未执行。').waitFor({timeout:15000})
  const execution=page.waitForResponse(r=>r.request().method()==='POST'&&/\/api\/transfers\/\d+\/execute$/.test(r.url()))
  await dialog.getByRole('button',{name:'执行操作'}).click()
  const completed=await execution
  requireTrue(completed.status()===200,'Execution HTTP did not succeed')
  const firstResult=await completed.json()
  await dialog.getByText('模拟转账已完成').waitFor({timeout:25000})
  requireTrue(errors.length===0,'Browser error')
  console.log(JSON.stringify({result:'PASS',synthetic:true,
    selected_account:true,verified_tool:true,
    confirmed_by_user:true,executed_by_user:true,browser_errors:0}))
  await context.close()
 }finally{await browser.close()}
}
run().catch(e=>{console.error('ACTION_E2E_FAIL: '+e.message);process.exitCode=1})
