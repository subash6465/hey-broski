"use client"

import { useState, useEffect, useRef } from 'react'

// Detect API base URL - use Codespaces forwarded port if available, else Next.js proxy
function getApiBase(): string {
  if (typeof window !== 'undefined') {
    // In Codespaces, ports are forwarded with predictable URLs
    const codespaceName = process.env.NEXT_PUBLIC_CODESPACE_NAME
    const forwardingDomain = process.env.NEXT_PUBLIC_GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
    
    if (codespaceName && forwardingDomain) {
      return `https://${codespaceName}-8000.${forwardingDomain}`
    }
    
    // Check if we can determine from current URL
    const hostname = window.location.hostname
    if (hostname.includes('githubpreview.dev') || hostname.includes('github.dev')) {
      // Replace port 3000 with 8000 in the forwarded URL
      return window.location.origin.replace(':3000', ':8000').replace('-3000.', '-8000.')
    }
  }
  // Fallback to Next.js proxy
  return ''
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Array<{
    id: string
    role: 'user' | 'assistant'
    content: string
    sources?: any[]
    actionCards?: any[]
  }>>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello! I\'m Hey Broski. I can help you with your daily attention summary, find upcoming renewals, detect follow-ups, and manage your tasks. Try asking "What needs my attention today?" or "Who is waiting on me?" to get started.'
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [status, setStatus] = useState<'connecting' | 'connected' | 'error'>('connecting')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const apiBase = getApiBase()

  useEffect(() => {
    const initSession = async () => {
      try {
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 30000)
        
        const res = await fetch(`${apiBase}/api/chat/sessions`, { 
          method: 'POST',
          signal: controller.signal
        })
        clearTimeout(timeoutId)
        
        if (!res.ok) throw new Error(`Session creation failed: ${res.status}`)
        const data = await res.json()
        console.log('Session created:', data.session_id)
        setSessionId(data.session_id)
        setStatus('connected')
      } catch (err) {
        console.error('Session init error:', err)
        setStatus('error')
      }
    }
    initSession()
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || !sessionId || loading) return

    const userMsg = { id: `user-${Date.now()}`, role: 'user' as const, content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 300000) // 5 min timeout
      
      const res = await fetch(`${apiBase}/api/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input }),
        signal: controller.signal
      })
      clearTimeout(timeoutId)
      
      if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`)
      const data = await res.json()
      
      const assistantMsg = {
        id: data.message_id,
        role: 'assistant' as const,
        content: data.content,
        sources: data.sources || [],
        actionCards: data.action_cards || []
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      console.error('API Error:', err)
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      setMessages(prev => [...prev, { 
        id: `err-${Date.now()}`, 
        role: 'assistant' as const, 
        content: `Error: ${errorMessage}. Check console for details.` 
      }])
    } finally {
      setLoading(false)
    }
  }

  const suggestions = [
    "What needs my attention today?",
    "Who is waiting on me?",
    "Find upcoming renewals and deadlines",
    "Summarize important unread emails"
  ]

  const statusColors = {
    connecting: 'bg-yellow-500',
    connected: 'bg-green-500',
    error: 'bg-red-500'
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Hey Broski</h1>
            <p className="text-sm text-gray-600">Local-first personal admin AI</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${statusColors[status]}`}></span>
              <span className="text-sm text-gray-600 capitalize">{status}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Chat Area */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-6 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-6" ref={messagesEndRef}>
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[70%] ${msg.role === 'user' ? 'order-2' : 'order-1'}`}>
                <div className={`
                  px-4 py-3 rounded-2xl text-sm leading-relaxed
                  ${msg.role === 'user' 
                    ? 'bg-blue-600 text-white rounded-tr-none' 
                    : 'bg-white border border-gray-200 rounded-tl-none shadow-sm'
                  }
                `}>
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  
                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <p className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2">
                        Sources ({msg.sources.length})
                      </p>
                      <div className="space-y-1">
                        {msg.sources.map((src: any, i: number) => (
                          <div key={i} className="text-xs text-gray-700 bg-gray-50 p-2 rounded">
                            <span className="font-medium">{src.account_label}</span> - {src.title}
                            <div className="text-gray-600 mt-1">{src.snippet}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Cards */}
                  {msg.actionCards && msg.actionCards.length > 0 && (
                    <div className="mt-3 space-y-3">
                      <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                        Suggested Actions ({msg.actionCards.length})
                      </p>
                      {msg.actionCards.map((card: any) => (
                        <div key={card.id} className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className={`
                                px-2 py-1 rounded text-xs font-medium
                                ${card.priority === 'high' ? 'bg-red-100 text-red-800' : 
                                  card.priority === 'medium' ? 'bg-yellow-100 text-yellow-800' : 
                                  'bg-green-100 text-green-800'}
                              `}>{card.priority}</span>
                              <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                                {card.card_type}
                              </span>
                            </div>
                            <span className="text-xs text-gray-500">
                              Confidence: {Math.round(card.confidence * 100)}%
                            </span>
                          </div>
                          <h4 className="font-medium text-gray-900 mb-1">{card.title}</h4>
                          <div className="flex flex-wrap gap-1 mb-2">
                            {card.source_refs?.map((src: any, i: number) => (
                              <span key={i} className="px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs">
                                {src.account_label}
                              </span>
                            ))}
                          </div>
                          <div className="flex gap-2">
                            <button className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700">
                              Approve
                            </button>
                            <button className="px-3 py-1 bg-gray-200 text-gray-800 rounded text-xs font-medium hover:bg-gray-300">
                              Edit
                            </button>
                            <button className="px-3 py-1 bg-red-100 text-red-700 rounded text-xs font-medium hover:bg-red-200">
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
                <div className="flex gap-2">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Form */}
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
            {suggestions.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setInput(s)}
                className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm hover:bg-gray-200 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </form>
      </main>
    </div>
  )
}