export interface Citation {
  source_id: string;
  title: string;
  url?: string | null;
  excerpt?: string | null;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  locale?: string;
  user_context?: Record<string, unknown>;
}

export interface ChatResponse {
  conversation_id: string;
  response: string;
  intent: string;
  citations: Citation[];
  requires_handoff: boolean;
  emergency: boolean;
  metadata: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  intent?: string;
  emergency?: boolean;
  requiresHandoff?: boolean;
}

