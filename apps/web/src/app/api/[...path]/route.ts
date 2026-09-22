import { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

const excludedRequestHeaders = new Set(['connection', 'content-length', 'host'])
const excludedResponseHeaders = new Set(['connection', 'content-encoding', 'content-length', 'transfer-encoding'])

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  const apiBase = (
    process.env.API_INTERNAL_BASE_URL ||
    process.env.API_BASE_URL ||
    process.env.HEYBROSKI_API_BASE_URL ||
    'http://127.0.0.1:8000'
  ).replace(/\/$/, '')
  const target = new URL(`${apiBase}/api/${path.join('/')}`)
  target.search = request.nextUrl.search

  const headers = new Headers()
  request.headers.forEach((value, key) => {
    if (!excludedRequestHeaders.has(key.toLowerCase())) headers.set(key, value)
  })

  try {
    const hasBody = request.method !== 'GET' && request.method !== 'HEAD'
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(70_000),
    })
    const responseHeaders = new Headers()
    upstream.headers.forEach((value, key) => {
      if (!excludedResponseHeaders.has(key.toLowerCase())) responseHeaders.set(key, value)
    })
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    const cause = error instanceof Error && error.cause instanceof Error
      ? `: ${error.cause.message}`
      : ''
    const message = `${error instanceof Error ? error.message : 'Unknown proxy error'}${cause}`
    console.error('api_proxy_failed', { method: request.method, target: target.toString(), message })
    return Response.json(
      { detail: `The Hey Broski API is unavailable: ${message}` },
      { status: 503 },
    )
  }
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
