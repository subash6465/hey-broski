'use client'

import { Mail, RefreshCw, Trash2 } from 'lucide-react'
import type { ConnectedAccount, OnboardingState } from './Onboarding'

type Job = OnboardingState['sync_jobs'][string]

export function MailAccountCard({ account, job, pendingChunks, busy, onSync, onPause, onCancel, onDelete, onDisconnect }: {
  account: ConnectedAccount; job: Job; pendingChunks: number; busy: boolean
  onSync: () => void; onPause: () => void; onCancel: () => void; onDelete: () => void; onDisconnect: () => void
}) {
  const processing = job?.status === 'complete' && pendingChunks > 0
  const active = job?.status === 'running' || processing
  const paused = job?.status === 'paused' || job?.status === 'paused_processing'
  const cancellable = active || paused || job?.status === 'failed'
  const status = job?.status === 'running' ? `Importing · ${job.processed_count} messages`
    : paused ? 'Import and processing paused'
    : job?.status === 'canceled' ? 'Canceled · imported mail retained'
    : job?.status === 'failed' ? `Sync needs attention: ${job.error}`
    : processing ? `${pendingChunks} chunks awaiting embeddings`
    : account.last_synced_at ? `Last synced ${new Date(account.last_synced_at).toLocaleString()}` : 'Waiting to import'

  return <article className="account-card"><span className="provider-mark"><Mail size={20} /></span><div>
    <strong>{account.display_name}</strong>
    <p>{account.email} · {account.provider === 'gmail' ? 'Gmail' : 'Outlook'}</p>
    <small>{status}</small>
    <div className="account-buttons">
      <button onClick={onSync} disabled={busy || active}><RefreshCw size={14} /> {paused || job?.status === 'failed' ? 'Resume' : 'Sync now'}</button>
      {active && <button onClick={onPause} disabled={busy}>Pause</button>}
      {cancellable && <button onClick={onCancel} disabled={busy}>Cancel</button>}
      <button onClick={onDelete} disabled={busy}><Trash2 size={14} /> Delete imported mail</button>
      <button onClick={onDisconnect} disabled={busy || active}>Disconnect</button>
    </div>
  </div></article>
}
