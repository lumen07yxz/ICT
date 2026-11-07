import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react'
import { SlidingThumb, useSlidingThumb } from './SlidingNav'

const DOCK_BASE = 40
const DOCK_MAX = 64
const DOCK_GAP = 10
const DOCK_RANGE = 90
const DOCK_PAD_X = 14

export type BottomDockItem = {
  id: string
  label: string
  active?: boolean
  dividerBefore?: boolean
  onSelect: () => void
  icon: ReactNode
}

function magnificationAt(distance: number): number {
  if (distance >= DOCK_RANGE) return 0
  const t = 1 - distance / DOCK_RANGE
  // Cosine falloff keeps nearby icons moving with the cursor without hard steps.
  return 0.5 - 0.5 * Math.cos(Math.PI * t)
}

function scalesFromPointer(pointerX: number, count: number): number[] {
  // Base centers are computed from the viewport midpoint so tray growth does not jitter the origin.
  const totalBase = count * DOCK_BASE + Math.max(0, count - 1) * DOCK_GAP + DOCK_PAD_X * 2
  let x = window.innerWidth / 2 - totalBase / 2 + DOCK_PAD_X
  const centers: number[] = []
  for (let i = 0; i < count; i += 1) {
    centers.push(x + DOCK_BASE / 2)
    x += DOCK_BASE + DOCK_GAP
  }
  return centers.map((center) => {
    const boost = magnificationAt(Math.abs(pointerX - center))
    return 1 + (DOCK_MAX / DOCK_BASE - 1) * boost
  })
}

export function BottomDockNav({
  items,
  reduceMotion = false,
}: {
  items: BottomDockItem[]
  reduceMotion?: boolean
}) {
  const [scales, setScales] = useState<number[]>(() => items.map(() => 1))
  const [peakIndex, setPeakIndex] = useState<number | null>(null)
  const [focusIndex, setFocusIndex] = useState<number | null>(null)
  const [finePointer, setFinePointer] = useState(false)
  const activeId = items.find((item) => item.active)?.id ?? null
  const scaleSignature = scales.map((value) => value.toFixed(3)).join(',')
  const { containerRef, thumbStyle, thumbReady } = useSlidingThumb({
    activeKey: activeId,
    reduceMotion,
    variant: 'dock',
    itemSelector: '.bottom-dock__item.is-active, .bottom-dock__item[aria-current="page"]',
  }, [scaleSignature])

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      setFinePointer(true)
      return
    }
    const media = window.matchMedia('(pointer: fine)')
    const sync = () => setFinePointer(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  useEffect(() => {
    setScales(items.map(() => 1))
    setPeakIndex(null)
  }, [items.length])

  const magnificationEnabled = finePointer && !reduceMotion

  const resetScales = () => {
    setScales(items.map(() => 1))
    setPeakIndex(null)
  }

  const applyPointer = (clientX: number) => {
    if (!magnificationEnabled) return
    const next = scalesFromPointer(clientX, items.length)
    setScales(next)
    let best = 0
    for (let i = 1; i < next.length; i += 1) {
      if (next[i] > next[best]) best = i
    }
    setPeakIndex(next[best] > 1.04 ? best : null)
  }

  const labelIndex = peakIndex ?? focusIndex

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('.bottom-dock__item'))
    if (buttons.length === 0) return
    const current = buttons.findIndex((button) => button === document.activeElement)
    const delta = event.key === 'ArrowRight' ? 1 : -1
    const next = current < 0 ? 0 : (current + delta + buttons.length) % buttons.length
    buttons[next]?.focus()
  }

  return (
    <nav className="bottom-dock" aria-label="一级导航">
      <div
        ref={(node) => {
          containerRef.current = node
        }}
        className={'bottom-dock__tray sliding-nav' + (magnificationEnabled ? ' is-magnify' : ' is-static')}
        onMouseMove={(event) => applyPointer(event.clientX)}
        onMouseLeave={resetScales}
        onKeyDown={onKeyDown}
      >
        <SlidingThumb style={thumbStyle} ready={thumbReady} variant="dock" />
        {items.map((item, index) => {
          const scale = magnificationEnabled ? scales[index] ?? 1 : 1
          const size = DOCK_BASE * scale
          const showLabel = labelIndex === index
          return (
            <div key={item.id} className="bottom-dock__slot">
              {item.dividerBefore && <span className="bottom-dock__divider" aria-hidden="true" />}
              <button
                type="button"
                className={'bottom-dock__item' + (item.active ? ' is-active' : '')}
                aria-label={item.label}
                aria-current={item.active ? 'page' : undefined}
                style={{ width: size, height: size }}
                onClick={item.onSelect}
                onFocus={() => setFocusIndex(index)}
                onBlur={() => setFocusIndex((current) => (current === index ? null : current))}
              >
                <span className="bottom-dock__icon" style={{ width: size * 0.55, height: size * 0.55 }}>
                  {item.icon}
                </span>
                {showLabel && (
                  <span className="bottom-dock__label" aria-hidden="true">
                    {item.label}
                  </span>
                )}
              </button>
            </div>
          )
        })}
      </div>
    </nav>
  )
}
