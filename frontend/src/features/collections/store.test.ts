import 'fake-indexeddb/auto'
import { describe, expect, it } from 'vitest'
import { clearSnapshots, listSnapshots, saveSnapshot, deleteSnapshot, refreshSnapshot } from './store'

const card = { version: 1, id: 'bill-2026', title: '账单', source: '账户 ****1234', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'text', text: '消费' }] }

describe('本地卡片快照', () => {
  it('保存经过验证的刷新规范，按用户隔离并更新卡片内容', async () => {
    const saved = await saveSnapshot(2201, card, undefined, { conversationId: 3, messageId: 11 },
      { kind: 'monthly_bill', month: '2026-01', accountId: 7 })
    expect((await listSnapshots(2201))[0].refresh).toEqual({ kind: 'monthly_bill', month: '2026-01', accountId: 7 })
    await expect(refreshSnapshot(2202, saved.id, { ...card, title: '伪造更新' })).rejects.toThrow()
    const updated = await refreshSnapshot(2201, saved.id, { ...card, title: '新账单', blocks: [{ type: 'text', text: '已更新' }] })
    expect(updated.card).toMatchObject({ title: '新账单', origin: { conversationId: 3, messageId: 11 } })
    expect((await listSnapshots(2201))[0].card).toMatchObject({ title: '新账单' })
    expect(updated.savedAt).toBe(saved.savedAt)
  })
  it('非法刷新来源或卡片无法替换旧收藏', async () => {
    await expect(saveSnapshot(2203, card, undefined, undefined,
      { kind: 'monthly_bill', month: '2026-99', accountId: 7 })).rejects.toThrow()
    const saved = await saveSnapshot(2203, card, undefined, undefined, { kind: 'monthly_bill', month: '2026-01', accountId: 1 })
    await expect(refreshSnapshot(2203, saved.id, { version: 99 })).rejects.toThrow()
    expect((await listSnapshots(2203))[0].card).toMatchObject({ title: '账单' })
  })

  it('合成预览和真实收藏使用独立数据库', async () => {
    const saved = await saveSnapshot(1100, card, 'webank-ui-preview-test')
    expect((await listSnapshots(1100, 'webank-ui-preview-test')).some((item) => item.id === saved.id)).toBe(true)
    expect((await listSnapshots(1100)).some((item) => item.id === saved.id)).toBe(false)
    await clearSnapshots(1100, 'webank-ui-preview-test')
  })
  it('按用户隔离并支持删除', async () => {
    const saved = await saveSnapshot(1001, card)
    expect((await listSnapshots(1001)).some((item) => item.id === saved.id)).toBe(true)
    expect((await listSnapshots(1002)).some((item) => item.id === saved.id)).toBe(false)
    await deleteSnapshot(1001, saved.id)
    expect((await listSnapshots(1001)).some((item) => item.id === saved.id)).toBe(false)
  })

  it('保存时剔除额外字段并遮盖敏感字符串', async () => {
    const saved = await saveSnapshot(1003, { ...card, confirmation_token: 'secret', source: '手机号 13812345678', blocks: [{ type: 'text', text: '联系 13812345678 <PHONE_TMP_SECRET>' }] })
    const result = JSON.stringify(saved)
    expect(result).not.toContain('secret')
    expect(result).not.toContain('13812345678')
    expect(result).not.toContain('PHONE_TMP_SECRET')
  })

  it('拒绝未知组件而不写入', async () => {
    await expect(saveSnapshot(1004, { ...card, blocks: [{ type: 'script', code: 'x' }] })).rejects.toThrow()
    expect(await listSnapshots(1004)).toEqual([])
  })

  it('收藏快照不保存导航或其他可执行入口', async () => {
    const saved = await saveSnapshot(1008, { ...card, blocks: [...card.blocks, { type: 'action', action: 'open_assets' }] })
    expect(JSON.stringify(saved)).not.toContain('open_assets')
    expect(JSON.stringify(saved)).toContain('消费')
  })

  it('忽略卡片自行声明的来源，仅保存调用方提供的已校验引用', async () => {
    const saved = await saveSnapshot(1011, { ...card, origin: { conversationId: 99, messageId: 88 } }, undefined, { conversationId: 2, messageId: 7 })
    expect(saved.card).toMatchObject({ origin: { conversationId: 2, messageId: 7 } })
    const untrusted = await saveSnapshot(1011, { ...card, origin: { conversationId: 99, messageId: 88 } })
    expect(untrusted.card).not.toHaveProperty('origin')
    await expect(saveSnapshot(1011, card, undefined, { conversationId: -1, messageId: 7 })).rejects.toThrow()
  })

  it('月账单的脱敏账户来源保留在快照中，但没有会话来源时不补造跳转引用', async () => {
    const billSource = '测试账户 · ****1234 · 北京时间自然月 · 账户现金流口径'
    const saved = await saveSnapshot(1012, { ...card, title: '2026-01 账单', source: billSource, origin: { conversationId: 9, messageId: 10 } })

    expect(saved.card).toMatchObject({ title: '2026-01 账单', source: billSource })
    expect(saved.card).not.toHaveProperty('origin')
  })

  it('图表快照保留数值并处理标签中的敏感信息', async () => {
    const saved = await saveSnapshot(1009, { ...card, blocks: [{ type: 'bar_chart', title: '分类', rows: [{ label: '13812345678', value: 100 }] }] })
    expect(JSON.stringify(saved)).not.toContain('13812345678')
    expect(JSON.stringify(saved)).toContain('100')
  })

  it('分组快照移除内部动作并保留数据', async () => {
    const saved = await saveSnapshot(1010, { ...card, blocks: [{ type: 'group', layout: 'columns', blocks: [{ type: 'text', text: '消费' }, { type: 'action', action: 'open_assets' }] }] })
    expect(JSON.stringify(saved)).not.toContain('open_assets')
    expect(JSON.stringify(saved)).toContain('消费')
  })

  it('损坏的记录不会阻断其他记录，且仍可删除', async () => {
    const good = await saveSnapshot(1005, card)
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('webank-ui-snapshots', 1)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction('snapshots', 'readwrite')
      transaction.objectStore('snapshots').put({ key: '1005:broken', userId: 1005, id: 'broken', savedAt: null, card: { version: 99 } })
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error)
    })
    database.close()
    const rows = await listSnapshots(1005)
    expect(rows.some((item) => item.id === good.id)).toBe(true)
    expect(rows.some((item) => item.id === 'broken')).toBe(true)
    expect(rows.find((item) => item.id === 'broken')?.savedAt).toBe('')
    await deleteSnapshot(1005, 'broken')
    expect((await listSnapshots(1005)).some((item) => item.id === 'broken')).toBe(false)
  })

  it('清空当前用户收藏不会删除其他用户的收藏', async () => {
    await saveSnapshot(1006, card)
    const other = await saveSnapshot(1007, card)
    await clearSnapshots(1006)
    expect(await listSnapshots(1006)).toEqual([])
    expect((await listSnapshots(1007)).some((item) => item.id === other.id)).toBe(true)
  })
})
