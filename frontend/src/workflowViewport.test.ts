import { describe, expect, it } from 'vitest'
import { minimalViewportPanForNode } from './workflowViewport'

const canvas = { left: 100, top: 80, right: 900, bottom: 680 }

describe('minimal viewport pan for newly added nodes', () => {
  it('leaves a node in the visible canvas exactly where it is', () => {
    expect(minimalViewportPanForNode({ left: 300, top: 200, right: 560, bottom: 420 }, canvas)).toEqual({ x: 0, y: 0 })
  })

  it('does not move a node that is close to an edge but is not obscured', () => {
    expect(minimalViewportPanForNode({ left: 120, top: 90, right: 380, bottom: 310 }, canvas)).toEqual({ x: 0, y: 0 })
  })

  it('moves only enough to clear the bottom canvas boundary and margin', () => {
    expect(minimalViewportPanForNode({ left: 300, top: 620, right: 560, bottom: 840 }, canvas)).toEqual({ x: 0, y: -176 })
  })

  it('moves only enough to clear a horizontal canvas boundary', () => {
    expect(minimalViewportPanForNode({ left: 850, top: 200, right: 1110, bottom: 420 }, canvas)).toEqual({ x: -226, y: 0 })
  })
})
