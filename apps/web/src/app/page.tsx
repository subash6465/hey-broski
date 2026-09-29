'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import {
  Archive,
  Bot,
  CheckCircle2,
  ChevronRight,
  FileText,
  Inbox,
  Menu,
  MessageSquarePlus,
  History,
  Paperclip,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { ActionCardView } from '@/components/ActionCardView'
import { request, streamChat, type ChatStreamEvent } from '@/lib/api'
import type { ActionCard, ChatMessage, ChatSession, DocumentRecord, Source, StoredMessage } from '@/lib/types'

type View = 'chat' | 'actions' | 'vault' | 'history'
type DeleteTarget = { kind: 'conversation' | 'document'; id: string; label: string }
type Health = { status: string; mode: string; inference_enabled: boolean; services: { database: string; ollama: string }; model: string }

const prompts = [
  { label: 'Daily brief', text: 'What needs my attention this week?' },
  { label: 'Waiting on me', text: 'Who is waiting on me?' },
  { label: 'Renewals', text: 'Show upcoming renewals and deadlines' },
]

const welcome: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: "Morning! I’ve organized your demo inbox. Ask for a daily brief, check who needs a reply, or upload a document to search your local vault.",
}

export default function Home() {
  const [view, setView] = useState<View>('chat')
  const [mobileNav, setMobileNav] = useState(false)
  const [sessionId, setSessionId] = useState<string>()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([welcome])
  const [actions, setActions] = useState<ActionCard[]>([])
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [health, setHealth] = useState<Health>()
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [statusText, setStatusText] = useState('')
  const [uploading, setUploading] = useState(false)
  const [decisionBusy, setDecisionBusy] = useState<string>()
  const [error, setError] = useState<string>()
  const [notice, setNotice] = useState<string>()
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>()
  const [deleting, setDeleting] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    async function initialize() {
      const [history, status, currentActions, docs] = await Promise.allSettled([
          request<{ sessions: ChatSession[] }>('/api/chat/sessions'),
          request<Health>('/api/health'),
          request<ActionCard[]>('/api/actions'),
          request<DocumentRecord[]>('/api/documents'),
      ])
      if (history.status === 'fulfilled') {
        setSessions(history.value.sessions)
        if (history.value.sessions.length) {
          const latest = history.value.sessions[0]
          try {
            const stored = await request<{ messages: StoredMessage[] }>(`/api/chat/sessions/${latest.session_id}/messages`)
            setSessionId(latest.session_id)
            setMessages(stored.messages.length ? stored.messages.map(toChatMessage) : [welcome])
          } catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Could not load conversation history')
          }
        }
      } else setError('Could not load conversation history')
      if (status.status === 'fulfilled') setHealth(status.value)
      if (currentActions.status === 'fulfilled') setActions(currentActions.value)
      if (docs.status === 'fulfilled') setDocuments(docs.value)
    }
    void initialize()
  }, [])

  useEffect(() => {
    // An effect may only return a cleanup function. Some embedded browsers
    // return a value from scrollIntoView(), so do not return that expression.
    bottom.current?.scrollIntoView({ behavior: busy ? 'auto' : 'smooth' })
  }, [messages, busy, streamingText, statusText])

  useEffect(() => {
    const interval = window.setInterval(() => {
      void request<Health>('/api/health').then(setHealth).catch(() => setHealth(undefined))
    }, 12_000)
    return () => window.clearInterval(interval)
  }, [])

  async function sendMessage(event?: FormEvent, selectedPrompt?: string) {
    event?.preventDefault()
    const text = (selectedPrompt ?? input).trim()
    if (!text || busy) return
    setError(undefined)
    setNotice(undefined)
    setBusy(true)
    setStreamingText('')
    setStatusText('')
    const pendingId = crypto.randomUUID()
    try {
      let activeSession = sessionId
      if (!activeSession) {
        const session = await request<{ session_id: string }>(
          '/api/chat/sessions',
          { method: 'POST' },
          15_000,
        )
        activeSession = session.session_id
        setSessionId(activeSession)
      }
      setInput('')
      setMessages((current) => [...current, { id: pendingId, role: 'user', content: text }])
      await streamChat(`/api/chat/sessions/${activeSession}/messages/stream`, text, (update: ChatStreamEvent) => {
        if (update.type === 'status') setStatusText(update.text)
        if (update.type === 'content') {
          setStatusText('')
          setStreamingText((current) => current + update.text)
        }
        if (update.type === 'complete') {
          setStreamingText('')
          setStatusText('')
          setMessages((current) => [...current.map((item) => item.id === pendingId ? { ...item, id: update.user_message_id, turnId: update.turn_id } : item), {
            id: update.message_id, role: 'assistant', content: update.content, sources: update.sources,
            actionCards: update.action_cards, generatedBy: update.generated_by, turnId: update.turn_id,
          }])
          setActions((current) => mergeActions(current, update.action_cards))
        }
      })
      try {
        setSessions((await request<{ sessions: ChatSession[] }>('/api/chat/sessions')).sessions)
      } catch {
        // The answer is already persisted; a failed sidebar refresh must not
        // turn a successful chat response into a failed send.
      }
    } catch (caught) {
      setMessages((current) => current.filter((message) => message.id !== pendingId))
      setInput(text)
      setError(caught instanceof Error ? caught.message : 'Message failed')
    } finally {
      setBusy(false)
      setStreamingText('')
      setStatusText('')
    }
  }

  function newConversation() {
    if (busy) return
    setSessionId(undefined)
    setMessages([welcome])
    setInput('')
    setError(undefined)
    setView('chat')
    setMobileNav(false)
  }

  async function openConversation(id: string) {
    if (busy) return
    setError(undefined)
    try {
      const stored = await request<{ messages: StoredMessage[] }>(`/api/chat/sessions/${id}/messages`)
      setSessionId(id)
      setMessages(stored.messages.length ? stored.messages.map(toChatMessage) : [welcome])
      setView('chat')
      setMobileNav(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not open conversation')
    }
  }

  async function decide(card: ActionCard, decision: 'approve' | 'dismiss') {
    setDecisionBusy(card.id)
    setError(undefined)
    try {
      const updated = await request<ActionCard>(`/api/actions/${card.id}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision }),
      })
      setActions((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMessages((current) => current.map((message) => ({
        ...message,
        actionCards: message.actionCards?.map((item) => item.id === updated.id ? updated : item),
      })))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update the action')
    } finally {
      setDecisionBusy(undefined)
    }
  }

  async function upload(file?: File) {
    if (!file || uploading) return
    setUploading(true)
    setError(undefined)
    setNotice(undefined)
    try {
      const form = new FormData()
      form.append('file', file)
      const document = await request<DocumentRecord>('/api/documents', { method: 'POST', body: form })
      setDocuments((current) => [document, ...current])
      setNotice(`${document.filename} was added to your local document vault.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function confirmDelete() {
    if (!deleteTarget || deleting || busy) return
    const target = deleteTarget
    setDeleting(true)
    setError(undefined)
    setNotice(undefined)
    try {
      const path = target.kind === 'conversation'
        ? `/api/chat/sessions/${encodeURIComponent(target.id)}`
        : `/api/documents/${encodeURIComponent(target.id)}`
      await request<void>(path, { method: 'DELETE' })
      if (target.kind === 'conversation') {
        setSessions((current) => current.filter((session) => session.session_id !== target.id))
        if (sessionId === target.id) {
          setSessionId(undefined)
          setMessages([welcome])
          setInput('')
        }
        try {
          setActions(await request<ActionCard[]>('/api/actions'))
        } catch {
          // The delete succeeded; refresh the inbox on the next visit.
        }
      } else {
        setDocuments((current) => current.filter((document) => document.id !== target.id))
      }
      setNotice(target.kind === 'conversation' ? 'Conversation deleted permanently.' : 'Document removed from the vault. Existing conversations are unchanged.')
      setDeleteTarget(undefined)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Delete failed')
      setDeleteTarget(undefined)
    } finally {
      setDeleting(false)
    }
  }

  async function switchView(next: View) {
    setView(next)
    setMobileNav(false)
    try {
      if (next === 'actions') setActions(await request<ActionCard[]>('/api/actions'))
      if (next === 'vault') setDocuments(await request<DocumentRecord[]>('/api/documents'))
      if (next === 'history') setSessions((await request<{ sessions: ChatSession[] }>('/api/chat/sessions')).sessions)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load this view')
    }
  }

  const pendingCount = actions.filter((action) => action.status === 'pending').length

  return (
    <div className="app-shell">
      <button className="mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu /></button>
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="brand"><div className="brand-mark"><Sparkles size={20} /></div><span>Hey Broski</span></div>
        <button className="sidebar-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X /></button>
        <button className="new-chat" onClick={newConversation} disabled={busy}><MessageSquarePlus size={17} /> New conversation</button>
        <nav>
          <NavButton icon={<Inbox />} label="Chat" active={view === 'chat'} onClick={() => void switchView('chat')} />
          <NavButton icon={<CheckCircle2 />} label="Action inbox" count={pendingCount} active={view === 'actions'} onClick={() => void switchView('actions')} />
          <NavButton icon={<Archive />} label="Document vault" active={view === 'vault'} onClick={() => void switchView('vault')} />
          <NavButton icon={<History />} label="Conversation history" active={view === 'history'} onClick={() => void switchView('history')} />
        </nav>
        <div className="recent-conversations" aria-label="Recent conversations">
          <span className="recent-label">RECENT CHATS</span>
          {sessions.slice(0, 8).map((session) => <div className="recent-chat-row" key={session.session_id}><button className={sessionId === session.session_id && view === 'chat' ? 'selected' : ''} disabled={busy || deleting} onClick={() => void openConversation(session.session_id)} title={session.title}>{session.title}</button><button className="recent-delete" type="button" disabled={busy || deleting} onClick={() => setDeleteTarget({ kind: 'conversation', id: session.session_id, label: session.title })} aria-label={`Delete conversation ${session.title}`} title="Delete conversation"><Trash2 size={14} /></button></div>)}
        </div>
        <div className="sidebar-footer">
          <div className="privacy-note"><ShieldCheck size={17} /><div><strong>Local-first</strong><span>Your data stays on this device.</span></div></div>
          <div className="profile"><div className="avatar">Y</div><div><strong>You</strong><span>Demo workspace</span></div></div>
        </div>
      </aside>
      {mobileNav && <button className="nav-overlay" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}

      <main className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">PERSONAL ADMIN COPILOT</p><h1>{viewTitles[view]}</h1></div>
          <div className="status-cluster">
            <span className="mode-badge"><span className="status-dot" /> {!health ? 'Connecting…' : health.mode === 'demo' ? 'Demo data' : 'Connected data'}</span>
            <span className="model-label">{!health ? 'Checking local model' : !health.inference_enabled ? 'Local model disabled' : health.services.ollama === 'available' ? `Local model: ${health.model}` : health.services.ollama.startsWith('model_missing:') ? `Model not ready: ${health.model}` : 'Local model offline'}</span>
          </div>
        </header>
        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError(undefined)}><X size={16} /></button></div>}
        {notice && <div className="notice-banner" role="status"><span>{notice}</span><button onClick={() => setNotice(undefined)}><X size={16} /></button></div>}

        {view === 'chat' && (
          <section className="chat-layout">
            <div className="messages">
              {messages.map((message) => (
                <div className={`message-row ${message.role}`} key={message.id}>
                  {message.role === 'assistant' && <div className="bot-avatar"><Bot size={17} /></div>}
                  <div className="message-wrap">
                    <div className="message-bubble"><p>{message.content}</p></div>
                    {message.generatedBy && <span className="generated-by">Answered by local model ({health?.model ?? 'Ollama'})</span>}
                    {!!message.sources?.length && <SourceList sources={message.sources} />}
                    {!!message.actionCards?.length && <div className="inline-actions">{message.actionCards.map((card) => <ActionCardView key={card.id} card={actions.find((item) => item.id === card.id) ?? card} busy={decisionBusy === card.id} onDecision={decide} />)}</div>}
                  </div>
                </div>
              ))}
              {messages.length === 1 && <div className="prompt-grid">{prompts.map((prompt) => <button type="button" disabled={busy} key={prompt.label} onClick={() => void sendMessage(undefined, prompt.text)}><span>{prompt.label}</span><p>{prompt.text}</p><ChevronRight size={16} /></button>)}</div>}
              {busy && <div className="message-row assistant"><div className="bot-avatar"><Bot size={17} /></div><div className="message-wrap">{streamingText ? <div className="message-bubble"><p>{streamingText}</p></div> : statusText ? <div className="thinking-preview" role="status"><span>Preparing answer…</span><p>{statusText}</p></div> : <div className="typing" role="status" aria-label="Generating an answer"><i /><i /><i /></div>}</div></div>}
              <div ref={bottom} />
            </div>
            <form className="composer" onSubmit={sendMessage} aria-busy={busy}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage() } }} placeholder="Ask what needs your attention…" rows={1} disabled={busy} />
              <label className="attach" title="Upload a document"><Paperclip size={19} /><input type="file" disabled={uploading} accept=".pdf,.txt,.md,.csv" onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; void upload(file) }} /></label>
              <button className="send-button" disabled={!input.trim() || busy}><Send size={18} /></button>
              <span className="composer-note">Sources are cited. Actions always require approval.</span>
            </form>
          </section>
        )}

        {view === 'actions' && <Collection title={`${pendingCount} items need a decision`} subtitle="Review every proposed action before anything changes.">{actions.length ? actions.map((card) => <ActionCardView key={card.id} card={card} busy={decisionBusy === card.id} onDecision={decide} />) : <Empty text="Ask for your daily brief to generate action cards." />}</Collection>}
        {view === 'vault' && <Collection title="Your local documents" subtitle="PDF, text, Markdown, and CSV files are searchable from chat."><label className="upload-card"><Upload size={22} /><strong>{uploading ? 'Uploading…' : 'Upload a document'}</strong><span>Maximum 10 MB</span><input type="file" disabled={uploading} accept=".pdf,.txt,.md,.csv" onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; void upload(file) }} /></label>{documents.map((doc) => <article className="document-card" key={doc.id}><FileText /><div><strong>{doc.filename}</strong><span>{Math.ceil(doc.size_bytes / 1024)} KB · {new Date(doc.created_at).toLocaleDateString()}</span><p>{doc.preview}</p><div className="document-actions"><button type="button" onClick={() => { setInput(`What does ${doc.filename} say about `); setView('chat') }}>Ask about this file</button><button type="button" className="delete-button" disabled={busy || uploading || deleting} onClick={() => setDeleteTarget({ kind: 'document', id: doc.id, label: doc.filename })}><Trash2 size={14} /> Delete</button></div></div></article>)}</Collection>}
        {view === 'history' && <Collection title="Conversation history" subtitle="Your conversations are saved locally and can be reopened anytime.">{sessions.length ? sessions.map((session) => <div className="history-row" key={session.session_id}><button className="history-card" disabled={busy || deleting} onClick={() => void openConversation(session.session_id)}><strong>{session.title}</strong><span>{new Date(session.updated_at).toLocaleString()}</span><ChevronRight size={17} /></button><button className="history-delete delete-button" type="button" disabled={busy || deleting} onClick={() => setDeleteTarget({ kind: 'conversation', id: session.session_id, label: session.title })} aria-label={`Delete conversation ${session.title}`}><Trash2 size={16} /> Delete</button></div>) : <Empty text="Your conversations will appear here after you send a message." />}</Collection>}
      </main>
      {deleteTarget && <div className="confirm-backdrop" onClick={(event) => { if (event.target === event.currentTarget && !deleting) setDeleteTarget(undefined) }}><div className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description" onKeyDown={(event) => { if (event.key === 'Escape' && !deleting) setDeleteTarget(undefined) }}><h2 id="delete-title">Delete {deleteTarget.kind}?</h2><p id="delete-description"><strong>{deleteTarget.label}</strong> {deleteTarget.kind === 'document' ? 'and its searchable text will be removed from the local vault. Future chats cannot retrieve it, but existing conversations and their saved source excerpts will remain.' : 'and its messages, related actions, and reminders will be permanently removed.'} This cannot be undone.</p><div className="confirm-actions"><button type="button" autoFocus disabled={deleting} onClick={() => setDeleteTarget(undefined)}>Cancel</button><button type="button" className="confirm-delete" disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? 'Deleting…' : 'Delete permanently'}</button></div></div></div>}
    </div>
  )
}

const viewTitles: Record<View, string> = { chat: 'Good morning', actions: 'Action inbox', vault: 'Document vault', history: 'Conversation history' }

function toChatMessage(message: StoredMessage): ChatMessage {
  return {
    id: message.id, role: message.role, content: message.content, turnId: message.turn_id,
    createdAt: message.created_at, responseTimeMs: message.response_time_ms,
    sources: message.metadata.sources, actionCards: message.metadata.action_cards,
    generatedBy: message.metadata.generated_by,
  }
}

function mergeActions(current: ActionCard[], incoming: ActionCard[]) {
  const merged = new Map(current.map((item) => [item.id, item]))
  incoming.forEach((item) => merged.set(item.id, item))
  return Array.from(merged.values())
}

function NavButton({ icon, label, count, active, onClick }: { icon: React.ReactNode; label: string; count?: number; active: boolean; onClick: () => void }) {
  return <button className={active ? 'active' : ''} onClick={onClick}>{icon}<span>{label}</span>{count ? <b>{count}</b> : null}</button>
}

function SourceList({ sources }: { sources: Source[] }) {
  return <details className="sources"><summary>{sources.length} grounded source{sources.length === 1 ? '' : 's'}</summary><div>{sources.map((source, index) => <article key={`${source.source_id}-${index}`}><span>{index + 1}</span><div><strong>{source.title}</strong><small>{source.account_label}</small><p>{source.snippet}</p></div></article>)}</div></details>
}

function Collection({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="collection"><div className="collection-heading"><h2>{title}</h2><p>{subtitle}</p></div><div className="collection-grid">{children}</div></section>
}

function Empty({ text }: { text: string }) { return <div className="empty-state"><Sparkles /><p>{text}</p></div> }
