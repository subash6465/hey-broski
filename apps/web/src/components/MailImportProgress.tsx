'use client'

import type { ConnectedAccount, OnboardingState } from './Onboarding'

type Job = OnboardingState['sync_jobs'][string]
type Pipeline = { searchable_messages: number; embedded_messages: number; pending_embedding_chunks: number; imported_messages: number; processed_messages: number; discovered_messages: number }

export function MailImportProgress({ account, job, pipeline, busy, onResume, onPause, onCancel }: {
  account: ConnectedAccount; job: Job; pipeline?: Pipeline; busy: boolean
  onResume: () => void; onPause: () => void; onCancel: () => void
}) {
  const gmail = account.provider === 'gmail'
  const hasDiscovered = (pipeline?.discovered_messages ?? 0) > 0
  const exact = gmail && job?.discovery_complete === 1 && hasDiscovered
  const countedScan = gmail && hasDiscovered
  const total = exact ? (job?.total_estimate ?? 0) : gmail && job?.status === 'complete' ? (pipeline?.searchable_messages ?? null) : null
  const imported = gmail ? (countedScan ? (pipeline?.imported_messages ?? 0) : (pipeline?.searchable_messages ?? 0)) : (job?.processed_count ?? 0)
  const processed = gmail ? (countedScan ? (pipeline?.processed_messages ?? 0) : (pipeline?.embedded_messages ?? 0)) : 0
  const skipped = job?.skipped_count ?? 0
  const complete = job?.status === 'complete' && (!gmail || (pipeline?.pending_embedding_chunks ?? 0) === 0)
  const percent = total === null ? null : total === 0 ? 100 : Math.min(100, Math.round((imported + processed + 2 * skipped) / (2 * total) * 100))
  const state = job?.status === 'paused' || job?.status === 'paused_processing' ? 'Paused' : job?.status === 'canceled' ? 'Canceled' : job?.status === 'failed' ? 'Needs attention' : complete ? 'Complete' : 'In progress'

  return <div className="import-progress-account">
    <div className="import-progress-line"><strong>{account.email}</strong><span>{state}</span></div>
    <div className="import-progress-stages">
      <div className="import-progress-stage"><span>1 · Import</span><strong>{imported} / {total === null ? 'unknown' : total}</strong><small>{total === null ? gmail ? 'Scanning matching message IDs' : 'Count unavailable for this sync' : `${skipped} inaccessible skipped`}</small></div>
      <div className="import-progress-stage"><span>2 · Process</span><strong>{gmail ? `${processed} / ${imported}` : 'Unavailable'}</strong><small>{gmail ? `${pipeline?.pending_embedding_chunks ?? 0} chunks awaiting embeddings` : 'Semantic indexing is currently Gmail only'}</small></div>
    </div>
    <div className={`import-progress-track ${percent === null && job?.status === 'running' ? 'indeterminate' : ''}`} role="progressbar" aria-label={`${account.email} end-to-end progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined} aria-valuetext={percent === null ? 'Counting matching messages' : `${percent}% complete`}><span style={percent === null ? undefined : { width: `${percent}%` }} /></div>
    {total === null && <small>{gmail ? 'The total appears after the matching message scan finishes. Gmail does not provide an exact total for this search.' : 'This provider has no exact total for the selected import window, so percentage progress is unavailable.'}</small>}
    {exact && <small>Total counts the message IDs returned during this scan. New mail can arrive while it runs.</small>}
    {job?.error && <small className="import-progress-error">{job.error}</small>}
    <div className="import-progress-actions">
      {(job?.status === 'running' || job?.status === 'complete' && !complete) && <button type="button" disabled={busy} onClick={onPause}>Pause</button>}
      {(job?.status === 'paused' || job?.status === 'paused_processing' || job?.status === 'failed') && <button type="button" disabled={busy} onClick={onResume}>Resume</button>}
      {(job?.status === 'running' || job?.status === 'paused' || job?.status === 'paused_processing' || job?.status === 'failed' || job?.status === 'complete' && !complete) && <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>}
    </div>
  </div>
}
