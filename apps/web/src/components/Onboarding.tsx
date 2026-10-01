'use client'

import { FormEvent, useEffect, useState } from 'react'
import { ArrowRight, Check, ChevronLeft, LockKeyhole, Mail, RefreshCw, Sparkles } from 'lucide-react'
import { request } from '@/lib/api'

export type ConnectedAccount = {
  id: string; provider: 'gmail' | 'outlook'; email: string; display_name: string
  status: string; last_synced_at: string | null; sync_error: string | null
}

export type OnboardingState = {
  profile: { first_name: string; last_name: string; age: number; date_of_birth: string | null; country_code: string | null; phone_number: string; gender: string; time_zone: string } | null
  profile_complete: boolean
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
  const firstPreferences = initial.accounts.length ? initial.sync_preferences[initial.accounts[0].id] : null
  const [historyMonths, setHistoryMonths] = useState(firstPreferences?.history_months ?? 12)
  const [intervalHours, setIntervalHours] = useState(firstPreferences?.interval_hours ?? 24)
  const [includeSent, setIncludeSent] = useState(firstPreferences ? Boolean(firstPreferences.include_sent) : true)
  const [busy, setBusy] = useState(false)
  const [waitingForImport, setWaitingForImport] = useState(false)
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
        body: JSON.stringify({ first_name: firstName, last_name: lastName, date_of_birth: dateOfBirth, country_code: countryCode,
          phone_number: phone, gender: genderOption === 'self-describe' ? genderDescription : genderOption, time_zone: timeZone }) })
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
            <div className="field-row"><label>Date of birth<input type="date" autoComplete="bday" max={latestBirthDate} value={dateOfBirth} onChange={e => setDateOfBirth(e.target.value)} required /></label><div className="phone-fields"><label>Country code<input type="tel" inputMode="tel" autoComplete="tel-country-code" placeholder="+91" pattern="\+[1-9][0-9]{0,3}" title="Enter a calling code like +91" value={countryCode} onChange={e => setCountryCode(e.target.value)} required maxLength={5} /></label><label>Phone number<input type="tel" inputMode="numeric" autoComplete="tel-national" placeholder="Digits only" pattern="[0-9]{4,15}" title="Enter 4 to 15 digits without the country code" value={phone} onChange={e => setPhone(e.target.value)} required maxLength={15} /></label></div></div>
            {calculatedAge !== null && <p className="detected-setting">Age calculated from your birth date: <strong>{calculatedAge}</strong></p>}
            <label>Gender<select value={genderOption} onChange={e => setGenderOption(e.target.value)} required><option value="" disabled>Select an option</option><option value="male">Male</option><option value="female">Female</option><option value="non-binary">Non-binary</option><option value="self-describe">Self describe</option></select></label>
            {genderOption === 'self-describe' && <label>Describe your gender<input value={genderDescription} onChange={e => setGenderDescription(e.target.value)} placeholder="How you describe yourself" required maxLength={80} /></label>}
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
                {provider === 'gmail' ? <><div className="setup-cost"><strong>Check the billing choice first</strong><span>Google currently provides standard Gmail API use at no additional cost. But if this project is linked to a Cloud Billing account, other Cloud services and future billable usage could charge it. Do not create a project with a billing account selected unless you accept that link.</span></div>
                  <details className="setup-alternative"><summary>Only billing accounts appear in New Project?</summary><p>Cancel that form. Open <a href="https://shell.cloud.google.com/" target="_blank" rel="noreferrer">Google Cloud Shell ↗</a> and run the command below, replacing <code>your-unique-id</code> with a unique lowercase name. This command does not specify a billing account. After it finishes, refresh Cloud Console, open the project picker, and search the exact project ID under <b>All</b> or <b>No organization</b>. Check that Billing shows no linked account, then return to step 3. If enabling Gmail API asks you to link billing, stop there.</p><code>gcloud projects create your-unique-id --name=&quot;Hey Broski Personal&quot;</code></details>
                  <ol className="setup-guide">
                    <li><strong>Open Google Cloud Console.</strong><span>Visit <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">console.cloud.google.com ↗</a> and sign in with the Gmail account you want to connect.</span></li>
                    <li><strong>Create a project without linking billing.</strong><span>Click the project name at the top, then <b>New Project</b>. Enter a name such as <b>Hey Broski Personal</b>. If a <b>Billing account</b> field appears, select <b>No billing account</b> if offered. If the list contains only billing accounts, do not click <b>Create</b>; use the alternative above. Select the new project once it is created.</span></li>
                    <li><strong>Enable Gmail API.</strong><span>Open the <b>☰ Menu → APIs &amp; Services → Library</b>. Search for <b>Gmail API</b>, open it, and click <b>Enable</b>.</span></li>
                    <li><strong>Enter the app details.</strong><span>Open <b>☰ Menu → Google Auth platform → Branding</b> and click <b>Get started</b> if shown. Enter <b>Hey Broski</b> as the app name, select your email as the user support email, then click <b>Next</b>.</span></li>
                    <li><strong>Choose who can use it.</strong><span>Select <b>External</b> for a personal Gmail account and click <b>Next</b>. Enter your email as the contact address, click <b>Next</b>, review the Google API Services User Data Policy, then click <b>Continue → Create</b>. For a managed Google Workspace account, your administrator may instead require <b>Internal</b>.</span></li>
                    <li><strong>Add yourself as a test user.</strong><span>In <b>Google Auth platform → Audience</b>, find <b>Test users</b>, click <b>Add users</b>, enter the same Gmail address, and save.</span></li>
                    <li><strong>Allow read-only mail access.</strong><span>In <b>Google Auth platform → Data Access</b>, click <b>Add or remove scopes</b>. Find and select <code>https://www.googleapis.com/auth/gmail.readonly</code>, then update and save. This lets Hey Broski read mail; it cannot send or delete it.</span></li>
                    <li><strong>Create the Desktop client.</strong><span>Open <b>Google Auth platform → Clients → Create client</b>. Choose <b>Desktop app</b>, name it <b>Hey Broski Local</b>, and click <b>Create</b>.</span></li>
                    <li><strong>Download and import the JSON.</strong><span>Click <b>Download JSON</b> in the confirmation window, or use the download icon beside the client in <b>Clients</b>. Save the file on this computer, choose it below, then click <b>Confirm client details</b>. After that, use <b>Continue with Google</b> to approve access.</span></li>
                  </ol>
                  <p className="setup-footnote">While your Google app stays in <b>Testing</b>, Google may ask you to reconnect after seven days. Your previously imported local mail stays available.</p>
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
