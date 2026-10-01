import type { Metadata } from 'next'
import '@fontsource-variable/dm-sans/wght.css'
import '@fontsource-variable/manrope/wght.css'
import '@fontsource/dm-mono/400.css'
import './globals.css'
import './glass.css'
import './onboarding.css'

export const metadata: Metadata = {
  title: 'Hey Broski',
  description: 'Local-first personal admin AI assistant',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
