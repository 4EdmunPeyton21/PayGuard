export type RiskLevel = 'LOW_CONCERN' | 'CAUTION' | 'HIGH_RISK'

export interface Evidence {
  id: string
  tool: string
  signal: string
  observed: string
  interpretation: string
  quote: string | null
  direction: 'risk' | 'benign' | 'neutral'
  strength: 'HIGH' | 'MEDIUM' | 'LOW'
  confidence: number
  kb_ref: string | null
}

export interface ReportClaim {
  text: string
  evidence_ids: string[]
}

export interface SafetyReport {
  case_id: string
  risk_level: RiskLevel
  risk_score: number
  headline: string
  why: ReportClaim[]
  evidence: Evidence[]
  recommended_actions: string[]
  unverified: string[]
  rules_fired: string[]
  policy_version: string
  kb_version: string
  model: string
  tool_calls: number
  latency_ms: number
}

export class ApiError extends Error {}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(body?.detail ?? `Request failed (${res.status})`)
  }
  return res.json()
}

export function analyzeCase(text: string, paymentContext: string): Promise<SafetyReport> {
  return fetch('/api/v1/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      payment_context: paymentContext || null,
    }),
  }).then(unwrap<SafetyReport>)
}

export function getCase(caseId: string): Promise<SafetyReport> {
  return fetch(`/api/v1/cases/${caseId}`).then(unwrap<SafetyReport>)
}

export interface OcrResult {
  text: string
  confidence: number
  low_confidence: boolean
  line_count: number
}

export function ocrUpload(file: File): Promise<OcrResult> {
  const formData = new FormData()
  formData.append('file', file)
  return fetch('/api/v1/ocr', { method: 'POST', body: formData }).then(unwrap<OcrResult>)
}

export interface ToolStartEvent {
  tool: string
  args: Record<string, unknown>
}

export interface ToolResultEvent {
  tool: string
  result_type: 'ok' | 'rejected'
  elapsed_ms: number
  summary: string
  raw?: unknown
}

export interface RiskEvent {
  level: RiskLevel
  score: number
  rules_fired: string[]
}

export type StreamEvent =
  | { event: 'ingest'; data: { case_id: string; input_types: string[] } }
  | { event: 'tool_start'; data: ToolStartEvent }
  | { event: 'tool_result'; data: ToolResultEvent }
  | { event: 'risk'; data: RiskEvent }
  | { event: 'report'; data: SafetyReport }

/**
 * Consumes POST /api/v1/analyze/stream. Native EventSource can't send a
 * POST body, so this reads the raw SSE frames off the fetch body stream.
 */
export async function* streamAnalyzeCase(
  text: string,
  paymentContext: string,
): AsyncGenerator<StreamEvent> {
  const res = await fetch('/api/v1/analyze/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, payment_context: paymentContext || null }),
  })
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null)
    throw new ApiError(body?.detail ?? `Request failed (${res.status})`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sepIndex = buffer.indexOf('\n\n')
    while (sepIndex !== -1) {
      const frame = buffer.slice(0, sepIndex)
      buffer = buffer.slice(sepIndex + 2)
      const lines = frame.split('\n')
      const eventLine = lines.find((l) => l.startsWith('event: '))
      const dataLine = lines.find((l) => l.startsWith('data: '))
      if (eventLine && dataLine) {
        yield {
          event: eventLine.slice('event: '.length),
          data: JSON.parse(dataLine.slice('data: '.length)),
        } as StreamEvent
      }
      sepIndex = buffer.indexOf('\n\n')
    }
  }
}
