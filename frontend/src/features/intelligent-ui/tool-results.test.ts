import { expect, it } from 'vitest'
import { messageToolResults } from './tool-results'
import type { Message } from '@/lib/api'

const base = {id:42,role:'assistant' as const,content:'完成',created_at:'2026-01-01T00:00:00Z'}
it('返回来源顺序一致的多张金融结果，且不重复兼容字段',()=>{
 const message:Message={...base,tool_results:[
   {kind:'card_status',data:{cards:[]}},
   {kind:'monthly_bill',data:{month:'2026-01'}},
 ],card_result:{cards:[{card_id:99}]}}
 expect(messageToolResults(message).map(x=>x.kind)).toEqual(['card_status','monthly_bill'])
})
it('会话历史中的可信内部转账回执可以恢复，不依赖临时 SSE 状态',()=>{
 const receipt = {
  transfer_id:12,status:'completed',amount_fen:50000,note:'',
  source_name:'日常账户',source_masked:'**** 0011',
  target_name:'备用账户',target_masked:'**** 0022',
  balance_fen:450000,currency:'CNY',transaction_id:21,
 }
 const message: Message = {...base,tool_results:[{kind:'internal_transfer',data:receipt}]}
 expect(messageToolResults(message)).toEqual([{kind:'internal_transfer',data:receipt}])
})

it('旧消息继续还原单卡或账单',()=>{
 expect(messageToolResults({...base,bill_result:{month:'2026-01'}})).toEqual([
   {kind:'monthly_bill',data:{month:'2026-01'}}])
})
it('未知类型和超量数据不被呈现',()=>{
 const fake={kind:'transfer_completed',data:{status:'completed'}}
 expect(messageToolResults({...base,tool_results:[fake]})).toEqual([])
 expect(messageToolResults({...base,tool_results:Array(9).fill({kind:'card_status',data:{cards:[]}})})).toEqual([])
})
