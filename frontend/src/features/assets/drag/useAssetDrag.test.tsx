// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useAssetDrag } from './useAssetDrag'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

function emitPointer(type: string, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y })
  Object.defineProperty(event, 'pointerId', { value: 4 })
  window.dispatchEvent(event)
}

it('asset pointer drag to composer creates reference, not a bank operation', () => {
  const item = { kind: 'account' as const, id: 7, label: '演示活期', detail: '****1234' }
  const source = document.createElement('div')
  source.getBoundingClientRect = () => ({
    x: 0, y: 0, left: 0, top: 0, width: 120, height: 70,
    right: 120, bottom: 70, toJSON: () => ({}),
  })
  const composer = document.createElement('div')
  composer.setAttribute('data-object-dropzone', '')
  document.body.append(source, composer)
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true, value: () => [composer],
  })
  const onDrop = vi.fn()
  const onReferenceDrop = vi.fn()
  const { result, unmount } = renderHook(() => useAssetDrag({
    findTarget: () => null, onDrop, onReferenceDrop,
  }))
  act(() => result.current.start({
    item, element: source,
    event: { pointerId: 4, pointerType: 'mouse', button: 0,
      clientX: 10, clientY: 10, preventDefault: vi.fn() } as never,
  }))
  act(() => emitPointer('pointermove', 45, 25))
  act(() => emitPointer('pointerup', 45, 25))
  expect(onReferenceDrop).toHaveBeenCalledWith(item)
  expect(onDrop).not.toHaveBeenCalled()
  unmount()
  source.remove()
  composer.remove()
})
