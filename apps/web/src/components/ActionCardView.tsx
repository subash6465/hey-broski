'use client'

import { useState } from 'react'
import { Check, Clock3, Mail, X } from 'lucide-react'
import { request } from '@/lib/api'
import type { ActionCard, ActionDetails } from '@/lib/types'

type Props = {
  card: ActionCard
  busy?: boolean
  onDecision: (card: ActionCard, decision: 'approve' | 'dismiss', comment: string) => void | Promise<void>
}

const activityLabels: Record<string, string> = {
  mail_created: 'Card created from mail', mail_updated: 'Card updated from mail',
  mail_completed: 'Marked done from mail', approved: 'Approved', dismissed: 'Dismissed',
  created: 'Created in chat', edited: 'Edited in chat', completed: 'Marked done in chat',
  pending: 'Reopened in chat',
}

export function ActionCardView({ card, busy, onDecision }: Props) {
  const [details, setDetails] = useState<ActionDetails>()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [detailsBusy, setDetailsBusy] = useState(false)
  const [detailsError, setDetailsError] = useState<string>()
  const [draftDecision, setDraftDecision] = useState<'approve' | 'dismiss'>()
  const [comment, setComment] = useState('')
  const dueTime = card.due_at ? new Date(card.due_at).getTime() : null
  const overdue = card.status === 'pending' && dueTime !== null && dueTime < Date.now()
  const approaching = card.status === 'pending' && dueTime !== null && !overdue && dueTime - Date.now() <= 7 * 86400000
  const date = card.due_at
    ? new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(card.due_at))
    : null
  const mailCount = card.source_refs.filter(source => source.source_type === 'email').length

  async function toggleDetails() {
    if (detailsOpen) { setDetailsOpen(false); return }
    setDetailsOpen(true)
    setDetailsBusy(true)
    setDetailsError(undefined)
    try { setDetails(await request<ActionDetails>(`/api/actions/${card.id}/details`)) }
    catch (error) { setDetailsError(error instanceof Error ? error.message : 'Could not load card details') }
    finally { setDetailsBusy(false) }
  }

  async function submitDecision() {
    if (!draftDecision) return
    try { await onDecision(card, draftDecision, comment.trim()) }
    catch { return }
    setDraftDecision(undefined)
    setComment('')
    if (detailsOpen) {
      try { setDetails(await request<ActionDetails>(`/api/actions/${card.id}/details`)) } catch { /* The decision result is shown on the card. */ }
    }
  }

  return (
    <article className="action-card">
      <div className="action-topline">
        <span className={`priority priority-${card.priority}`}>{card.priority}</span>
        {overdue && <span className="priority priority-urgent">Past due · review</span>}
        {approaching && <span className="priority priority-high">Due soon</span>}
        {date && <span className="due-date"><Clock3 size={13} /> Due {date}</span>}
      </div>
      <h4>{card.title}</h4>
      <p>{card.description}</p>
      <button type="button" className="action-detail-toggle" aria-expanded={detailsOpen} onClick={() => void toggleDetails()}>
        <Mail size={13} /> {mailCount ? `View ${mailCount} related ${mailCount === 1 ? 'mail' : 'mails'} & history` : 'View card history'}
      </button>
      {detailsOpen && <div className="action-detail-panel">
        {detailsBusy && <p>Loading related mail and history…</p>}
        {detailsError && <p role="alert">{detailsError}</p>}
        {details && <>
          {!!details.mails.length && <div className="action-mail-thread"><strong>Related mail</strong>{details.mails.map(mail => (
            <details key={mail.source_id} className="action-mail-item">
              <summary><span>{mail.title}</span><small>{mail.sent_at ? new Date(mail.sent_at).toLocaleString() : ''}</small></summary>
              <div className="action-mail-content"><small>From {mail.sender || mail.account_label}{!mail.available ? ' · saved excerpt' : ''}</small><pre>{mail.body}</pre></div>
            </details>
          ))}</div>}
          {!!details.activity.length && <div className="action-activity"><strong>Card history</strong>{details.activity.map((event, index) => (
            <div key={`${event.created_at}-${index}`}><span>{activityLabels[event.event_type] ?? event.event_type}</span><small>{new Date(event.created_at).toLocaleString()}</small>
              {event.source_id && <small>Supported by {details.mails.find(mail => mail.source_id === event.source_id)?.title ?? 'related mail'}</small>}
              {event.comment && <p>“{event.comment}”</p>}
            </div>
          ))}</div>}
          {!details.mails.length && !details.activity.length && <p>No source mail or decisions recorded yet.</p>}
        </>}
      </div>}
      {card.status === 'pending' ? <>
        <div className="action-buttons">
          <button className="approve-button" disabled={busy} onClick={() => setDraftDecision('approve')}><Check size={15} /> Approve</button>
          <button className="dismiss-button" disabled={busy} onClick={() => setDraftDecision('dismiss')}><X size={15} /> Dismiss</button>
        </div>
        {draftDecision && <div className="action-decision-form">
          <label htmlFor={`decision-comment-${card.id}`}>Why are you {draftDecision === 'approve' ? 'approving' : 'dismissing'} this? <span>Optional · saved in card history</span></label>
          <textarea id={`decision-comment-${card.id}`} value={comment} maxLength={1000} onChange={event => setComment(event.target.value)} rows={2} placeholder="Add a note for later…" />
          <div><button type="button" disabled={busy} onClick={() => { setDraftDecision(undefined); setComment('') }}>Cancel</button>
            <button type="button" className="action-decision-confirm" disabled={busy} onClick={() => void submitDecision()}>{busy ? 'Saving…' : `Confirm ${draftDecision}`}</button></div>
        </div>}
      </> : <div className={`decision-state ${card.status}`}>
        {card.status === 'completed' ? card.completion_origin === 'mail' ? 'Done · confirmed by mail' : card.completion_origin === 'reminder' ? 'Approved · reminder created' : 'Done' : card.status}
      </div>}
    </article>
  )
}
