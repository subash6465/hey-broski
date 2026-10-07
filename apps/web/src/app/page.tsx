'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import {
  ArrowUpRight,
  BookOpen,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileText,
  House,
  Menu,
  MessageCircle,
  MessageSquarePlus,
  Mail,
  RefreshCw,
  History,
  Paperclip,
  Send,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { ActionCardView } from '@/components/ActionCardView'
import { ActionInbox } from '@/components/ActionInbox'
import { LocalDateTime } from '@/components/LocalDateTime'
import { Onboarding, type OnboardingState } from '@/components/Onboarding'
import { MailImportProgress } from '@/components/MailImportProgress'
import { MailAccountCard } from '@/components/MailAccountCard'
import { request, streamChat, type ChatStreamEvent } from '@/lib/api'
import type { ActionCard, ChatMessage, ChatSession, DocumentRecord, Source, StoredMessage } from '@/lib/types'

type View = 'desk' | 'chat' | 'actions' | 'vault' | 'history' | 'accounts'
type DeleteTarget = { kind: 'conversation' | 'document'; id: string; label: string }
type Health = { status: string; mode: string; inference_enabled: boolean; services: { database: string; ollama: string }; model: string }
type MailPipeline = { searchable_messages: number; embedded_messages: number; pending_embedding_chunks: number; imported_messages: number; processed_messages: number; discovered_messages: number; action_messages_total: number; action_messages_processed: number; action_messages_failed: number }

const prompts = [
  { label: 'Daily brief', text: 'What needs my attention this week?' },
  { label: 'Waiting on me', text: 'Who is waiting on me?' },
]

const welcome: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: "Hey, I'm Broski. Ask for a brief, check who needs a reply, or search a document in your local library.",
}

export default function Home() {
  const [onboarding, setOnboarding] = useState<OnboardingState | null>()
  const [showSetup, setShowSetup] = useState(() => typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('setup'))
  const [setupStep, setSetupStep] = useState<'profile' | 'connections' | 'sync'>(() => {
    if (typeof window === 'undefined') return 'connections'
    const requested = new URLSearchParams(window.location.search).get('setup')
    return requested === 'profile' || requested === 'sync' ? requested : 'connections'
  })
  const [accountJobs, setAccountJobs] = useState<OnboardingState['sync_jobs']>({})
  const [accountPipelines, setAccountPipelines] = useState<Record<string, MailPipeline>>({})
  const [accountBusy, setAccountBusy] = useState<string>()
  const [view, setView] = useState<View>('desk')
  const [mobileNav, setMobileNav] = useState(false)
  const [sessionId, setSessionId] = useState<string>()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([welcome])
  const [sendingMessageId, setSendingMessageId] = useState<string>()
  const [selectedSources, setSelectedSources] = useState<Source[] | null>(null)
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
    void request<OnboardingState>('/api/onboarding').then(setOnboarding).catch(() => setOnboarding(null))
  }, [])

  useEffect(() => {
    if (!onboarding?.ready || showSetup) return
    async function pollAccounts() {
      try {
        const result = await request<{ accounts: OnboardingState['accounts'] }>('/api/accounts')
        setOnboarding(current => current ? { ...current, accounts: result.accounts } : current)
        const entries = await Promise.all(result.accounts.map(async account => {
          const status = await request<{ job: NonNullable<OnboardingState['sync_jobs'][string]> | null; pipeline: MailPipeline }>(`/api/accounts/${account.id}/sync`)
          return [account.id, status] as const
        }))
        setAccountJobs(Object.fromEntries(entries.map(([id, status]) => [id, status.job])))
        setAccountPipelines(Object.fromEntries(entries.map(([id, status]) => [id, status.pipeline])))
        setActions(await request<ActionCard[]>('/api/actions'))
      } catch { /* Account status is advisory; the workspace remains usable. */ }
    }
    void pollAccounts()
    const interval = window.setInterval(() => void pollAccounts(), 4_000)
    return () => window.clearInterval(interval)
  }, [onboarding?.ready, showSetup])

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

  useEffect(() => {
    if (!selectedSources) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelectedSources(null) }
    window.addEventListener('keydown', closeOnEscape)
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener('keydown', closeOnEscape) }
  }, [selectedSources])

  async function sendMessage(event?: FormEvent, selectedPrompt?: string) {
    event?.preventDefault()
    const text = (selectedPrompt ?? input).trim()
    if (!text || busy) return
    const fromDesk = view === 'desk'
    setView('chat')
    setError(undefined)
    setNotice(undefined)
    setBusy(true)
    setStreamingText('')
    setStatusText('')
    const pendingId = crypto.randomUUID()
    setSendingMessageId(pendingId)
    if (fromDesk) {
      setSessionId(undefined)
      setMessages([welcome, { id: pendingId, role: 'user', content: text }])
    } else {
      setMessages((current) => [...current, { id: pendingId, role: 'user', content: text }])
    }
    setInput('')
    try {
      let activeSession = fromDesk ? undefined : sessionId
      if (!activeSession) {
        const session = await request<{ session_id: string }>(
          '/api/chat/sessions',
          { method: 'POST' },
          15_000,
        )
        activeSession = session.session_id
        setSessionId(activeSession)
      }
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
      try { setActions(await request<ActionCard[]>('/api/actions')) } catch { /* Chat result is already saved. */ }
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
      setSendingMessageId(undefined)
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

  async function decide(card: ActionCard, decision: 'approve' | 'dismiss', comment: string) {
    setDecisionBusy(card.id)
    setError(undefined)
    try {
      const updated = await request<ActionCard>(`/api/actions/${card.id}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, comment }),
      })
      setActions((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMessages((current) => current.map((message) => ({
        ...message,
        actionCards: message.actionCards?.map((item) => item.id === updated.id ? updated : item),
      })))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update the action')
      throw caught
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
      if (next === 'desk' || next === 'actions') setActions(await request<ActionCard[]>('/api/actions'))
      if (next === 'vault') setDocuments(await request<DocumentRecord[]>('/api/documents'))
      if (next === 'history') setSessions((await request<{ sessions: ChatSession[] }>('/api/chat/sessions')).sessions)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load this view')
    }
  }

  async function syncAccount(id: string) {
    setAccountBusy(id)
    try {
      const result = await request<{ status: string }>(`/api/accounts/${id}/sync`, { method: 'POST' })
      setAccountJobs(current => ({ ...current, [id]: { ...(current[id] ?? onboarding?.sync_jobs[id] ?? { processed_count: 0, skipped_count: 0, total_estimate: null, discovery_complete: 0 }), status: result.status === 'resumed' ? 'complete' : 'running', error: null } }))
      setNotice(result.status === 'resumed' ? 'Mail processing resumed.' : 'Mailbox sync started.')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not start sync') }
    finally { setAccountBusy(undefined) }
  }

  async function controlSync(id: string, action: 'pause' | 'cancel') {
    setAccountBusy(id)
    try {
      await request(`/api/accounts/${id}/sync/${action}`, { method: 'POST' })
      setAccountJobs(current => { const job = current[id] ?? onboarding?.sync_jobs[id]; return { ...current, [id]: job ? { ...job, status: action === 'pause' ? job.status === 'complete' ? 'paused_processing' : 'paused' : 'canceled' } : null } })
      setNotice(action === 'pause' ? 'Import paused. Resume whenever you are ready.' : 'Import canceled. Already imported mail remains searchable.')
    } catch (caught) { setError(caught instanceof Error ? caught.message : `Could not ${action} sync`) }
    finally { setAccountBusy(undefined) }
  }

  async function deleteMailData(id: string) {
    if (!window.confirm('Delete all imported mail and embeddings for this account? The account stays connected. Mail-sourced chat turns are removed; conversations without recorded mail sources may still contain copied excerpts. This cannot be undone.')) return
    setAccountBusy(id)
    try {
      await request(`/api/accounts/${id}/mail-data`, { method: 'DELETE' })
      const next = await request<OnboardingState>('/api/onboarding')
      setOnboarding(next)
      setAccountJobs(next.sync_jobs)
      setAccountPipelines(current => ({ ...current, [id]: { searchable_messages: 0, embedded_messages: 0, pending_embedding_chunks: 0, imported_messages: 0, processed_messages: 0, discovered_messages: 0, action_messages_total: 0, action_messages_processed: 0, action_messages_failed: 0 } }))
      setNotice('Imported mail and embeddings deleted. The account remains connected.')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not delete imported mail') }
    finally { setAccountBusy(undefined) }
  }

  async function disconnectAccount(id: string) {
    if (!window.confirm('Disconnect this mailbox and remove its imported mail and pending actions? Existing conversations may still contain saved answers and source excerpts; delete those conversations separately if needed.')) return
    setAccountBusy(id)
    try {
      await request(`/api/accounts/${id}`, { method: 'DELETE' })
      const next = await request<OnboardingState>('/api/onboarding')
      setOnboarding(next)
      if (!next.ready) { setSetupStep('connections'); setShowSetup(true) }
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not disconnect mailbox') }
    finally { setAccountBusy(undefined) }
  }

  const pendingCount = actions.filter((action) => action.status === 'pending').length
  const pendingActions = actions.filter((action) => action.status === 'pending')
  const firstAction = pendingActions[0]
  const visibleSyncAccounts = onboarding?.accounts.filter(account => {
    const job = accountJobs[account.id] ?? onboarding.sync_jobs[account.id]
    return (!account.last_synced_at && job?.status !== 'canceled') || job?.status === 'running' || job?.status === 'paused' || job?.status === 'paused_processing' || job?.status === 'failed' ||
      (account.provider === 'gmail' && (accountPipelines[account.id]?.pending_embedding_chunks ?? 0) > 0) ||
      (accountPipelines[account.id]?.action_messages_processed ?? 0) < (accountPipelines[account.id]?.action_messages_total ?? 0)
  }) ?? []

  if (onboarding === undefined) return <div className="onboarding-shell"><div className="onboarding-header"><div className="onboarding-brand"><Sparkles size={21} /> hey broski<span>.</span></div></div><p>Opening your local workspace…</p></div>
  if (onboarding === null) return <div className="onboarding-shell"><div className="onboarding-card"><h1>Could not open setup</h1><p>Check that the local API is running, then reload this page.</p><button className="onboarding-primary" onClick={() => window.location.reload()}>Retry</button></div></div>
  if (!onboarding.ready || showSetup) return <Onboarding initial={onboarding} initialStep={showSetup && onboarding.profile_complete ? setupStep : undefined} editing={showSetup && onboarding.ready} onCancel={() => { setShowSetup(false); window.history.replaceState({}, '', '/') }} onComplete={next => { setOnboarding(next); setAccountJobs(next.sync_jobs); setView('desk'); setShowSetup(false); window.history.replaceState({}, '', '/') }} />

  return (
    <div className="app-shell">
      <button className="mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu /></button>
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="brand"><div className="brand-mark"><Sparkles size={20} /></div><span>hey broski<span className="brand-dot">.</span></span></div>
        <button className="sidebar-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X /></button>
        <nav>
          <NavButton icon={<House />} label="My desk" active={view === 'desk'} onClick={() => void switchView('desk')} />
          <NavButton icon={<MessageCircle />} label="Chat" active={view === 'chat'} onClick={() => void switchView('chat')} />
          <NavButton icon={<CheckCircle2 />} label="To review" count={pendingCount} active={view === 'actions'} onClick={() => void switchView('actions')} />
          <NavButton icon={<BookOpen />} label="Library" active={view === 'vault'} onClick={() => void switchView('vault')} />
          <NavButton icon={<Mail />} label="Accounts" active={view === 'accounts'} onClick={() => void switchView('accounts')} />
        </nav>
        <button className="new-chat" onClick={newConversation} disabled={busy}><MessageSquarePlus size={16} /> New conversation</button>
        <button className={`history-link ${view === 'history' ? 'active' : ''}`} onClick={() => void switchView('history')}><History size={16} /> History</button>
        <div className="sidebar-footer">
          <div className="privacy-note"><span className="privacy-dot" /><div><strong>Local workspace</strong><span>Private by default</span></div></div>
        </div>
      </aside>
      {mobileNav && <button className="nav-overlay" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}

      <main className="workspace">
        <header className="topbar">
          <div className="topbar-path"><span>{viewTitles[view]}</span><span className="path-divider">/</span>{view === 'desk' ? <LocalDateTime /> : <span>HEY BROSKI</span>}</div>
          <div className="status-cluster">
            <span className="mode-badge"><span className="status-dot" /> {!health ? 'Connecting...' : onboarding.accounts.length ? `${onboarding.accounts.length} connected` : 'Local workspace'}</span>
            <span className="model-label">{!health ? 'Checking local model' : !health.inference_enabled ? 'Local model disabled' : health.services.ollama === 'available' ? `Local model: ${health.model}` : health.services.ollama.startsWith('model_missing:') ? `Model not ready: ${health.model}` : 'Local model offline'}</span>
          </div>
        </header>
        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError(undefined)}><X size={16} /></button></div>}
        {notice && <div className="notice-banner" role="status"><span>{notice}</span><button onClick={() => setNotice(undefined)}><X size={16} /></button></div>}
        {!!visibleSyncAccounts.length && <section className="import-progress" aria-label="Mail import progress"><div className="import-progress-heading"><RefreshCw size={16} /><div><strong>Bringing your mail in</strong><span>Imported mail is searchable while processing continues. Answers may be incomplete until import finishes.</span></div></div>{visibleSyncAccounts.map(account => <MailImportProgress key={account.id} account={account} job={accountJobs[account.id] ?? onboarding.sync_jobs[account.id]} pipeline={accountPipelines[account.id]} busy={accountBusy === account.id} onResume={() => void syncAccount(account.id)} onPause={() => void controlSync(account.id, 'pause')} onCancel={() => void controlSync(account.id, 'cancel')} />)}</section>}

        <div className="workspace-view" key={view}>
        {view === 'desk' && <section className="desk" aria-label="My desk">
          <div className="desk-intro"><p className="section-label">A LITTLE CLARITY FOR TODAY</p><h1>Hey, {onboarding.profile?.first_name ?? 'there'} <Sparkles aria-hidden="true" /></h1><p>Here&apos;s what&apos;s worth a look. The rest can wait.</p></div>
          <div className="desk-cards">
            <section className="glass-card brief-card" aria-label="Your brief"><div className="card-kicker"><span>YOUR BRIEF</span><span>01 / 02</span></div><h2>Today, at a glance.</h2>
              {pendingActions.length ? pendingActions.slice(0, 2).map((action) => <button className="brief-row" type="button" key={action.id} onClick={() => void switchView('actions')}><span className="brief-icon"><ArrowUpRight size={15} /></span><span className="brief-copy"><strong>{action.title}</strong><small>{action.description}</small></span><span className="brief-source">{action.source_refs[0]?.source_type ?? 'ACTION'}</span></button>) : <><button className="brief-row" type="button" onClick={() => void sendMessage(undefined, 'Who is waiting on me?')}><span className="brief-icon"><ArrowUpRight size={15} /></span><span className="brief-copy"><strong>Find follow-ups</strong><small>Ask who is waiting on you</small></span><span className="brief-source">ASK</span></button><button className="brief-row" type="button" onClick={() => void sendMessage(undefined, 'Show upcoming renewals and deadlines')}><span className="brief-icon"><Clock3 size={15} /></span><span className="brief-copy"><strong>Check upcoming dates</strong><small>Look for renewals and deadlines</small></span><span className="brief-source">ASK</span></button></>}
              <button className="text-link" type="button" onClick={() => void switchView('actions')}>See everything <ArrowUpRight size={14} /></button>
            </section>
            <section className="glass-card review-card" aria-label="Suggestions for review"><div className="card-kicker"><span>NEEDS YOUR OKAY</span><span>{pendingCount} TO REVIEW</span></div><div className="review-orb"><Sparkles size={22} /></div><h2>{firstAction ? 'A suggestion is ready when you are.' : 'You call the shots.'}</h2><p>{firstAction ? firstAction.description : 'Ask Broski for a brief. Any suggested next steps will appear here for your review.'}</p><button className="primary-button" type="button" onClick={() => firstAction ? void switchView('actions') : void sendMessage(undefined, 'What needs my attention this week?')}>{firstAction ? 'Review suggestion' : 'Get my brief'} <ArrowUpRight size={16} /></button><small>Suggested actions wait for your approval.</small></section>
          </div>
          <form className="desk-ask" onSubmit={sendMessage}><label htmlFor="desk-input" className="section-label">ASK BROSKI</label><h2>What&apos;s on your mind?</h2><div className="desk-input"><input id="desk-input" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about your day, a document, or what's next..." disabled={busy} /><button type="submit" aria-label="Send message" disabled={!input.trim() || busy}><ArrowUpRight size={19} /></button></div><div className="desk-prompts"><span>Try:</span><button type="button" disabled={busy} onClick={() => void sendMessage(undefined, 'Who is waiting on me?')}>Who&apos;s waiting on me?</button><button type="button" disabled={busy} onClick={() => void sendMessage(undefined, 'Show my deadlines')}>Show my deadlines</button></div></form>
        </section>}

        {view === 'chat' && (
          <section className="chat-layout">
            <div className="messages">
              {messages.map((message) => (
                <div className={`message-row ${message.role} ${message.id === sendingMessageId ? 'message-sending' : ''}`} key={message.id}>
                  {message.role === 'assistant' && <div className="bot-avatar"><Bot size={17} /></div>}
                  <div className="message-wrap">
                    <div className="message-bubble"><p>{message.content}</p></div>
                    {message.generatedBy && <span className="generated-by">{message.generatedBy === 'ollama' ? `Answered by local model (${health?.model ?? 'Ollama'})` : message.generatedBy === 'agent' ? 'Answered with local search tools' : message.generatedBy === 'metadata' ? 'Answered from mail metadata' : 'Mailbox coverage notice'}</span>}
                    {!!message.sources?.length && <SourceList sources={message.sources} onOpen={() => setSelectedSources(message.sources ?? null)} />}
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

        {view === 'actions' && <ActionInbox actions={actions} decisionBusy={decisionBusy} onDecision={decide} />}
        {view === 'vault' && <Collection eyebrow="YOUR LIBRARY" title="Your local documents" subtitle="PDF, text, Markdown, and CSV files are searchable from chat."><label className="upload-card"><Upload size={22} /><strong>{uploading ? 'Uploading…' : 'Upload a document'}</strong><span>Maximum 10 MB</span><input type="file" disabled={uploading} accept=".pdf,.txt,.md,.csv" onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; void upload(file) }} /></label>{documents.map((doc) => <article className="document-card" key={doc.id}><FileText /><div><strong>{doc.filename}</strong><span>{Math.ceil(doc.size_bytes / 1024)} KB · {new Date(doc.created_at).toLocaleDateString()}</span><p>{doc.preview}</p><div className="document-actions"><button type="button" onClick={() => { setInput(`What does ${doc.filename} say about `); setView('chat') }}>Ask about this file</button><button type="button" className="delete-button" disabled={busy || uploading || deleting} onClick={() => setDeleteTarget({ kind: 'document', id: doc.id, label: doc.filename })}><Trash2 size={14} /> Delete</button></div></div></article>)}</Collection>}
        {view === 'history' && <Collection eyebrow="PAST CONVERSATIONS" title="Conversation history" subtitle="Your conversations are saved locally and can be reopened anytime.">{sessions.length ? sessions.map((session) => <div className="history-row" key={session.session_id}><button className="history-card" disabled={busy || deleting} onClick={() => void openConversation(session.session_id)}><strong>{session.title}</strong><span>{new Date(session.updated_at).toLocaleString()}</span><ChevronRight size={17} /></button><button className="history-delete delete-button" type="button" disabled={busy || deleting} onClick={() => setDeleteTarget({ kind: 'conversation', id: session.session_id, label: session.title })} aria-label={`Delete conversation ${session.title}`}><Trash2 size={16} /> Delete</button></div>) : <Empty text="Your conversations will appear here after you send a message." />}</Collection>}
        {view === 'accounts' && <Collection eyebrow="CONNECTED MAIL" title="Your accounts" subtitle="Your mail is imported and stored on this computer. Manage each connection and its sync here."><button className="account-add" onClick={() => { window.history.replaceState({}, '', '/?setup=connections'); setSetupStep('connections'); setShowSetup(true) }}>Connect another account <ArrowUpRight size={16} /></button><button className="account-add" onClick={() => { window.history.replaceState({}, '', '/?setup=sync'); setSetupStep('sync'); setShowSetup(true) }} disabled={onboarding.accounts.some(account => accountJobs[account.id]?.status === 'running')}>Change import and sync settings <ArrowUpRight size={16} /></button><button className="account-add" onClick={() => { window.history.replaceState({}, '', '/?setup=profile'); setSetupStep('profile'); setShowSetup(true) }}>Edit profile <ArrowUpRight size={16} /></button>{onboarding.accounts.map(account => <MailAccountCard key={account.id} account={account} job={accountJobs[account.id] ?? onboarding.sync_jobs[account.id]} pendingChunks={accountPipelines[account.id]?.pending_embedding_chunks ?? 0} busy={accountBusy === account.id} onSync={() => void syncAccount(account.id)} onPause={() => void controlSync(account.id, 'pause')} onCancel={() => void controlSync(account.id, 'cancel')} onDelete={() => void deleteMailData(account.id)} onDisconnect={() => void disconnectAccount(account.id)} />)}</Collection>}
        </div>
      </main>
      {selectedSources && <SourceDialog sources={selectedSources} onClose={() => setSelectedSources(null)} />}
      {deleteTarget && <div className="confirm-backdrop" onClick={(event) => { if (event.target === event.currentTarget && !deleting) setDeleteTarget(undefined) }}><div className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description" onKeyDown={(event) => { if (event.key === 'Escape' && !deleting) setDeleteTarget(undefined) }}><h2 id="delete-title">Delete {deleteTarget.kind}?</h2><p id="delete-description"><strong>{deleteTarget.label}</strong> {deleteTarget.kind === 'document' ? 'and its searchable text will be removed from the local vault. Future chats cannot retrieve it, but existing conversations and their saved source excerpts will remain.' : 'and its messages, related actions, and reminders will be permanently removed.'} This cannot be undone.</p><div className="confirm-actions"><button type="button" autoFocus disabled={deleting} onClick={() => setDeleteTarget(undefined)}>Cancel</button><button type="button" className="confirm-delete" disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? 'Deleting…' : 'Delete permanently'}</button></div></div></div>}
    </div>
  )
}

const viewTitles: Record<View, string> = { desk: 'MY DESK', chat: 'CHAT', actions: 'TO REVIEW', vault: 'LIBRARY', history: 'HISTORY', accounts: 'ACCOUNTS' }

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

function SourceList({ sources, onOpen }: { sources: Source[]; onOpen: () => void }) {
  return <button type="button" className="sources-trigger" onClick={onOpen}><BookOpen size={14} /> {sources.length} grounded source{sources.length === 1 ? '' : 's'} <ChevronRight size={14} /></button>
}

function SourceDialog({ sources, onClose }: { sources: Source[]; onClose: () => void }) {
  const [expanded, setExpanded] = useState<number[]>([])
  return <div className="source-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="source-dialog" role="dialog" aria-modal="true" aria-labelledby="source-dialog-title" onKeyDown={event => {
      if (event.key !== 'Tab') return
      const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not([disabled])')
      if (!buttons.length) return
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}>
      <header><div><span className="section-label">ANSWER REFERENCES</span><h2 id="source-dialog-title">Grounded sources</h2><p>{sources.length} source{sources.length === 1 ? '' : 's'} used in this answer</p></div><button type="button" aria-label="Close sources" autoFocus onClick={onClose}><X size={18} /></button></header>
      <div className="source-dialog-scroll">{sources.map((source, index) => <article key={`${source.source_id}-${index}`}><span className="source-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{source.title}</strong><small>{source.account_label}{source.timestamp ? ` · ${new Date(source.timestamp).toLocaleDateString()}` : ''}</small><p className={source.snippet.length > 300 && !expanded.includes(index) ? 'source-snippet-preview' : ''}>{source.snippet}</p>{source.snippet.length > 300 && <button className="source-expand" type="button" onClick={() => setExpanded(current => current.includes(index) ? current.filter(item => item !== index) : [...current, index])}>{expanded.includes(index) ? 'Show less' : 'Read full excerpt'}</button>}</div></article>)}</div>
    </section>
  </div>
}

function Collection({ eyebrow, title, subtitle, children }: { eyebrow: string; title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="collection"><div className="collection-heading"><span className="section-label">{eyebrow}</span><h2>{title}</h2><p>{subtitle}</p></div><div className="collection-grid">{children}</div></section>
}

function Empty({ text }: { text: string }) { return <div className="empty-state"><Sparkles /><p>{text}</p></div> }
