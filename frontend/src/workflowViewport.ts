export interface ViewportBounds {
  left: number
  top: number
  right: number
  bottom: number
}

export interface ViewportPan {
  x: number
  y: number
}

function minimalAxisPan(nodeStart: number, nodeEnd: number, canvasStart: number, canvasEnd: number, margin: number): number {
  if (nodeStart < canvasStart) return canvasStart + margin - nodeStart
  if (nodeEnd > canvasEnd) return canvasEnd - margin - nodeEnd
  return 0
}

export function minimalViewportPanForNode(node: ViewportBounds, canvas: ViewportBounds, margin = 16): ViewportPan {
  return {
    x: minimalAxisPan(node.left, node.right, canvas.left, canvas.right, margin),
    y: minimalAxisPan(node.top, node.bottom, canvas.top, canvas.bottom, margin),
  }
}
