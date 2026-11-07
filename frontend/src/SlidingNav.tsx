import { useLayoutEffect, useRef, useState, type CSSProperties, type DependencyList, type HTMLAttributes, type ReactNode, type RefObject } from 'react'

export type SlidingThumbBox = {
  x: number
  y: number
  width: number
  height: number
}

const DEFAULT_ACTIVE_SELECTOR = '[aria-current="page"], [aria-selected="true"], [aria-checked="true"], .active, .is-active'

function readThumbBox(container: HTMLElement, active: HTMLElement): SlidingThumbBox {
  const parent = container.getBoundingClientRect()
  const target = active.getBoundingClientRect()
  return {
    x: target.left - parent.left + container.scrollLeft,
    y: target.top - parent.top + container.scrollTop,
    width: target.width,
    height: target.height,
  }
}

function adjustThumbBox(box: SlidingThumbBox, variant: 'pill' | 'underline' | 'dock'): SlidingThumbBox {
  if (variant !== 'underline') return box
  const inset = 6
  return {
    x: box.x + inset,
    y: box.y + box.height - 2,
    width: Math.max(12, box.width - inset * 2),
    height: 2,
  }
}

export function useSlidingThumb({
  activeKey,
  reduceMotion = false,
  itemSelector = DEFAULT_ACTIVE_SELECTOR,
  enabled = true,
  variant = 'pill',
}: {
  activeKey: string | number | boolean | null | undefined
  reduceMotion?: boolean
  itemSelector?: string
  enabled?: boolean
  variant?: 'pill' | 'underline' | 'dock'
}, extraDeps: DependencyList = []) {
  const containerRef = useRef<HTMLElement | null>(null)
  const primedRef = useRef(false)
  const [box, setBox] = useState<SlidingThumbBox | null>(null)
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    if (!enabled) {
      primedRef.current = false
      setBox(null)
      setReady(false)
      return
    }
    const container = containerRef.current
    if (!container) return

    let enableMotionFrame = 0
    const sync = () => {
      const active = container.querySelector<HTMLElement>(itemSelector)
      if (!active) {
        setBox(null)
        return
      }
      setBox(adjustThumbBox(readThumbBox(container, active), variant))
      if (!primedRef.current) {
        enableMotionFrame = window.requestAnimationFrame(() => {
          primedRef.current = true
          setReady(true)
        })
      }
    }

    sync()
    const frame = window.requestAnimationFrame(sync)
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(() => sync()) : null
    observer?.observe(container)
    window.addEventListener('resize', sync)
    return () => {
      window.cancelAnimationFrame(frame)
      window.cancelAnimationFrame(enableMotionFrame)
      observer?.disconnect()
      window.removeEventListener('resize', sync)
    }
  }, [activeKey, enabled, itemSelector, reduceMotion, variant, ...extraDeps])

  const thumbStyle: CSSProperties | undefined = box
    ? {
        width: box.width,
        height: box.height,
        transform: `translate(${box.x}px, ${box.y}px)`,
        transition: reduceMotion || !ready ? 'none' : undefined,
      }
    : undefined

  return {
    containerRef: containerRef as RefObject<HTMLElement | null>,
    thumbStyle,
    thumbReady: ready && Boolean(box),
  }
}

export function SlidingThumb({
  style,
  ready,
  variant = 'pill',
  className = '',
}: {
  style?: CSSProperties
  ready: boolean
  variant?: 'pill' | 'underline' | 'dock'
  className?: string
}) {
  if (!style) return null
  return (
    <span
      className={`sliding-thumb sliding-thumb--${variant}${ready ? ' is-ready' : ''}${className ? ` ${className}` : ''}`}
      style={style}
      aria-hidden="true"
    />
  )
}

type SlidingNavFrameProps = {
  as?: 'nav' | 'div'
  activeKey: string | number | boolean | null | undefined
  reduceMotion?: boolean
  variant?: 'pill' | 'underline' | 'dock'
  className?: string
  children: ReactNode
} & Omit<HTMLAttributes<HTMLElement>, 'className' | 'children'>

export function SlidingNavFrame({
  as = 'div',
  activeKey,
  reduceMotion = false,
  variant = 'pill',
  className = '',
  children,
  ...rest
}: SlidingNavFrameProps) {
  const { containerRef, thumbStyle, thumbReady } = useSlidingThumb({ activeKey, reduceMotion, variant })
  const classes = ['sliding-nav', className].filter(Boolean).join(' ')
  const thumb = <SlidingThumb style={thumbStyle} ready={thumbReady} variant={variant} />

  if (as === 'nav') {
    return (
      <nav
        {...rest}
        ref={(node) => {
          containerRef.current = node
        }}
        className={classes}
      >
        {thumb}
        {children}
      </nav>
    )
  }

  return (
    <div
      {...rest}
      ref={(node) => {
        containerRef.current = node
      }}
      className={classes}
    >
      {thumb}
      {children}
    </div>
  )
}
