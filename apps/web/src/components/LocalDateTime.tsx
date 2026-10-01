'use client'

import { useEffect, useState } from 'react'

const moments = [
  { start: 0, label: 'Midnight', emoji: '✨' },
  { start: 4, label: 'Early morning', emoji: '🌅' },
  { start: 7, label: 'Morning', emoji: '🌤️' },
  { start: 12, label: 'Noon', emoji: '🌞' },
  { start: 14, label: 'Afternoon', emoji: '☀️' },
  { start: 18, label: 'Evening', emoji: '🌙' },
  { start: 21, label: 'Night', emoji: '⭐' },
] as const

function ordinalSuffix(day: number) {
  return day % 100 >= 11 && day % 100 <= 13
    ? 'th'
    : day % 10 === 1 ? 'st' : day % 10 === 2 ? 'nd' : day % 10 === 3 ? 'rd' : 'th'
}

export function LocalDateTime() {
  // The server cannot know the visitor's computer time zone. Fill this after hydration.
  const [now, setNow] = useState<Date | null>(null)

  useEffect(() => {
    const refresh = () => setNow(new Date())
    refresh()
    const interval = window.setInterval(refresh, 1_000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [])

  if (!now) return <span className="local-date-time" aria-hidden="true" />

  const hour = now.getHours()
  const moment = [...moments].reverse().find(({ start }) => hour >= start) ?? moments[0]
  const day = now.getDate()
  const month = now.toLocaleString('en-GB', { month: 'long' }).toLowerCase()
  const time = now.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  const localDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  return (
    <span className="local-date-time">
      <time dateTime={localDate}>{String(day).padStart(2, '0')}<sup>{ordinalSuffix(day)}</sup> {month} {now.getFullYear()}</time>
      <span className="time-of-day" title={`${moment.label} · ${time}`} aria-label={`${moment.label}, local time ${time}`} tabIndex={0}>
        <span className="time-of-day-emoji" key={moment.label} aria-hidden="true">{moment.emoji}</span>
      </span>
    </span>
  )
}
