const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, '')
// `/api` is the same-origin proxy path, not a host prefix. Treating it as a
// prefix would produce broken URLs such as `/api/api/health`.
export const apiBase = configuredBase && configuredBase !== '/api' && !configuredBase.includes('://api:')
  ? configuredBase
  : ''

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail || fallback
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (!item || typeof item !== 'object') return ''
      const issue = item as { loc?: unknown; msg?: unknown }
      const field = Array.isArray(issue.loc) ? issue.loc.filter(part => part !== 'body').join(' ') : ''
      return typeof issue.msg === 'string' ? `${field ? `${field}: ` : ''}${issue.msg}` : ''
    }).filter(Boolean)
    return messages.join('; ') || fallback
  }
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message
  return fallback
}

export async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 60_000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${apiBase}${path}`, { ...init, signal: controller.signal })
    const text = await response.text()
    let body: unknown = undefined
    try {
      body = text ? JSON.parse(text) : undefined
    } catch {
      body = text
    }
    if (!response.ok) {
      const detail = typeof body === 'object' && body && 'detail' in body ? body.detail : body
      throw new Error(errorMessage(detail, `Request failed (${response.status})`))
    }
    return body as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('The request timed out. The local model may be busy; you can retry safely.')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export type ChatStreamEvent =
  | { type: 'status' | 'content'; text: string }
  | { type: 'error'; detail: string }
  | { type: 'complete'; message_id: string; turn_id: string; user_message_id: string; content: string; sources: import('./types').Source[]; action_cards: import('./types').ActionCard[]; generated_by: import('./types').GeneratedBy }

export async function streamChat(path: string, message: string, onEvent: (event: ChatStreamEvent) => void): Promise<void> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/x-ndjson' },
    body: JSON.stringify({ message }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(errorMessage(body.detail, `Chat failed (${response.status})`))
  }
  if (!response.body) throw new Error('The chat stream did not open')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.trim()) continue
        const event = JSON.parse(line) as ChatStreamEvent
        if (event.type === 'error') throw new Error(event.detail)
        onEvent(event)
        if (event.type === 'complete') completed = true
      }
    }
    if (!completed) throw new Error('The model stream ended before completing an answer. Please retry.')
  } finally {
    reader.releaseLock()
  }
}
