const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, '')
// `/api` is the same-origin proxy path, not a host prefix. Treating it as a
// prefix would produce broken URLs such as `/api/api/health`.
export const apiBase = configuredBase && configuredBase !== '/api' && !configuredBase.includes('://api:')
  ? configuredBase
  : ''

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
      const detail = typeof body === 'object' && body && 'detail' in body ? String(body.detail) : text
      throw new Error(detail || `Request failed (${response.status})`)
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
