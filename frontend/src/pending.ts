export interface PendingAnalysis {
  text: string
  paymentContext: string
}

// Module-level handoff from InputPage to TracePage across a client-side
// navigation — the SSE request only exists once TracePage mounts and
// opens it, so InputPage can't hold the connection itself.
let pending: PendingAnalysis | null = null

export function setPendingAnalysis(request: PendingAnalysis) {
  pending = request
}

export function takePendingAnalysis(): PendingAnalysis | null {
  const request = pending
  pending = null
  return request
}
