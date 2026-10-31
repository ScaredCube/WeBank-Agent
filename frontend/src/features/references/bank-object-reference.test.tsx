// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { addBankReference, composeReferenceContext, parseBankReference, parseDroppedReference, presentReferenceMessage } from './bank-object-reference'
import { ReferenceSource } from './ReferenceSource'
import { ChatComposer } from '@/components/chat/ChatComposer'

const account = {kind:'account' as const,id:1,label:'日常账户',detail:'****8899'}
const contact = {kind:'contact' as const,id:2,label:'小林',detail:'某银行'}
afterEach(cleanup)

it('引用最多五个且按类型与 ID 去重', () => {
  expect(addBankReference([account],account)).toHaveLength(1)
  expect(addBankReference([account],contact)).toHaveLength(2)
  const many = Array.from({length:7},(_,i)=>({...account,id:i+1}))
  expect(many.reduce(addBankReference,[] as typeof many)).toHaveLength(1)
  expect(addBankReference([account,contact],{...account,id:8}).map(item=>item.id)).toEqual([2,8])
  expect(addBankReference([account,contact],{...contact,id:7}).map(item=>item.id)).toEqual([1,7])
})

it('任意外部拖拽内容不会被当作可信对象引用', () => {
  expect(parseBankReference({kind:'admin',id:1,label:'a',detail:'b'})).toBeNull()
  expect(parseDroppedReference('{"kind":"account","id":-2,"label":"x","detail":"y"}')).toBeNull()
  expect(parseDroppedReference('<script>alert(1)</script>')).toBeNull()
  expect(parseDroppedReference(JSON.stringify(account))).toEqual(account)
})

it('发给 Agent 的引用属于普通用户文本，明确要求服务端核实', () => {
  const content = composeReferenceContext('帮我看看账单',[account,contact])
  expect(content).not.toContain('账户：日常账户')
  expect(content).not.toContain('联系人：小林')
  expect(content).toBe('帮我看看账单')
  expect(composeReferenceContext('分析持仓',[{kind:'holding',id:3,label:'稳健理财',detail:'R2'}])).toContain('不是授权令牌')
  expect(presentReferenceMessage(content)).toEqual({text:'帮我看看账单',objects:[]})
  expect(presentReferenceMessage('查消费\n\n[已引用对象：账户：日常账户 · ****8899；联系人：小林 · 某银行]')).toEqual({text:'查消费',objects:['账户：日常账户 · ****8899','联系人：小林 · 某银行']})
  expect(presentReferenceMessage('查消费\n\n[已引用账户：日常账户 · ****8899]')).toEqual({text:'查消费',objects:['账户：日常账户 · ****8899']})
  expect(presentReferenceMessage('普通问题')).toEqual({text:'普通问题',objects:[]})
})

it('通过点击引用与删除胶囊，不依赖拖拽完成操作', () => {
  const onReference = vi.fn()
  const remove = vi.fn()
  render(<><ReferenceSource reference={account} onReference={onReference}><div>日常账户对象</div></ReferenceSource>
    <ChatComposer value="分析消费" onChange={() => {}} onSend={() => {}} references={[account]}
      onReferenceDrop={() => {}} onRemoveReference={remove}/></>)
  fireEvent.click(screen.getByRole('button',{name:'引用到对话：日常账户'}))
  expect(onReference).toHaveBeenCalledWith(account)
  expect(screen.getByLabelText('已引用的金融对象')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'移除引用：日常账户'}))
  expect(remove).toHaveBeenCalledWith(account)
})
