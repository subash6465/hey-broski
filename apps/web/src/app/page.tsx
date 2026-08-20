"use client"

import { useEffect, useMemo, useRef, useState } from 'react'

type ChatStatus = 'connecting' | 'connected' | 'error'
type MessageRole = 'user' | 'assistant'

type Source = {
  account_label?: string
  title?: string
  snippet?: string
}

type ActionCard = {
  id: string
  priority?: 'urgent' | 'high' | 'medium' | 'low'
  card_type?: string
  confidence?: number
  title?: string
  source_refs?: Source[]
}

type ChatMessage = {
  id: string
  role: MessageRole
  content: string
  sources?: Source[]
  actionCards?: ActionCard[]
}

type SessionResponse = {
  session_id: string
}

type ChatResponse = {
  message_id: string
  content: string
  sources?: Source[]
  action_cards?: ActionCard[]
}

const suggestions = [
  'What needs my attention today?',
  'Who is waiting on me?',
  'Find upcoming renewals and deadlines',
  'Summarize important unread emails',
]

const statusColors: Record<ChatStatus, string> = {
  connecting: 'bg-yellow-500',
  connected: 'bg-green-500',
  error: 'bg-red-500',
}

function getApiBase(): string {
  const envBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, '')

  // Never expose Docker's internal service DNS name to the browser.
  // In Docker, use the Next.js rewrite and call relative /api instead.
  if (envBase && !envBase.includes('://api:')) {
    return envBase
  }

  return ''
}

async function fetchJson<T>(url: string, init: RequestInit, timeoutMs: number): Promise<T> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(url, { ...init, signal: controller.signal })
    const rawText = await res.text()

    console.log('API response status:', res.status)
    console.log('API response body:', rawText)

    if (!res.ok) {
      let message = rawText

      try {
        const parsed = JSON.parse(rawText)
        message = parsed.detail || parsed.message || rawText
      } catch {
        // keep raw text
      }

      throw new Error(`${res.status} ${res.statusText}${message ? ` - ${message}` : ''}`)
    }

    if (!rawText) {
      throw new Error('Backend returned an empty response')
    }

    return JSON.parse(rawText) as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds`)
    }

    throw err
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        'Hello! I\'m Hey Broski. I can help you with your daily attention summary, find upcoming renewals, detect follow-ups, and manage your tasks. Try asking "What needs my attention today?" or "Who is waiting on me?" to get started.',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [status, setStatus] = useState<ChatStatus>('connecting')
  const bottomRef = useRef<HTMLDivElement>(null)
  const apiBase = useMemo(() => getApiBase(), [])

  useEffect(() => {
    let cancelled = false

    async function initSession() {
      setStatus('connecting')
      try {
        const data = await fetchJson<SessionResponse>(
          `${apiBase}/api/chat/sessions`,
          { method: 'POST' },
          30_000,
        )
        if (!cancelled) {
          setSessionId(data.session_id)
          setStatus('connected')
        }
      } catch (err) {
        console.error('Session init error:', err)
        if (!cancelled) {
          setStatus('error')
          setMessages((prev) => [
            ...prev,
            {
              id: `session-error-${Date.now()}`,
              role: 'assistant',
              content:
                err instanceof Error
                  ? `Could not connect to the backend: ${err.message}`
                  : 'Could not connect to the backend.',
            },
          ])
        }
      }
    }

    initSession()
    return () => {
      cancelled = true
    }
  }, [apiBase])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const messageText = input.trim()
    if (!messageText || !sessionId || loading) return

    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', content: messageText }])
    setInput('')
    setLoading(true)

    try {
      const data = await fetchJson<ChatResponse>(
        `${apiBase}/api/chat/sessions/${sessionId}/messages`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: messageText }),
        },
        300_000,
      )

      setMessages((prev) => [
        ...prev,
        {
          id: data.message_id,
          role: 'assistant',
          content: data.content,
          sources: data.sources ?? [],
          actionCards: data.action_cards ?? [],
        },
      ])
    } catch (err) {
      console.error('API error:', err)
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${errorMessage}. Check the API and Ollama logs for details.`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Hey Broski</h1>
            <p className="text-sm text-gray-600">Local-first personal admin AI</p>
          </div>
          <div className="flex items-center gap-2" aria-live="polite">
            <span className={`w-2 h-2 rounded-full ${statusColors[status]}`} />
            <span className="text-sm text-gray-600 capitalize">{status}</span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-4xl mx-auto w-full p-6 flex flex-col">
        <div className="flex-1 overflow-y-auto space-y-6">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[70%] ${msg.role === 'user' ? 'order-2' : 'order-1'}`}>
                <div
                  className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-tr-none'
                      : 'bg-white border border-gray-200 rounded-tl-none shadow-sm'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <p className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2">
                        Sources ({msg.sources.length})
                      </p>
                      <div className="space-y-1">
                        {msg.sources.map((src, i) => (
                          <div key={`${src.title ?? 'source'}-${i}`} className="text-xs text-gray-700 bg-gray-50 p-2 rounded">
                            <span className="font-medium">{src.account_label ?? 'Source'}</span>
                            {src.title ? ` - ${src.title}` : null}
                            {src.snippet ? <div className="text-gray-600 mt-1">{src.snippet}</div> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {msg.actionCards && msg.actionCards.length > 0 && (
                    <div className="mt-3 space-y-3">
                      <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                        Suggested Actions ({msg.actionCards.length})
                      </p>
                      {msg.actionCards.map((card) => (
                        <div key={card.id} className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span
                                className={`px-2 py-1 rounded text-xs font-medium ${
                                  card.priority === 'urgent' || card.priority === 'high'
                                    ? 'bg-red-100 text-red-800'
                                    : card.priority === 'medium'
                                      ? 'bg-yellow-100 text-yellow-800'
                                      : 'bg-green-100 text-green-800'
                                }`}
                              >
                                {card.priority ?? 'low'}
                              </span>
                              <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                                {card.card_type ?? 'custom'}
                              </span>
                            </div>
                            {typeof card.confidence === 'number' ? (
                              <span className="text-xs text-gray-500">Confidence: {Math.round(card.confidence * 100)}%</span>
                            ) : null}
                          </div>
                          <h4 className="font-medium text-gray-900 mb-1">{card.title ?? 'Suggested action'}</h4>
                          <div className="flex flex-wrap gap-1 mb-2">
                            {card.source_refs?.map((src, i) => (
                              <span key={`${src.account_label ?? 'source'}-${i}`} className="px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs">
                                {src.account_label ?? 'Source'}
                              </span>
                            ))}
                          </div>
                          <div className="flex gap-2">
                            <button type="button" className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700">
                              Approve
                            </button>
                            <button type="button" className="px-3 py-1 bg-gray-200 text-gray-800 rounded text-xs font-medium hover:bg-gray-300">
                              Edit
                            </button>
                            <button type="button" className="px-3 py-1 bg-red-100 text-red-700 rounded text-xs font-medium hover:bg-red-200">
                              Dismiss
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl px-6 py-4">
                <div className="flex gap-2" aria-label="Assistant is typing">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSend} className="mt-6">
          <div className="flex gap-4">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask me anything..."
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              disabled={!sessionId || loading}
            />
            <button
              type="submit"
              disabled={!input.trim() || !sessionId || loading}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors font-medium"
            >
              Send
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => setInput(suggestion)}
                className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm hover:bg-gray-200 transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </form>
      </main>
    </div>
  )
}
