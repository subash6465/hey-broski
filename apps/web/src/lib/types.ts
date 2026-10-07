export type Source = {
  source_type: 'email' | 'calendar' | 'document'
  source_id: string
  account_label: string
  title: string
  snippet: string
  timestamp: string
}

export type ActionCard = {
  id: string
  card_type: string
  title: string
  description: string
  priority: 'urgent' | 'high' | 'medium' | 'low'
  status: 'pending' | 'completed' | 'dismissed' | 'approved' | 'failed'
  due_at?: string | null
  confidence: number
  source_refs: Source[]
  completion_origin?: 'reminder' | 'mail' | 'manual' | null
  created_at?: string | null
  updated_at?: string | null
}

export type ActionDetails = {
  card: ActionCard
  mails: { source_id: string; title: string; sender: string; sent_at: string; account_label: string; body: string; available: boolean }[]
  activity: { event_type: string; comment: string; source_id: string | null; created_at: string }[]
}

export type GeneratedBy = 'ollama' | 'metadata' | 'coverage' | 'agent'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  actionCards?: ActionCard[]
  generatedBy?: GeneratedBy
  turnId?: string
  createdAt?: string
  responseTimeMs?: number | null
}

export type ChatSession = {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

export type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  metadata: { sources?: Source[]; action_cards?: ActionCard[]; generated_by?: GeneratedBy }
  turn_id: string
  created_at: string
  updated_at: string
  response_time_ms: number | null
}

export type DocumentRecord = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
  preview: string
}
