// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { useConversationScroll } from './useConversationScroll'
import type { Message } from '@/lib/api'

const message = (id:number):Message => ({id,role:'user',content:'历史消息',created_at:''})
function Harness({ messages, loading }: {messages:Message[],loading:boolean}) {
  const {scrollRef,onScroll,resetScroll}=useConversationScroll(messages,'',false,loading)
  return <><div role="log" ref={scrollRef} onScroll={onScroll}/><button onClick={() => resetScroll('top')}>打开历史</button><button onClick={() => resetScroll()}>发送消息</button></>
}
afterEach(cleanup)

it('打开已有会话从第一条开始，而非自动滚动到末尾', () => {
  const view=render(<Harness messages={[]} loading />)
  const log=view.getByRole('log')
  Object.defineProperty(log,'scrollHeight',{configurable:true,value:1200})
  Object.defineProperty(log,'clientHeight',{configurable:true,value:400})
  log.scrollTop=450
  fireEvent.click(view.getByRole('button',{name:'打开历史'}))
  view.rerender(<Harness messages={[message(10),message(11)]} loading={false}/>)
  expect(log.scrollTop).toBe(0)
  log.scrollTop=120
  fireEvent.scroll(log)
  fireEvent.click(view.getByRole('button',{name:'打开历史'}))
  view.rerender(<Harness messages={[message(20),message(21)]} loading={false}/>)
  expect(log.scrollTop).toBe(0)
})

it('正常发送仍可自动跟随最新回复', () => {
  const view=render(<Harness messages={[message(1)]} loading={false}/>)
  const log=view.getByRole('log')
  Object.defineProperty(log,'scrollHeight',{configurable:true,value:1200})
  Object.defineProperty(log,'clientHeight',{configurable:true,value:400})
  fireEvent.click(view.getByRole('button',{name:'发送消息'}))
  view.rerender(<Harness messages={[message(1),message(2)]} loading={false}/>)
  expect(log.scrollTop).toBe(1200)
})
