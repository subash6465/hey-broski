import { Check, Clock3, ExternalLink, X } from 'lucide-react'
import type { ActionCard } from '@/lib/types'

type Props = {
  card: ActionCard
  busy?: boolean
  onDecision: (card: ActionCard, decision: 'approve' | 'dismiss') => void
}

export function ActionCardView({ card, busy, onDecision }: Props) {
  const date = card.due_at
    ? new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short' }).format(new Date(card.due_at))
    : null
  return (
    <article className="action-card">
      <div className="action-topline">
        <span className={`priority priority-${card.priority}`}>{card.priority}</span>
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
          {card.status === 'completed' ? 'Approved · reminder created' : card.status}
        </div>
      )}
    </article>
  )
}
