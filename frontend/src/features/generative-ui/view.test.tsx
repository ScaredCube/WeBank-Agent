// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import fixture from '../../../../fixtures/generative-ui/v1.json'
import { parseView } from './view'
import { ViewRenderer } from './ViewRenderer'
import { ViewPanel } from './ViewPanel'
import { api, ApiError } from '@/lib/api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
describe('可信视图', () => {
  it('Composer 只生成指标布局时，仍保留可信分类选择入口', async () => {
    const raw = structuredClone(fixture)
    raw.spec.elements.root.children = ['total']
    delete (raw.spec.elements as Partial<typeof raw.spec.elements>).categories
    const view = parseView(raw)!
    expect(view).not.toBeNull()
    const updated = structuredClone(raw)
    updated.revision = 2
    Object.assign(updated.interaction_state, { selected_category: '餐饮' })
    const write = vi.spyOn(api, 'viewInteraction').mockResolvedValue(updated)
    const onChange = vi.fn()
    render(<ViewPanel view={view} token="test" hidden={false} onChange={onChange}
      onClose={() => {}} onFollow={() => {}} onSource={() => {}} />)
    expect(screen.getByRole('region', {name:'消费分类选择'})).toBeTruthy()
    fireEvent.click(screen.getByRole('button', {name:'餐饮'}))
    await waitFor(() => expect(write).toHaveBeenCalledWith('test', view.view_id, 1, 'select_category', '餐饮'))
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1))
    expect(onChange.mock.calls[0][0].interaction_state.selected_category).toBe('餐饮')
    expect(screen.queryByRole('alert')).toBeNull()
  })
  it('分类选择始终由工作区统一管理，隐藏金额时也隐藏分类', () => {
    const view = parseView(fixture)!
    const { rerender } = render(<ViewPanel view={view} token="test" hidden={false}
      onChange={() => {}} onClose={() => {}} onFollow={() => {}} onSource={() => {}} />)
    expect(screen.getByRole('region', {name:'消费分类选择'})).toBeTruthy()
    expect(screen.getAllByRole('button', {name:'餐饮'})).toHaveLength(1)
    const raw = structuredClone(fixture)
    raw.spec.elements.root.children = ['total']
    delete (raw.spec.elements as Partial<typeof raw.spec.elements>).categories
    rerender(<ViewPanel view={parseView(raw)!} token="test" hidden
      onChange={() => {}} onClose={() => {}} onFollow={() => {}} onSource={() => {}} />)
    expect(screen.queryByRole('button', {name:'餐饮'})).toBeNull()
    expect(screen.getByRole('button', {name:'分类 1'})).toBeTruthy()
  })
  it('模型重复引用分类数据集时，页面也只有一个可点击分类入口', () => {
    const raw = structuredClone(fixture)
    raw.spec.elements.root.children.push('selector')
    ;(raw.spec.elements as Record<string, unknown>).selector = {
      type: 'Selector', props: { dataset_ref: 'fixture-bill:categories' },
    }
    const view = parseView(raw)!
    expect(view).not.toBeNull()
    const interact = vi.fn()
    render(<ViewPanel view={view} token="test" hidden={false} onChange={() => {}}
      onClose={() => {}} onFollow={() => {}} onSource={() => {}} />)
    expect(screen.getAllByRole('button', { name: '餐饮' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: '交通' })).toHaveLength(1)
    expect(screen.getByRole('region', {name:'消费分类选择'})).toBeTruthy()
    expect(interact).not.toHaveBeenCalled()
  })
  it('使用共享契约渲染可信金额，并在隐私模式隐藏', () => {
    const view = parseView(fixture)!
    expect(view).not.toBeNull()
    const { rerender } = render(<ViewRenderer view={view} hidden={false}/>)
    expect(screen.getByText(/100\.00/)).toBeTruthy()
    expect(screen.getByText('餐饮').tagName).not.toBe('BUTTON')
    rerender(<ViewRenderer view={view} hidden/>)
    expect(screen.queryByText('餐饮')).toBeNull()
    expect(screen.queryByText(/100\.00/)).toBeNull()
  })
  it('拒绝未知组件、附加属性、循环、伪造引用及不安全金额', () => {
    for (const mutate of [
      (v: typeof fixture) => { v.spec.elements.total.type = 'script' },
      (v: typeof fixture) => { Object.assign(v.spec.elements.total.props, { value: 999 }) },
      (v: typeof fixture) => { v.spec.elements.root.children.push('root') },
      (v: typeof fixture) => { v.spec.elements.total.props.metric_ref = 'untrusted' },
      (v: typeof fixture) => { v.trusted_data.metrics['fixture-bill:consumption_fen'].value = 1.5 },
    ]) { const data = structuredClone(fixture); mutate(data); expect(parseView(data)).toBeNull() }
  })
  it('按已保存排序显示类别，且选中态来自服务端版本', () => {
    const raw = {...structuredClone(fixture), interaction_state: {...fixture.interaction_state, sort:'amount_asc', selected_category:'餐饮'}}
    const view = parseView(raw)!
    render(<ViewRenderer view={view} hidden={false} interact={() => {}}/>)
    const buttons = screen.getAllByRole('button')
    expect(buttons.map(button => button.textContent)).toEqual(['交通', '餐饮'])
    expect(screen.getByRole('button', {name:'餐饮'}).getAttribute('aria-pressed')).toBe('true')
  })
  it('选中分类后展示该可信分类的金额和可用笔数', () => {
    const raw = structuredClone(fixture)
    Object.assign(raw.interaction_state, { selected_category: '餐饮' })
    const categories = raw.trusted_data.datasets['fixture-bill:categories']
    categories.columns.push({ key: 'count', label: '笔数', format: 'number' })
    Object.assign(categories.rows[0], { count: 3 })
    const view = parseView(raw)!

    const { rerender } = render(<ViewRenderer view={view} hidden={false} interact={() => {}} />)

    expect(screen.getByRole('status').textContent).toContain('已选餐饮')
    expect(screen.getByRole('status').textContent).toContain('60.00')
    expect(screen.getByRole('status').textContent).toContain('3 笔')
    rerender(<ViewRenderer view={view} hidden interact={() => {}} />)
    expect(screen.getByRole('status').textContent).not.toContain('餐饮')
    expect(screen.getByRole('status').textContent).not.toContain('60.00')
    expect(screen.getByRole('status').textContent).not.toContain('3 笔')
  })
  it('保存筛选前阻止续问，冲突后保留快照并允许重读', async () => {
    const view = parseView(fixture)!
    let reject!: (reason: Error) => void
    vi.spyOn(api, 'viewInteraction').mockImplementation(() => new Promise((_, fail) => { reject = fail }))
    const follow = vi.fn()
    render(<ViewPanel view={view} token="test" hidden={false} onChange={() => {}} onClose={() => {}} onFollow={follow} onSource={() => {}}/>)
    fireEvent.click(screen.getByRole('button', {name:'餐饮'}))
    expect((screen.getByRole('button', {name:'继续分析'}) as HTMLButtonElement).disabled).toBe(true)
    reject(new ApiError('conflict', 409))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('版本已变化'))
    expect(screen.getByRole('button', {name:'重新读取'})).toBeTruthy()
    expect(follow).not.toHaveBeenCalled()
  })

  it('筛选保存失败后解除发送阻塞', async () => {
    const view = parseView(fixture)!
    vi.spyOn(api, 'viewInteraction').mockRejectedValue(new ApiError('conflict', 409))
    const onBlockedChange = vi.fn()
    render(<ViewPanel view={view} token="test" hidden={false}
      onChange={() => {}} onClose={() => {}} onFollow={() => {}} onSource={() => {}}
      onBlockedChange={onBlockedChange}/>)

    fireEvent.click(screen.getByRole('button', {name:'餐饮'}))

    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('版本已变化'))
    expect(onBlockedChange.mock.calls).toEqual([[true], [false]])
  })

  it('重读失败后解除发送阻塞', async () => {
    const view = parseView(fixture)!
    vi.spyOn(api, 'viewInteraction').mockRejectedValue(new ApiError('conflict', 409))
    vi.spyOn(api, 'view').mockRejectedValue(new ApiError('unavailable', 503))
    const onBlockedChange = vi.fn()
    render(<ViewPanel view={view} token="test" hidden={false}
      onChange={() => {}} onClose={() => {}} onFollow={() => {}} onSource={() => {}}
      onBlockedChange={onBlockedChange}/>)

    fireEvent.click(screen.getByRole('button', {name:'餐饮'}))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('版本已变化'))
    fireEvent.click(screen.getByRole('button', {name:'重新读取'}))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('无法读取最新视图'))
    expect(onBlockedChange.mock.calls).toEqual([[true], [false], [true], [false]])
  })
})
