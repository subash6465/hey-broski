'use client'

import { FormEvent, useCallback, useState } from 'react'
import { ArrowRight, Check, ChevronLeft, LockKeyhole, Mail, RefreshCw, Sparkles, X } from 'lucide-react'
import { request } from '@/lib/api'
import { ConnectionDialog } from './ConnectionDialog'

export type ConnectedAccount = {
  id: string; provider: 'gmail' | 'outlook'; email: string; display_name: string
  status: string; last_synced_at: string | null; sync_error: string | null
}

export type OnboardingState = {
  profile: { first_name: string; last_name: string; age: number; date_of_birth: string | null; country_code: string | null; phone_number: string; gender: string; time_zone: string } | null
  profile_complete: boolean
  accounts: ConnectedAccount[]
  sync_preferences: Record<string, { history_months: number; interval_hours: number; include_sent: number } | null>
  sync_jobs: Record<string, { status: string; processed_count: number; skipped_count: number; total_estimate: number | null; discovery_complete: number; error: string | null } | null>
  ready: boolean
  gmail_client_imported: boolean
  outlook_available: boolean
}

type Step = 'profile' | 'connections' | 'sync'

export function Onboarding({ initial, onComplete, initialStep, editing = false, onCancel }: { initial: OnboardingState; onComplete: (state: OnboardingState) => void; initialStep?: Step; editing?: boolean; onCancel?: () => void }) {
  const [state, setState] = useState(initial)
  const [step, setStep] = useState<Step>(initialStep ?? (initial.profile_complete ? initial.accounts.length ? 'sync' : 'connections' : 'profile'))
  const [firstName, setFirstName] = useState(initial.profile?.first_name ?? '')
  const [lastName, setLastName] = useState(initial.profile?.last_name ?? '')
  const [dateOfBirth, setDateOfBirth] = useState(initial.profile?.date_of_birth ?? '')
  const [countryCode, setCountryCode] = useState(initial.profile?.country_code ?? '')
  const [phone, setPhone] = useState(initial.profile?.country_code ? initial.profile.phone_number : '')
  const savedGender = initial.profile?.gender ?? ''
  const [genderOption, setGenderOption] = useState(['male', 'female', 'non-binary'].includes(savedGender) ? savedGender : savedGender ? 'self-describe' : '')
  const [genderDescription, setGenderDescription] = useState(['male', 'female', 'non-binary'].includes(savedGender) ? '' : savedGender)
  const [gmailJson, setGmailJson] = useState('')
  const [outlookId, setOutlookId] = useState('')
  const [openProvider, setOpenProvider] = useState<'gmail' | 'outlook' | null>(null)
  const closeProvider = useCallback(() => setOpenProvider(null), [])
  const firstPreferences = initial.accounts.length ? initial.sync_preferences[initial.accounts[0].id] : null
  const [historyMonths, setHistoryMonths] = useState(firstPreferences?.history_months ?? 12)
  const [intervalHours, setIntervalHours] = useState(firstPreferences?.interval_hours ?? 24)
  const [includeSent, setIncludeSent] = useState(firstPreferences ? Boolean(firstPreferences.include_sent) : true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const connectionResult = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('connection')
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const today = new Date()
  const latestBirthDate = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-')
  const birth = dateOfBirth ? new Date(`${dateOfBirth}T12:00:00`) : null
  const calculatedAge = birth && !Number.isNaN(birth.getTime()) && dateOfBirth <= latestBirthDate
    ? today.getFullYear() - birth.getFullYear() - (today.getMonth() < birth.getMonth() || today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate() ? 1 : 0)
    : null
  const currentStepIndex = (['profile', 'connections', 'sync'] as const).indexOf(step)

  async function refresh() {
    const next = await request<OnboardingState>('/api/onboarding')
    setState(next)
    return next
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const saveAndExit = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'save'
    setBusy(true); setError('')
    try {
      await request('/api/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ first_name: firstName, last_name: lastName, date_of_birth: dateOfBirth, country_code: countryCode,
          phone_number: phone, gender: genderOption === 'self-describe' ? genderDescription : genderOption, time_zone: timeZone }) })
      const next = await refresh()
      if (editing && saveAndExit) onComplete(next)
      else setStep('connections')
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

  async function saveConnections() {
    setBusy(true); setError('')
    try {
      const next = await refresh()
      if (next.ready) onComplete(next)
      else setError('Connect at least one mailbox before returning to the workspace')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save connections') }
    finally { setBusy(false) }
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
        {error && !openProvider && <div className="onboarding-error" role="alert">{error}</div>}
        <div key={step} className="onboarding-stage">
        {step === 'profile' && <><span className="section-label">STEP 01 / 03</span><h1>Let&apos;s get to know you.</h1><p className="onboarding-intro">These details stay in your local Hey Broski database. Your computer supplies the time zone automatically.</p>
          <form onSubmit={saveProfile} className="onboarding-form">
            <div className="field-row"><label>First name<input autoComplete="given-name" value={firstName} onChange={e => setFirstName(e.target.value)} required maxLength={80} /></label><label>Last name<input autoComplete="family-name" value={lastName} onChange={e => setLastName(e.target.value)} required maxLength={80} /></label></div>
            <div className="field-row"><label>Date of birth<input type="date" autoComplete="bday" max={latestBirthDate} value={dateOfBirth} onChange={e => setDateOfBirth(e.target.value)} required /></label><div className="phone-fields"><label>Country code<input type="tel" inputMode="tel" autoComplete="tel-country-code" placeholder="+91" pattern="\+[1-9][0-9]{0,3}" title="Enter a calling code like +91" value={countryCode} onChange={e => setCountryCode(e.target.value)} required maxLength={5} /></label><label>Phone number<input type="tel" inputMode="numeric" autoComplete="tel-national" placeholder="Digits only" pattern="[0-9]{4,15}" title="Enter 4 to 15 digits without the country code" value={phone} onChange={e => setPhone(e.target.value)} required maxLength={15} /></label></div></div>
            {calculatedAge !== null && <p className="detected-setting">Age calculated from your birth date: <strong>{calculatedAge}</strong></p>}
            <label>Gender<select value={genderOption} onChange={e => setGenderOption(e.target.value)} required><option value="" disabled>Select an option</option><option value="male">Male</option><option value="female">Female</option><option value="non-binary">Non-binary</option><option value="self-describe">Self describe</option></select></label>
            {genderOption === 'self-describe' && <label>Describe your gender<input value={genderDescription} onChange={e => setGenderDescription(e.target.value)} placeholder="How you describe yourself" required maxLength={80} /></label>}
            <p className="detected-setting">Time zone detected from this computer: <strong>{timeZone}</strong></p>
            <button className="onboarding-primary" type="submit" value="continue" disabled={busy}>{busy ? 'Saving…' : 'Continue to connections'} <ArrowRight size={17} /></button>
            {editing && <div className="onboarding-edit-actions"><button className="onboarding-secondary" type="submit" value="save" disabled={busy}>Save profile</button><button className="onboarding-cancel" type="button" onClick={onCancel} disabled={busy}>Cancel <X size={15} /></button></div>}
          </form></>}
        {step === 'connections' && <><span className="section-label">STEP 02 / 03</span><h1>Connect your inbox.</h1><p className="onboarding-intro">Connect at least one account. You&apos;ll sign in with Google or Microsoft and approve read-only mail access.</p>
          {connectionResult && <div className={connectionResult === 'connected' ? 'onboarding-success' : 'onboarding-error'} role="status">{connectionResult === 'connected' ? 'Mailbox connected and verified.' : 'Connection was not completed. You can try again.'}</div>}
          <div className="provider-list">
            {(['gmail', 'outlook'] as const).map(provider => <div className="provider-card" key={provider}>
              <button type="button" className="provider-title" onClick={() => { setError(''); setOpenProvider(provider) }}><span className={`provider-mark ${provider}`}><Mail size={20} /></span><span className="provider-title-copy"><strong>{provider === 'gmail' ? 'Gmail' : 'Outlook'}</strong><small>{state.accounts.filter(a => a.provider === provider).length ? `${state.accounts.filter(a => a.provider === provider).length} connected` : 'Read-only mail access'}</small></span></button>
              <button type="button" className="onboarding-secondary" onClick={() => { setError(''); setOpenProvider(provider) }}>Set up connection</button>

            </div>)}
          </div>
          {!!state.accounts.length && <div className="connected-list"><strong>Verified mailboxes</strong>{state.accounts.map(account => <div key={account.id}><Check size={16} /> {account.email}</div>)}</div>}
          <button className="onboarding-primary" type="button" disabled={!state.accounts.length} onClick={() => setStep('sync')}>Choose import and sync settings <ArrowRight size={17} /></button>
          <button type="button" className="onboarding-back" onClick={() => setStep('profile')}><ChevronLeft size={15} /> Edit profile</button>
          {editing && <div className="onboarding-edit-actions"><button className="onboarding-secondary" type="button" onClick={() => void saveConnections()} disabled={busy}>Save connections</button><button className="onboarding-cancel" type="button" onClick={onCancel} disabled={busy}>Cancel <X size={15} /></button></div>}
        </>}
        {step === 'sync' && <><span className="section-label">STEP 03 / 03</span><h1>Make it yours.</h1><p className="onboarding-intro">Choose how much existing mail to import and how often Hey Broski checks for updates while it is running. These choices apply to all connected mailboxes.</p>
          <div className="connected-list"><strong>Connected mailboxes</strong>{state.accounts.map(account => <div key={account.id}><Check size={16} /> {account.email}</div>)}</div>
          <p className="onboarding-note"><RefreshCw size={15} /> Import starts in the background. You can use your workspace while it runs.</p>
          <form className="onboarding-form" onSubmit={saveSync}>
            <label>How far back should we import?<select value={historyMonths} onChange={e => setHistoryMonths(Number(e.target.value))}><option value="3">Last 3 months</option><option value="6">Last 6 months</option><option value="12">Last 1 year</option><option value="24">Last 2 years</option></select></label>
            <label>How often should we sync?<select value={intervalHours} onChange={e => setIntervalHours(Number(e.target.value))}><option value="1">Every hour</option><option value="6">Every 6 hours</option><option value="12">Every 12 hours</option><option value="24">Every day</option></select></label>
            <label className="onboarding-check"><input type="checkbox" checked={includeSent} onChange={e => setIncludeSent(e.target.checked)} /> Include sent mail, to help identify follow-ups</label>
            <p className="onboarding-note"><LockKeyhole size={15} /> Gmail message text and search indexes are stored on this computer without database encryption. Keep Hey Broski open while the first import finishes.</p>
            <button className="onboarding-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Enter my workspace'} <ArrowRight size={17} /></button>
            <button type="button" className="onboarding-back" onClick={() => setStep('connections')}><ChevronLeft size={15} /> Back to connections</button>
            {editing && <div className="onboarding-edit-actions"><button className="onboarding-secondary" type="submit" disabled={busy}>Save import and sync</button><button className="onboarding-cancel" type="button" onClick={onCancel} disabled={busy}>Cancel <X size={15} /></button></div>}
          </form></>}
        </div>
      </section>
    </div>
    <footer className="onboarding-footer"><RefreshCw size={14} /> Your connections and sync settings can always be changed later.</footer>
    <ConnectionDialog provider={openProvider} onClose={closeProvider} error={error} gmailJson={gmailJson} setGmailJson={setGmailJson} gmailClientImported={state.gmail_client_imported} outlookId={outlookId} setOutlookId={setOutlookId} outlookAvailable={state.outlook_available} busy={busy} importGmail={() => void importGmail()} importOutlook={() => void importOutlook()} connect={provider => void connect(provider)} />
  </main>
}
