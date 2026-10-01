'use client'

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowRight, X } from 'lucide-react'

type Provider = 'gmail' | 'outlook'

function GuideSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="setup-segment"><h3>{title}</h3><ol className="setup-guide">{children}</ol></section>
}

export function ConnectionDialog({ provider, onClose, error, gmailJson, setGmailJson, gmailClientImported, outlookId, setOutlookId, outlookAvailable, busy, importGmail, importOutlook, connect }: {
  provider: Provider | null
  onClose: () => void
  error: string
  gmailJson: string
  setGmailJson: (value: string) => void
  gmailClientImported: boolean
  outlookId: string
  setOutlookId: (value: string) => void
  outlookAvailable: boolean
  busy: boolean
  importGmail: () => void
  importOutlook: () => void
  connect: (provider: Provider) => void
}) {
  const [projectId] = useState(() => {
    if (typeof window === 'undefined') return ''
    const stored = window.sessionStorage.getItem('hey-broski-google-project-id')
    if (stored) return stored
    const suffix = Array.from(crypto.getRandomValues(new Uint8Array(3)), value => value.toString(16).padStart(2, '0')).join('')
    const date = new Date()
    const stamp = `${String(date.getFullYear()).slice(-2)}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`
    const next = `hey-broski-local-${stamp}-${suffix}`
    window.sessionStorage.setItem('hey-broski-google-project-id', next)
    return next
  })

  useEffect(() => {
    if (!provider) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => { document.body.style.overflow = previous; window.removeEventListener('keydown', onKeyDown) }
  }, [provider, onClose])

  if (!provider) return null

  return createPortal(<div className="connection-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="connection-dialog" role="dialog" aria-modal="true" aria-labelledby="connection-dialog-title">
      <header className="connection-dialog-header"><div><span className="section-label">CONNECT YOUR MAIL</span><h2 id="connection-dialog-title">Set up {provider === 'gmail' ? 'Gmail' : 'Outlook'}</h2><p>Follow the steps, then connect your account.</p></div><button type="button" className="connection-dialog-close" aria-label="Close setup" onClick={onClose}><X size={19} /></button></header>
      <div className="connection-dialog-scroll provider-details">
        {error && <div className="onboarding-error" role="alert">{error}</div>}
        {provider === 'gmail' ? <>
          <div className="setup-cost"><strong>Standard Gmail API use has no additional charge</strong><span>The command below creates a project without selecting a billing account. If Google asks you to link billing while enabling Gmail API, review that request before proceeding. Other Cloud services or future usage above Google&apos;s standard threshold may have charges.</span></div>
          <p className="setup-footnote">Already created a <b>Hey Broski Personal</b> project? Use that project in Cloud Console and skip the Cloud Shell creation command.</p>
          <GuideSection title="1 · Google Cloud Shell">
            <li><strong>Open Cloud Shell.</strong><span>Visit <a href="https://shell.cloud.google.com/" target="_blank" rel="noreferrer">shell.cloud.google.com ↗</a> and sign in with the Google account you want to connect.</span></li>
            <li><strong>Wait for the terminal.</strong><span>Cloud Shell may take a moment to initialize. Continue when you can type at its prompt.</span></li>
            <li><strong>Create your project.</strong><span>Copy and run this complete command. The project ID is unique to this setup:</span><code className="setup-command">{projectId ? `gcloud projects create ${projectId} --name="Hey Broski Personal"` : 'Preparing your project command…'}</code></li>
            <li><strong>Wait for completion.</strong><span>Keep Cloud Shell open until it reports that the project creation operation finished successfully.</span></li>
          </GuideSection>
          <GuideSection title="2 · Google Cloud Console">
            <li><strong>Open Cloud Console.</strong><span>Visit <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">console.cloud.google.com ↗</a> using the same Google account.</span></li>
            <li><strong>Find the project.</strong><span>Open the project picker at the top. Wait briefly and refresh if <b>Hey Broski Personal</b> has not appeared yet. Search for <code>{projectId || 'your project ID'}</code> under <b>All</b> or <b>No organization</b>, then select it.</span></li>
            <li><strong>Open the API Library.</strong><span>Use <b>Menu → APIs &amp; Services → Library</b> and search for <b>gmail</b>.</span></li>
            <li><strong>Choose the correct API.</strong><span>Of the four results, select <b>Gmail API</b> with the colored Gmail icon. Do not select Gmail MCP API, Gmail Postmaster Tools API, or Workspace MCP API.</span></li>
            <li><strong>Enable it.</strong><span>On the Gmail API page, click <b>Enable</b>.</span></li>
          </GuideSection>
          <GuideSection title="3 · Google Auth Platform">
            <li><strong>Open the setup page directly.</strong><span>Visit <a href={`https://console.cloud.google.com/auth/branding?project=${projectId}`} target="_blank" rel="noreferrer">Google Auth Platform → Branding ↗</a>. Check that <b>Hey Broski Personal</b> is selected at the top.</span></li>
            <li><strong>Start the consent screen.</strong><span>Click <b>Get started</b> if shown.</span></li>
            <li><strong>Enter the app information.</strong><span>Enter <b>Hey Broski</b> as the app name and choose your email as the user support email. Click <b>Next</b>.</span></li>
            <li><strong>Choose the audience.</strong><span>Select <b>External</b> for a personal Gmail account and click <b>Next</b>. A managed Workspace account may use <b>Internal</b>.</span></li>
            <li><strong>Add a contact address.</strong><span>Enter your email address for project notifications, then click <b>Next</b>.</span></li>
            <li><strong>Finish setup.</strong><span>Review Google&apos;s user data policy, accept it if you agree, click <b>Continue</b>, then <b>Create</b>.</span></li>
            <li><strong>Add your test account.</strong><span>Open <b>Audience → Test users → Add users</b>. Enter the Gmail address you want to connect and save.</span></li>
            <li><strong>Add read-only access.</strong><span>Open <b>Data Access → Add or remove scopes</b>. Select <code>https://www.googleapis.com/auth/gmail.readonly</code>, then update and save.</span></li>
            <li><strong>Create the OAuth client.</strong><span>Open <b>Clients → Create client</b>. Choose <b>Desktop app</b>, name it <b>Hey Broski Local</b>, then click <b>Create</b>.</span></li>
            <li><strong>Download the JSON.</strong><span>Click <b>Download JSON</b> in the confirmation window, or use the download icon beside that client in <b>Clients</b>.</span></li>
          </GuideSection>
          <p className="setup-footnote">While your Google app stays in <b>Testing</b>, Google may ask you to reconnect after seven days. Your previously imported local mail stays available.</p>
          {!gmailClientImported && <div className="connection-dialog-action"><label className="onboarding-file">Choose downloaded JSON<input type="file" accept="application/json,.json" onChange={async event => { const file = event.target.files?.[0]; if (file) setGmailJson(await file.text()) }} /></label><textarea aria-label="Google OAuth client JSON" placeholder="Or paste the downloaded Desktop OAuth JSON here" value={gmailJson} onChange={event => setGmailJson(event.target.value)} rows={4} /><button type="button" className="onboarding-secondary" onClick={importGmail} disabled={busy || !gmailJson.trim()}>Confirm client details</button></div>}
          {gmailClientImported && <div className="connection-dialog-action"><button type="button" className="onboarding-primary" disabled={busy} onClick={() => connect('gmail')}>Continue with Google <ArrowRight size={16} /></button></div>}
        </> : <>
          <p>Sign in with a personal Outlook account or a Microsoft 365 account whose administrator permits this application.</p>
          {!outlookAvailable && <><GuideSection title="Microsoft Entra">
            <li><strong>Register an application.</strong><span>Open <a href="https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app" target="_blank" rel="noreferrer">Microsoft Entra app registrations ↗</a> and create a new registration.</span></li>
            <li><strong>Choose supported accounts.</strong><span>Select support for personal and organizational accounts.</span></li>
            <li><strong>Add the redirect URI.</strong><span>Choose <b>Mobile and desktop</b> and enter <code>http://localhost:8000/api/accounts/outlook/callback</code>.</span></li>
            <li><strong>Add mail permissions.</strong><span>Add delegated <code>Mail.Read</code> and <code>User.Read</code> permissions.</span></li>
            <li><strong>Copy the client ID.</strong><span>Copy the <b>Application (client) ID</b> from the registration overview and enter it below.</span></li>
          </GuideSection><div className="connection-dialog-action"><label>Application (client) ID<input value={outlookId} onChange={event => setOutlookId(event.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label><button type="button" className="onboarding-secondary" disabled={busy || !outlookId.trim()} onClick={importOutlook}>Confirm application ID</button></div></>}
          {outlookAvailable && <div className="connection-dialog-action"><button type="button" className="onboarding-primary" disabled={busy} onClick={() => connect('outlook')}>Continue with Microsoft <ArrowRight size={16} /></button></div>}
        </>}
      </div>
    </section>
  </div>, document.body)
}
