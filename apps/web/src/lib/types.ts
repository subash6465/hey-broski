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
