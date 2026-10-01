'use client'

import { FormEvent, useEffect, useState } from 'react'
import { ArrowRight, Check, ChevronLeft, LockKeyhole, Mail, RefreshCw, Sparkles } from 'lucide-react'
import { request } from '@/lib/api'

export type ConnectedAccount = {
  id: string; provider: 'gmail' | 'outlook'; email: string; display_name: string
  status: string; last_synced_at: string | null; sync_error: string | null
}

export type OnboardingState = {
  profile: { first_name: string; last_name: string; age: number; phone_number: string; gender: string; time_zone: string } | null
  accounts: ConnectedAccount[]
  sync_preferences: Record<string, { history_months: number; interval_hours: number; include_sent: number } | null>
  sync_jobs: Record<string, { status: string; processed_count: number; error: string | null } | null>
  ready: boolean
  gmail_client_imported: boolean
  outlook_available: boolean
}

type Step = 'profile' | 'connections' | 'sync'

export function Onboarding({ initial, onComplete, initialStep }: { initial: OnboardingState; onComplete: (state: OnboardingState) => void; initialStep?: Step }) {
  const [state, setState] = useState(initial)
  const [step, setStep] = useState<Step>(initialStep ?? (initial.profile ? initial.accounts.length ? 'sync' : 'connections' : 'profile'))
  const [firstName, setFirstName] = useState(initial.profile?.first_name ?? '')
  const [lastName, setLastName] = useState(initial.profile?.last_name ?? '')
  const [age, setAge] = useState(initial.profile?.age?.toString() ?? '')
  const [phone, setPhone] = useState(initial.profile?.phone_number ?? '')
  const [gender, setGender] = useState(initial.profile?.gender ?? '')
  const [gmailJson, setGmailJson] = useState('')
  const [outlookId, setOutlookId] = useState('')
  const [openProvider, setOpenProvider] = useState<'gmail' | 'outlook' | null>(null)
  const firstPreferences = initial.accounts.length ? initial.sync_preferences[initial.accounts[0].id] : null
  const [historyMonths, setHistoryMonths] = useState(firstPreferences?.history_months ?? 12)
  const [intervalHours, setIntervalHours] = useState(firstPreferences?.interval_hours ?? 24)
  const [includeSent, setIncludeSent] = useState(firstPreferences ? Boolean(firstPreferences.include_sent) : true)
  const [busy, setBusy] = useState(false)
  const [waitingForImport, setWaitingForImport] = useState(false)
  const [error, setError] = useState('')
  const connectionResult = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('connection')
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const currentStepIndex = (['profile', 'connections', 'sync'] as const).indexOf(step)

  useEffect(() => {
    if (step !== 'sync' || !waitingForImport) return
    const timer = window.setInterval(() => {
      void request<OnboardingState>('/api/onboarding').then(next => {
        setState(next)
        if (next.ready) {
          window.clearInterval(timer)
          onComplete(next)
        }
      }).catch(() => setError('Could not check import progress. Try again.'))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [step, waitingForImport, onComplete])

  async function refresh() {
    const next = await request<OnboardingState>('/api/onboarding')
    setState(next)
    return next
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      await request('/api/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ first_name: firstName, last_name: lastName, age: Number(age), phone_number: phone, gender, time_zone: timeZone }) })
      await refresh()
      setStep('connections')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save your profile') }
    finally { setBusy(false) }
  }

  async function importGmail() {
    setBusy(true); setError('')
    try {
      const credentials = JSON.parse(gmailJson)
      await request('/api/accounts/gmail/client', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ credentials }) })
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not read the Google JSON file') }
    finally { setBusy(false) }
  }

  async function importOutlook() {
    setBusy(true); setError('')
    try {
      await request('/api/accounts/outlook/client', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id: outlookId.trim() }) })
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save the Microsoft application ID') }
    finally { setBusy(false) }
  }

  async function connect(provider: 'gmail' | 'outlook') {
    setBusy(true); setError('')
    try {
      const result = await request<{ authorization_url: string }>(`/api/accounts/${provider}/start`, { method: 'POST' })
      window.location.assign(result.authorization_url)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not start sign-in'); setBusy(false) }
  }

  async function saveSync(event: FormEvent) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      for (const account of state.accounts) {
        await request(`/api/accounts/${account.id}/sync-preferences`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ history_months: historyMonths, interval_hours: intervalHours, include_sent: includeSent }) })
        if (state.sync_jobs[account.id]?.status === 'failed') {
          await request(`/api/accounts/${account.id}/sync`, { method: 'POST' })
        }
      }
      const next = await refresh()
      if (next.ready) onComplete(next)
      else if (next.accounts.length) setWaitingForImport(true)
      else setError('Connect at least one mailbox before continuing')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save sync settings') }
    finally { setBusy(false) }
  }

  return <main className="onboarding-shell">
    <div className="onboarding-glow onboarding-glow-one" aria-hidden="true" /><div className="onboarding-glow onboarding-glow-two" aria-hidden="true" />
    <div className="onboarding-header"><div className="onboarding-brand"><span className="onboarding-brand-mark"><Sparkles size={19} /></span> hey broski<span>.</span></div><p><span className="onboarding-header-dot" /> A little clarity, from the start</p></div>
    <div className="onboarding-layout">
      <aside className="onboarding-progress" aria-label="Setup progress">
        <div className="onboarding-aside-intro"><span className="section-label">A SPACE THAT FEELS LIKE YOURS</span><h2>Good things<br />start <em>here.</em></h2><p>Three thoughtful steps, and your space is ready to work with you.</p></div>
        <div className="onboarding-step-list">{([['profile', 'Your profile'], ['connections', 'Connect your mail'], ['sync', 'Import and sync']] as const).map(([key, label], index) =>
          <div className={`progress-step ${step === key ? 'current' : ''} ${index < currentStepIndex ? 'completed' : ''}`} key={key}><span>{index < currentStepIndex ? <Check size={15} /> : `0${index + 1}`}</span><div><strong>{label}</strong><small>{key === 'profile' ? 'A little about you' : key === 'connections' ? 'Read-only access' : 'Choose what to bring in'}</small></div></div>)}</div>
        <div className="onboarding-aside-note"><span className="onboarding-note-icon"><LockKeyhole size={16} /></span><p><strong>Made for your peace of mind.</strong><br />Your profile and imported mail live on this computer.</p></div>
      </aside>
      <section className="onboarding-card">
        {error && <div className="onboarding-error" role="alert">{error}</div>}
        <div key={step} className="onboarding-stage">
        {step === 'profile' && <><span className="section-label">STEP 01 / 03</span><h1>Let&apos;s get to know you.</h1><p className="onboarding-intro">These details stay in your local Hey Broski database. Your computer supplies the time zone automatically.</p>
          <form onSubmit={saveProfile} className="onboarding-form">
            <div className="field-row"><label>First name<input autoComplete="given-name" value={firstName} onChange={e => setFirstName(e.target.value)} required maxLength={80} /></label><label>Last name<input autoComplete="family-name" value={lastName} onChange={e => setLastName(e.target.value)} required maxLength={80} /></label></div>
            <div className="field-row"><label>Age<input type="number" min="1" max="120" value={age} onChange={e => setAge(e.target.value)} required /></label><label>Phone number<input type="tel" autoComplete="tel" value={phone} onChange={e => setPhone(e.target.value)} required maxLength={32} /></label></div>
            <label>Gender<input value={gender} onChange={e => setGender(e.target.value)} placeholder="How you describe yourself" required maxLength={80} /></label>
            <p className="detected-setting">Time zone detected from this computer: <strong>{timeZone}</strong></p>
            <button className="onboarding-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Continue to connections'} <ArrowRight size={17} /></button>
          </form></>}
        {step === 'connections' && <><span className="section-label">STEP 02 / 03</span><h1>Connect your inbox.</h1><p className="onboarding-intro">Connect at least one account. You&apos;ll sign in with Google or Microsoft and approve read-only mail access.</p>
          {connectionResult && <div className={connectionResult === 'connected' ? 'onboarding-success' : 'onboarding-error'} role="status">{connectionResult === 'connected' ? 'Mailbox connected and verified.' : 'Connection was not completed. You can try again.'}</div>}
          <div className="provider-list">
            {(['gmail', 'outlook'] as const).map(provider => <div className="provider-card" key={provider}>
              <div className="provider-title"><span className={`provider-mark ${provider}`}><Mail size={20} /></span><div><strong>{provider === 'gmail' ? 'Gmail' : 'Outlook'}</strong><small>{state.accounts.filter(a => a.provider === provider).length ? `${state.accounts.filter(a => a.provider === provider).length} connected` : 'Read-only mail access'}</small></div></div>
              <button type="button" className="onboarding-secondary" onClick={() => setOpenProvider(openProvider === provider ? null : provider)}>{openProvider === provider ? 'Hide steps' : 'Set up connection'}</button>
              {openProvider === provider && <div className="provider-details">
                {provider === 'gmail' ? <><ol><li>Create a Google Cloud project and enable the Gmail API.</li><li>Configure the OAuth consent screen for your own account.</li><li>Create an OAuth client of type <strong>Desktop app</strong> and download its JSON file.</li><li>Import that file here, then continue through Google sign-in.</li></ol>
                  <a href="https://developers.google.com/workspace/gmail/api/quickstart/python" target="_blank" rel="noreferrer">Google&apos;s setup guide ↗</a>
                  {!state.gmail_client_imported && <><label className="onboarding-file">Choose downloaded JSON<input type="file" accept="application/json,.json" onChange={async e => { const file = e.target.files?.[0]; if (file) setGmailJson(await file.text()) }} /></label><textarea aria-label="Google OAuth client JSON" placeholder="Or paste the downloaded Desktop OAuth JSON here" value={gmailJson} onChange={e => setGmailJson(e.target.value)} rows={4} /><button type="button" className="onboarding-secondary" onClick={importGmail} disabled={busy || !gmailJson.trim()}>Confirm client details</button></>}
                  {state.gmail_client_imported && <button type="button" className="onboarding-primary" disabled={busy} onClick={() => void connect('gmail')}>Continue with Google <ArrowRight size={16} /></button>}
                </> : <><p>Sign in with a personal Outlook account or a Microsoft 365 account whose administrator permits this application.</p>
                  {!state.outlook_available && <><ol><li>Register an application in Microsoft Entra.</li><li>Choose personal and organizational account support, add a Mobile and desktop redirect URI matching <code>http://localhost:8000/api/accounts/outlook/callback</code>.</li><li>Add delegated <code>Mail.Read</code> and <code>User.Read</code> permissions. Copy its Application (client) ID below.</li></ol><a href="https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app" target="_blank" rel="noreferrer">Microsoft&apos;s registration guide ↗</a><label>Application (client) ID<input value={outlookId} onChange={e => setOutlookId(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label><button type="button" className="onboarding-secondary" disabled={busy || !outlookId.trim()} onClick={importOutlook}>Confirm application ID</button></>}
                  {state.outlook_available && <button type="button" className="onboarding-primary" disabled={busy} onClick={() => void connect('outlook')}>Continue with Microsoft <ArrowRight size={16} /></button>}
                </>}
              </div>}
            </div>)}
          </div>
          {!!state.accounts.length && <div className="connected-list"><strong>Verified mailboxes</strong>{state.accounts.map(account => <div key={account.id}><Check size={16} /> {account.email}</div>)}</div>}
          <button className="onboarding-primary" type="button" disabled={!state.accounts.length} onClick={() => setStep('sync')}>Choose import and sync settings <ArrowRight size={17} /></button>
          <button type="button" className="onboarding-back" onClick={() => setStep('profile')}><ChevronLeft size={15} /> Edit profile</button>
        </>}
        {step === 'sync' && <><span className="section-label">STEP 03 / 03</span><h1>Make it yours.</h1><p className="onboarding-intro">Choose how much existing mail to import and how often Hey Broski checks for updates while it is running. These choices apply to all connected mailboxes.</p>
          <div className="connected-list"><strong>Connected mailboxes</strong>{state.accounts.map(account => <div key={account.id}><Check size={16} /> {account.email}</div>)}</div>
          {state.accounts.some(account => state.sync_jobs[account.id]) && <div className="connected-list" role="status"><strong>First import</strong>{state.accounts.map(account => { const job = state.sync_jobs[account.id]; return <div key={account.id}>{account.email}: {job?.status === 'complete' ? `${job.processed_count} messages checked` : job?.status === 'failed' ? `Import paused: ${job.error || 'provider error'}` : job?.status === 'running' ? `Importing · ${job.processed_count} messages checked` : 'Waiting to start'}</div> })}</div>}
          <form className="onboarding-form" onSubmit={saveSync}>
            <label>How far back should we import?<select value={historyMonths} onChange={e => setHistoryMonths(Number(e.target.value))}><option value="3">Last 3 months</option><option value="6">Last 6 months</option><option value="12">Last 1 year</option><option value="24">Last 2 years</option></select></label>
            <label>How often should we sync?<select value={intervalHours} onChange={e => setIntervalHours(Number(e.target.value))}><option value="1">Every hour</option><option value="6">Every 6 hours</option><option value="12">Every 12 hours</option><option value="24">Every day</option></select></label>
            <label className="onboarding-check"><input type="checkbox" checked={includeSent} onChange={e => setIncludeSent(e.target.checked)} /> Include sent mail, to help identify follow-ups</label>
            <p className="onboarding-note"><LockKeyhole size={15} /> Imported mail is stored on this computer. Keep Hey Broski open while the first import finishes.</p>
            <button className="onboarding-primary" type="submit" disabled={busy || waitingForImport && !state.accounts.some(account => state.sync_jobs[account.id]?.status === 'failed')}>{busy ? 'Saving…' : waitingForImport && !state.accounts.some(account => state.sync_jobs[account.id]?.status === 'failed') ? 'Importing your mail…' : 'Enter my workspace'} <ArrowRight size={17} /></button>
          </form><button type="button" className="onboarding-back" onClick={() => setStep('connections')}><ChevronLeft size={15} /> Back to connections</button></>}
        </div>
      </section>
    </div>
    <footer className="onboarding-footer"><RefreshCw size={14} /> Your connections and sync settings can always be changed later.</footer>
  </main>
}
