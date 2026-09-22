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
  Paperclip,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from 'lucide-react'
import { ActionCardView } from '@/components/ActionCardView'
import { request } from '@/lib/api'
import type { ActionCard, ChatMessage, DocumentRecord, Source } from '@/lib/types'

type View = 'chat' | 'actions' | 'vault' | 'audit'
type Health = { status: string; mode: string; services: { database: string; ollama: string }; model: string }
type AuditEvent = { id: string; event_type: string; entity_id?: string; details: Record<string, unknown>; created_at: string }

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
  const [messages, setMessages] = useState<ChatMessage[]>([welcome])
  const [actions, setActions] = useState<ActionCard[]>([])
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [health, setHealth] = useState<Health>()
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [decisionBusy, setDecisionBusy] = useState<string>()
  const [error, setError] = useState<string>()
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    async function initialize() {
      try {
        const [session, status, currentActions, docs] = await Promise.all([
          request<{ session_id: string }>('/api/chat/sessions', { method: 'POST' }),
          request<Health>('/api/health'),
          request<ActionCard[]>('/api/actions'),
          request<DocumentRecord[]>('/api/documents'),
        ])
        setSessionId(session.session_id)
        setHealth(status)
        setActions(currentActions)
        setDocuments(docs)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Could not connect to the API')
      }
    }
    void initialize()
  }, [])

  useEffect(() => bottom.current?.scrollIntoView({ behavior: 'smooth' }), [messages, busy])

  async function sendMessage(event?: FormEvent, selectedPrompt?: string) {
    event?.preventDefault()
    const text = (selectedPrompt ?? input).trim()
    if (!text || !sessionId || busy) return
    setInput('')
    setError(undefined)
    setBusy(true)
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', content: text }])
    try {
      const response = await request<{
        message_id: string
        content: string
        sources: Source[]
        action_cards: ActionCard[]
        generated_by: 'demo' | 'ollama'
      }>(`/api/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      setMessages((current) => [...current, {
        id: response.message_id,
        role: 'assistant',
        content: response.content,
        sources: response.sources,
        actionCards: response.action_cards,
        generatedBy: response.generated_by,
      }])
      setActions((current) => mergeActions(current, response.action_cards))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Message failed')
    } finally {
      setBusy(false)
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
    if (!file) return
    setBusy(true)
    setError(undefined)
    try {
      const form = new FormData()
      form.append('file', file)
      const document = await request<DocumentRecord>('/api/documents', { method: 'POST', body: form })
      setDocuments((current) => [document, ...current])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  async function switchView(next: View) {
    setView(next)
    setMobileNav(false)
    if (next === 'actions') setActions(await request<ActionCard[]>('/api/actions'))
    if (next === 'vault') setDocuments(await request<DocumentRecord[]>('/api/documents'))
    if (next === 'audit') setAudit((await request<{ events: AuditEvent[] }>('/api/audit')).events)
  }

  const pendingCount = actions.filter((action) => action.status === 'pending').length

  return (
    <div className="app-shell">
      <button className="mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu /></button>
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="brand"><div className="brand-mark"><Sparkles size={20} /></div><span>Hey Broski</span></div>
        <button className="sidebar-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X /></button>
        <button className="new-chat" onClick={() => window.location.reload()}><MessageSquarePlus size={17} /> New conversation</button>
        <nav>
          <NavButton icon={<Inbox />} label="Chat" active={view === 'chat'} onClick={() => void switchView('chat')} />
          <NavButton icon={<CheckCircle2 />} label="Action inbox" count={pendingCount} active={view === 'actions'} onClick={() => void switchView('actions')} />
          <NavButton icon={<Archive />} label="Document vault" active={view === 'vault'} onClick={() => void switchView('vault')} />
          <NavButton icon={<ShieldCheck />} label="Audit log" active={view === 'audit'} onClick={() => void switchView('audit')} />
        </nav>
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
            <span className="mode-badge"><span className="status-dot" /> {health?.mode === 'demo' ? 'Demo mode' : 'Connected'}</span>
            <span className="model-label">{health?.services.ollama === 'available' ? health.model : 'Reliable fallback'}</span>
          </div>
        </header>
        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError(undefined)}><X size={16} /></button></div>}

        {view === 'chat' && (
          <section className="chat-layout">
            <div className="messages">
              {messages.map((message) => (
                <div className={`message-row ${message.role}`} key={message.id}>
                  {message.role === 'assistant' && <div className="bot-avatar"><Bot size={17} /></div>}
                  <div className="message-wrap">
                    <div className="message-bubble"><p>{message.content}</p></div>
                    {message.generatedBy && <span className="generated-by">Answered by {message.generatedBy === 'ollama' ? health?.model : 'grounded demo engine'}</span>}
                    {!!message.sources?.length && <SourceList sources={message.sources} />}
                    {!!message.actionCards?.length && <div className="inline-actions">{message.actionCards.map((card) => <ActionCardView key={card.id} card={card} busy={decisionBusy === card.id} onDecision={decide} />)}</div>}
                  </div>
                </div>
              ))}
              {messages.length === 1 && <div className="prompt-grid">{prompts.map((prompt) => <button key={prompt.label} onClick={() => void sendMessage(undefined, prompt.text)}><span>{prompt.label}</span><p>{prompt.text}</p><ChevronRight size={16} /></button>)}</div>}
              {busy && <div className="message-row assistant"><div className="bot-avatar"><Bot size={17} /></div><div className="typing"><i /><i /><i /></div></div>}
              <div ref={bottom} />
            </div>
            <form className="composer" onSubmit={sendMessage}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage() } }} placeholder="Ask what needs your attention…" rows={1} disabled={!sessionId || busy} />
              <label className="attach" title="Upload a document"><Paperclip size={19} /><input type="file" accept=".pdf,.txt,.md,.csv" onChange={(event) => void upload(event.target.files?.[0])} /></label>
              <button className="send-button" disabled={!input.trim() || !sessionId || busy}><Send size={18} /></button>
              <span className="composer-note">Sources are cited. Actions always require approval.</span>
            </form>
          </section>
        )}

        {view === 'actions' && <Collection title={`${pendingCount} items need a decision`} subtitle="Review every proposed action before anything changes.">{actions.length ? actions.map((card) => <ActionCardView key={card.id} card={card} busy={decisionBusy === card.id} onDecision={decide} />) : <Empty text="Ask for your daily brief to generate action cards." />}</Collection>}
        {view === 'vault' && <Collection title="Your local documents" subtitle="PDF, text, Markdown, and CSV files are searchable from chat."><label className="upload-card"><Upload size={22} /><strong>Upload a document</strong><span>Maximum 10 MB</span><input type="file" accept=".pdf,.txt,.md,.csv" onChange={(event) => void upload(event.target.files?.[0])} /></label>{documents.map((doc) => <article className="document-card" key={doc.id}><FileText /><div><strong>{doc.filename}</strong><span>{Math.ceil(doc.size_bytes / 1024)} KB · {new Date(doc.created_at).toLocaleDateString()}</span><p>{doc.preview}</p></div></article>)}</Collection>}
        {view === 'audit' && <Collection title="Transparent by design" subtitle="Chat, upload, and approval decisions are recorded locally.">{audit.length ? audit.map((event) => <article className="audit-row" key={event.id}><div className="audit-icon"><ShieldCheck size={16} /></div><div><strong>{event.event_type.replaceAll('.', ' ')}</strong><span>{new Date(event.created_at).toLocaleString()}</span></div></article>) : <Empty text="No recorded activity yet." />}</Collection>}
      </main>
    </div>
  )
}

const viewTitles: Record<View, string> = { chat: 'Good morning', actions: 'Action inbox', vault: 'Document vault', audit: 'Audit log' }

function mergeActions(current: ActionCard[], incoming: ActionCard[]) {
  const merged = new Map(current.map((item) => [item.id, item]))
  incoming.forEach((item) => merged.set(item.id, item))
  return Array.from(merged.values())
}

function NavButton({ icon, label, count, active, onClick }: { icon: React.ReactNode; label: string; count?: number; active: boolean; onClick: () => void }) {
  return <button className={active ? 'active' : ''} onClick={onClick}>{icon}<span>{label}</span>{count ? <b>{count}</b> : null}</button>
}

function SourceList({ sources }: { sources: Source[] }) {
  return <details className="sources"><summary>{sources.length} grounded source{sources.length === 1 ? '' : 's'}</summary><div>{sources.map((source, index) => <article key={source.source_id}><span>{index + 1}</span><div><strong>{source.title}</strong><small>{source.account_label}</small><p>{source.snippet}</p></div></article>)}</div></details>
}

function Collection({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="collection"><div className="collection-heading"><h2>{title}</h2><p>{subtitle}</p></div><div className="collection-grid">{children}</div></section>
}

function Empty({ text }: { text: string }) { return <div className="empty-state"><Sparkles /><p>{text}</p></div> }
