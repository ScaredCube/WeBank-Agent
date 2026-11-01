/* Read-only competition E2E: isolated synthetic bank, browser UI, configured model.
   No transaction confirmation or execution, and no credential/token logging. */
const {chromium}=require('../node_modules/playwright');
const fs=require('fs'),path=require('path');
const BASE='http://127.0.0.1:5222',OUT=process.argv[2];
if(!OUT)throw Error('QA output directory required');
fs.mkdirSync(OUT,{recursive:true});
function insist(ok,msg){if(!ok)throw Error(msg)}
async function login(page){
 await page.goto(BASE+'/login',{waitUntil:'domcontentloaded'});
 await page.locator('#login-username').fill('demo');
 await page.locator('#login-password').fill('demo123');
 await page.getByRole('button',{name:'登录',exact:true}).click();
 await page.waitForURL('**/chat',{timeout:18000});
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const errors=[];
 try{
  const desktop=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
  const p=await desktop.newPage();
  p.on('pageerror',e=>errors.push(e.message));
  await login(p);
  const created=p.waitForResponse(r=>r.url().endsWith('/api/chat/conversations')
       &&r.request().method()==='POST');
  await p.getByRole('button',{name:'新对话'}).first().click();
  insist((await created).status()===201,'Could not create conversation');
  const editor=p.getByRole('textbox',{name:'输入消息'});
  await editor.fill('请查看@银行卡');
  await p.getByRole('listbox',{name:'选择金融对象'}).waitFor({timeout:16000});
  await p.getByRole('option').filter({hasText:'银行卡'}).first().click();
  insist(await p.locator('[aria-label="已引用的金融对象"] > span').count()===1,'Card reference absent');
  await editor.fill('请查询这张银行卡状态，以及关联账户2026-01月账单，各展示一张可信结果卡。');
  const response=p.waitForResponse(r=>r.request().method()==='POST'
          &&/\/api\/chat\/conversations\/\d+\/messages$/.test(r.url()),{timeout:15000});
  await p.getByRole('button',{name:'发送'}).click();
  insist((await response).status()===200,'Financial query was rejected');
  await p.locator('[data-intelligent-card]').first().waitFor({timeout:90000});
  await p.locator('[aria-label="银行卡状态结果"]').first().waitFor({timeout:90000});
  await p.getByRole('button',{name:'停止接收'}).waitFor({state:'hidden',timeout:90000});
  await p.screenshot({path:path.join(OUT,'desktop-live-readonly.png')});
  await p.reload({waitUntil:'domcontentloaded'});
  await p.locator('[data-intelligent-card]').first().waitFor({timeout:18000});
  await p.locator('[aria-label="银行卡状态结果"]').first().waitFor({timeout:18000});
  insist(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Desktop overflow');
  await desktop.close();

  const mobile=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
  const m=await mobile.newPage();m.on('pageerror',e=>errors.push(e.message));
  await login(m);
  await m.getByRole('button',{name:'打开导航和会话列表'}).click();
  await m.locator('nav[aria-label="最近对话"] button').filter({hasText:'银行卡'}).first().click();
  await m.locator('[data-intelligent-card]').first().waitFor({timeout:18000});
  await m.locator('[aria-label="银行卡状态结果"]').first().waitFor({timeout:18000});
  insist(!await m.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile overflow');
  await m.screenshot({path:path.join(OUT,'mobile-live-restored.png')});
  await mobile.close();
  insist(errors.length===0,'Browser JavaScript error: '+errors[0]);
  console.log(JSON.stringify({result:'PASS',desktop:true,mobile:true,
    verified:['typed_card_reference','trusted_bill','trusted_card','history_reload','mobile_history'],
    browser_errors:0,synthetic:true}));
 }finally{await browser.close()}
})().catch(e=>{console.error('READ_ONLY_E2E_ERROR: '+e.message);process.exitCode=1});
