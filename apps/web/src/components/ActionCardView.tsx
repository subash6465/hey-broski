import { Check, Clock3, ExternalLink, X } from 'lucide-react'
import type { ActionCard } from '@/lib/types'

type Props = {
  card: ActionCard
  busy?: boolean
  onDecision: (card: ActionCard, decision: 'approve' | 'dismiss') => void
}

export function ActionCardView({ card, busy, onDecision }: Props) {
  const overdue = card.status === 'pending' && !!card.due_at && new Date(card.due_at).getTime() < Date.now()
  const date = card.due_at
    ? new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(card.due_at))
    : null
  return (
    <article className="action-card">
      <div className="action-topline">
        <span className={`priority priority-${card.priority}`}>{card.priority}</span>
        {overdue && <span className="priority priority-urgent">Past due · review</span>}
        {date && <span className="due-date"><Clock3 size={13} /> {date}</span>}
      </div>
      <h4>{card.title}</h4>
      <p>{card.description}</p>
      {card.source_refs[0] && (
        <div className="source-pill"><ExternalLink size={12} /> {card.source_refs[0].account_label}</div>
      )}
      {card.status === 'pending' ? (
        <div className="action-buttons">
          <button className="approve-button" disabled={busy} onClick={() => onDecision(card, 'approve')}>
            <Check size={15} /> Approve
          </button>
          <button className="dismiss-button" disabled={busy} onClick={() => onDecision(card, 'dismiss')}>
            <X size={15} /> Dismiss
          </button>
        </div>
      ) : (
        <div className={`decision-state ${card.status}`}>
          {card.status === 'completed' ? (card.card_type === 'mail_task' ? 'Done · reported by email' : 'Completed') : card.status}
        </div>
      )}
    </article>
  )
}
