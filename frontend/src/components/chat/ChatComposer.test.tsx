// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { ChatComposer } from './ChatComposer'
import { findMention } from './mention'
import type { BankObjectReference } from '@/lib/bank-references'

afterEach(cleanup)

const catalog: BankObjectReference[] = [
  {kind:'account',id:1,label:'日常账户',detail:'**** 1001'},
  {kind:'card',id:2,label:'日常银行卡',detail:'**** 1001'},
  {kind:'contact',id:3,label:'张三',detail:'某银行 · 138****0001'},
]

function Demo({onSelected=vi.fn(),onSend=vi.fn(),search=vi.fn(async()=>catalog)}:{
  onSelected?:(item:BankObjectReference)=>void
  onSend?:()=>void
  search?:()=>Promise<BankObjectReference[]>
}) {
  const [value,setValue]=useState('')
  return <ChatComposer value={value} onChange={setValue} onSend={onSend}
    onReferenceDrop={onSelected} onSearchReferences={search}/>
}

it('仅识别光标前面的 @ 查询，不误删普通文本', () => {
  expect(findMention('看看 @张三',6)).toEqual({start:3,end:6,query:'张三'})
  expect(findMention('您好 hello',8)).toBeNull()
  expect(findMention('@张三 后续',6)).toBeNull()
  expect(findMention('你好 @',4)).toEqual({start:3,end:4,query:''})
})

it('键入 @张 后筛选联系人，Enter 插入引用并移除查询词，不发送消息', async () => {
  const user=userEvent.setup()
  const selected=vi.fn(),send=vi.fn(),search=vi.fn(async()=>catalog)
  render(<Demo onSelected={selected} onSend={send} search={search}/>)
  const input=screen.getByRole('textbox',{name:'输入消息'})
  await user.type(input,'请查询 @张')
  await screen.findByRole('option',{name:/张三/})
  expect(screen.queryByRole('option',{name:/日常账户/})).toBeNull()
  await user.keyboard('{Enter}')
  expect(selected).toHaveBeenCalledWith(catalog[2])
  expect(send).not.toHaveBeenCalled()
  await waitFor(()=>expect((input as HTMLTextAreaElement).value).toBe('请查询 '))
})

it('方向键选择不同账户及银行卡，Escape 可关闭菜单', async () => {
  const user=userEvent.setup()
  const selected=vi.fn()
  render(<Demo onSelected={selected}/>)
  const input=screen.getByRole('textbox',{name:'输入消息'})
  await user.type(input,'@')
  await screen.findByRole('option',{name:/日常账户/})
  await user.keyboard('{ArrowDown}{Enter}')
  expect(selected).toHaveBeenCalledWith(catalog[1])
  await user.type(input,'@')
  await screen.findByRole('listbox',{name:'选择金融对象'})
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.queryByRole('listbox')).toBeNull())
})

it('普通对话没有 @ 时不触发对象目录请求', async () => {
  const user=userEvent.setup()
  const search=vi.fn(async()=>catalog)
  render(<Demo search={search}/>)
  await user.type(screen.getByRole('textbox',{name:'输入消息'}),'你好，请查账单')
  expect(search).not.toHaveBeenCalled()
})

it('对象列表尚未加载时回车不会误发送 @ 指令', async () => {
  const user=userEvent.setup()
  const send=vi.fn()
  const pending=()=>new Promise<BankObjectReference[]>(()=>{})
  render(<Demo onSend={send} search={pending}/>)
  await user.type(screen.getByRole('textbox',{name:'输入消息'}),'我要问 @未加载')
  expect(await screen.findByRole('listbox',{name:'选择金融对象'})).toBeTruthy()
  await user.keyboard('{Enter}')
  expect(send).not.toHaveBeenCalled()
})
