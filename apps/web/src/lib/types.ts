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

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  actionCards?: ActionCard[]
  generatedBy?: 'demo' | 'ollama'
}

export type DocumentRecord = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
  preview: string
}
