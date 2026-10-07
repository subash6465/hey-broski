'use client'

import { useMemo, useState } from 'react'
import { ActionCardView } from './ActionCardView'
import type { ActionCard } from '@/lib/types'

type StatusFilter = 'all' | 'pending' | 'approved' | 'mail_done' | 'completed' | 'dismissed'
type DueFilter = 'all' | 'past_due' | 'due_soon' | 'later' | 'no_due'
type SortOrder = 'due_soon' | 'due_late' | 'priority' | 'newest'

const rank: Record<ActionCard['priority'], number> = { urgent: 0, high: 1, medium: 2, low: 3 }
const dueTime = (card: ActionCard) => card.due_at ? new Date(card.due_at).getTime() : Infinity

export function ActionInbox({ actions, decisionBusy, onDecision }: {
  actions: ActionCard[]
  decisionBusy?: string
  onDecision: (card: ActionCard, decision: 'approve' | 'dismiss', comment: string) => Promise<void>
}) {
  const [status, setStatus] = useState<StatusFilter>('pending')
  const [priority, setPriority] = useState<ActionCard['priority'] | 'all'>('all')
  const [due, setDue] = useState<DueFilter>('all')
  const [sort, setSort] = useState<SortOrder>('due_soon')
  const now = Date.now()
  const pending = actions.filter(card => card.status === 'pending').length
  const shown = useMemo(() => actions.filter(card => {
    if (status === 'pending' && card.status !== 'pending') return false
    if (status === 'approved' && card.status !== 'approved' && !(card.status === 'completed' && card.completion_origin === 'reminder')) return false
    if (status === 'mail_done' && !(card.status === 'completed' && card.completion_origin === 'mail')) return false
    if (status === 'completed' && card.status !== 'completed') return false
    if (status === 'dismissed' && card.status !== 'dismissed') return false
    if (priority !== 'all' && card.priority !== priority) return false
    const time = dueTime(card)
    if (due === 'past_due' && !(card.status === 'pending' && time < now)) return false
    if (due === 'due_soon' && !(card.status === 'pending' && time >= now && time <= now + 7 * 86400000)) return false
    if (due === 'later' && !(time > now + 7 * 86400000 && time < Infinity)) return false
    if (due === 'no_due' && time !== Infinity) return false
    return true
  }).sort((a, b) => {
    if (sort === 'priority') return rank[a.priority] - rank[b.priority] || dueTime(a) - dueTime(b)
    if (sort === 'newest') return (b.created_at ?? '').localeCompare(a.created_at ?? '')
    if (sort === 'due_late') return (dueTime(b) === Infinity ? -1 : dueTime(a) === Infinity ? 1 : dueTime(b) - dueTime(a))
    return dueTime(a) - dueTime(b) || rank[a.priority] - rank[b.priority]
  }), [actions, status, priority, due, sort, now])

  return <section className="collection action-inbox">
    <div className="collection-heading"><span className="section-label">ACTION INBOX</span><h2>{pending === 1 ? '1 item needs a decision' : `${pending} items need a decision`}</h2><p>Review tasks, related mail, and past decisions in one place.</p></div>
    <div className="action-filters" aria-label="Filter and sort action cards">
      <label>Status<select value={status} onChange={event => setStatus(event.target.value as StatusFilter)}>
        <option value="pending">To review</option><option value="all">All cards</option><option value="approved">Approved</option>
        <option value="mail_done">Done from mail</option><option value="completed">All done</option><option value="dismissed">Dismissed</option>
      </select></label>
      <label>Priority<select value={priority} onChange={event => setPriority(event.target.value as ActionCard['priority'] | 'all')}>
        <option value="all">All priorities</option><option value="urgent">Urgent</option><option value="high">High</option>
        <option value="medium">Medium</option><option value="low">Low</option>
      </select></label>
      <label>Due date<select value={due} onChange={event => setDue(event.target.value as DueFilter)}>
        <option value="all">Any date</option><option value="past_due">Past due</option><option value="due_soon">Next 7 days</option>
        <option value="later">Later</option><option value="no_due">No due date</option>
      </select></label>
      <label>Sort<select value={sort} onChange={event => setSort(event.target.value as SortOrder)}>
        <option value="due_soon">Due date · earliest</option><option value="due_late">Due date · latest</option>
        <option value="priority">Priority</option><option value="newest">Newest cards</option>
      </select></label>
    </div>
    <div className="action-results-count">Showing {shown.length} of {actions.length} cards</div>
    <div className="collection-grid">{shown.length ? shown.map(card => <ActionCardView key={card.id} card={card} busy={decisionBusy === card.id} onDecision={onDecision} />)
      : <div className="empty-state"><p>{actions.length ? 'No cards match these filters.' : 'Action cards appear here as mail processing finds tasks.'}</p>
          {actions.length > 0 && <button type="button" onClick={() => { setStatus('all'); setPriority('all'); setDue('all') }}>Show all cards</button>}</div>}</div>
  </section>
}
