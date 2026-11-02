import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react'
import type { AssetKind, IntentEntity } from '../intent'

const LONG_PRESS_MS = 250
const TOUCH_CANCEL_PX = 9
const MOUSE_ACTIVATE_PX = 5

export type DragGhostState = {
  item: IntentEntity
  x: number
  y: number
  width: number
  height: number
  offsetX: number
  offsetY: number
}

type StartInput = {
  event: ReactPointerEvent<HTMLElement>
  item: IntentEntity
  element: HTMLElement
}

type Options = {
  findTarget: (kind: AssetKind, id: number) => IntentEntity | null
  onDrop: (source: IntentEntity, target: IntentEntity | null) => void
  onReferenceDrop?: (source: IntentEntity) => void
  onCancel?: () => void
  scrollRef?: RefObject<HTMLElement | null>
}

type Session = {
  item: IntentEntity
  element: HTMLElement
  pointerId: number
  pointerType: string
  startX: number
  startY: number
  lastX: number
  lastY: number
  active: boolean
  offsetX: number
  offsetY: number
  target: IntentEntity | null
  overComposer: boolean
  timer: ReturnType<typeof setTimeout> | null
  scrollFrame: number | null
}

export function useAssetDrag({ findTarget, onDrop, onReferenceDrop, onCancel, scrollRef }: Options) {
  const session = useRef<Session | null>(null)
  const [ghost, setGhost] = useState<DragGhostState | null>(null)
  const [activeTargetKey, setActiveTargetKey] = useState<string | null>(null)
  const [activeSourceKey, setActiveSourceKey] = useState<string | null>(null)
  const [settledKey, setSettledKey] = useState<string | null>(null)
  const suppressClick = useRef(false)
  const settleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reduced = useRef(false)

  useEffect(() => {
    reduced.current = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    return () => { if (settleTimer.current) clearTimeout(settleTimer.current) }
  }, [])

  const cleanup = useCallback((cancelled: boolean) => {
    const current = session.current
    if (!current) return
    if (current.timer) clearTimeout(current.timer)
    if (current.scrollFrame) cancelAnimationFrame(current.scrollFrame)
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    window.removeEventListener('pointercancel', cancel)
    window.removeEventListener('keydown', keydown)
    document.body.classList.remove('asset-dragging')
    current.element.style.touchAction = ''
    const wasActive = current.active
    const source = current.item
    const target = current.target
    const overComposer = current.overComposer
    session.current = null
    setGhost(null)
    setActiveTargetKey(null)
    setActiveSourceKey(null)
    if (wasActive) {
      suppressClick.current = true
      setTimeout(() => { suppressClick.current = false }, 0)
      if (cancelled) onCancel?.()
      else {
        if (target) {
          setSettledKey(`${target.kind}:${target.id}`)
          if (settleTimer.current) clearTimeout(settleTimer.current)
          settleTimer.current = setTimeout(() => setSettledKey(null), 320)
        }
        if (overComposer && onReferenceDrop) onReferenceDrop(source)
        else onDrop(source, target)
      }
    }
  }, [onCancel, onDrop, onReferenceDrop])

  const activate = useCallback(() => {
    const current = session.current
    if (!current || current.active) return
    current.active = true
    const rect = current.element.getBoundingClientRect()
    current.offsetX = current.lastX - rect.left
    current.offsetY = current.lastY - rect.top
    setGhost({
      item: current.item, x: current.lastX, y: current.lastY,
      width: rect.width, height: rect.height,
      offsetX: current.offsetX, offsetY: current.offsetY,
    })
    setActiveSourceKey(`${current.item.kind}:${current.item.id}`)
    current.element.style.touchAction = 'none'
    document.body.classList.add('asset-dragging')
    if ('vibrate' in navigator) navigator.vibrate?.(30)
    autoScroll()
  }, [])

  function autoScroll() {
    const current = session.current
    const container = scrollRef?.current
    if (!current || !current.active || !container) return
    const rect = container.getBoundingClientRect()
    const edge = 64
    let delta = 0
    if (current.lastY < rect.top + edge) delta = -10
    else if (current.lastY > rect.bottom - edge) delta = 10
    if (delta) container.scrollTop += delta
    current.scrollFrame = requestAnimationFrame(autoScroll)
  }

  function targetAt(x: number, y: number): IntentEntity | null {
    const current = session.current
    if (!current) return null
    const nodes = document.elementsFromPoint(x, y)
    for (const node of nodes) {
      if (!(node instanceof HTMLElement)) continue
      const kind = node.dataset.assetKind as AssetKind | undefined
      const rawId = node.dataset.assetId
      if (!kind || !rawId) continue
      const id = Number(rawId)
      if (!Number.isSafeInteger(id)) continue
      if (kind === current.item.kind && id === current.item.id) continue
      const item = findTarget(kind, id)
      if (!item || item.disabled) continue
      return item
    }
    return null
  }

  function move(event: PointerEvent) {
    const current = session.current
    if (!current || event.pointerId !== current.pointerId) return
    current.lastX = event.clientX
    current.lastY = event.clientY
    const distance = Math.hypot(event.clientX - current.startX, event.clientY - current.startY)
    if (!current.active) {
      if (current.pointerType === 'mouse' && distance > MOUSE_ACTIVATE_PX) activate()
      else if (distance > TOUCH_CANCEL_PX) {
        cleanup(true)
        return
      }
    }
    if (!current.active) return
    event.preventDefault()
    setGhost((previous) => previous ? {
      ...previous, x: event.clientX, y: event.clientY,
    } : previous)
    const target = targetAt(event.clientX, event.clientY)
    current.overComposer = document.elementsFromPoint(event.clientX, event.clientY).some(
      node => node instanceof HTMLElement && !!node.closest('[data-object-dropzone]')
    )
    current.target = current.overComposer ? null : target
    setActiveTargetKey(current.overComposer ? null : target ? `${target.kind}:${target.id}` : null)
  }

  function up(event: PointerEvent) {
    const current = session.current
    if (!current || event.pointerId !== current.pointerId) return
    cleanup(false)
  }

  function cancel(event?: PointerEvent) {
    const current = session.current
    if (event && current && event.pointerId !== current.pointerId) return
    cleanup(true)
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      cleanup(true)
    }
  }

  const start = useCallback(({ event, item, element }: StartInput) => {
    if (item.disabled) return
    if (event.pointerType === 'mouse' && event.button !== 0) return
    cleanup(true)
    if (settleTimer.current) clearTimeout(settleTimer.current)
    setSettledKey(null)
    suppressClick.current = false
    const current: Session = {
      item, element, pointerId: event.pointerId, pointerType: event.pointerType,
      startX: event.clientX, startY: event.clientY,
      lastX: event.clientX, lastY: event.clientY,
      active: false, offsetX: 0, offsetY: 0, target: null, overComposer: false,
      timer: null, scrollFrame: null,
    }
    session.current = current
    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    window.addEventListener('keydown', keydown)
    if (event.pointerType !== 'mouse') {
      current.timer = setTimeout(() => {
        if (session.current === current && !current.active) activate()
      }, LONG_PRESS_MS)
    } else {
      event.preventDefault()
    }
  }, [activate, cleanup])

  const consumeClick = useCallback(() => {
    if (!suppressClick.current) return false
    suppressClick.current = false
    return true
  }, [])

  return { ghost, activeTargetKey, activeSourceKey, settledKey, start, consumeClick, reduced: reduced.current }
}
