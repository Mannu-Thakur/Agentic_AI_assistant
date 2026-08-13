export interface ToolCall {
  name: string;
  args: Record<string, any>;
  result?: string;
  status: 'running' | 'completed' | 'failed';
}

export interface SourceDocument {
  index: number;
  filename: string;
  content: string;
  distance?: number;
  confidence?: number;
  chunk_id?: number;
  document_id?: string;
  used: boolean;         // true = CRAG-validated and injected into LLM prompt
  url?: string;          // actual webpage URL for web search results (clickable link)
  source?: string;       // provider: 'tavily' | 'serpapi' | 'exa' | 'duckduckgo'
  sub_question?: string; // which sub-question this source answered (compound queries)
}

export interface DeveloperMetrics {
  model_used: string;
  latency_ms: number;
  tokens_input: number;
  tokens_output: number;
  cost_estimate: number;
  confidence_score: number;
  memory_hits: number;
  search_queries?: string[];
  chunks_used?: number;
  steps?: string[];
  generation_mode?: 'normal_rag' | 'model_knowledge' | 'crag_rejected' | 'web_fallback';
  execution_trace?: Array<{
    name: string;
    status: 'EXECUTED' | 'BYPASSED' | 'FAILED';
    timestamp?: number;
    duration_ms?: number;
    reason?: string;
    metadata?: Record<string, any>;
    error?: string;
  }>;
  semantic_status?: {
    retrieval_status: string;
    embedding_executed?: boolean;
    vector_search_executed?: boolean;
    rag_chunks?: number;
    reranked_chunks?: number;
    graded_chunks?: number;
    confidence?: number;
  };
  memory_status?: {
    lookup_status: string;
    memory_hits?: number;
    injected_into_prompt?: boolean;
    write_executed?: boolean;
    persisted_content?: string;
  };
  web_status?: {
    executed: boolean;
    reason?: string;
    results_count?: number;
    accepted_sources_count?: number;
    used_in_final_answer?: boolean;
    queries?: string[];
  };
  inconsistencies?: string[];
  // retrieved_context: ALL items fetched from vector store (for dev debug panel only)
  retrieved_context?: {
    type: 'memory' | 'chunk';
    filename: string;
    category?: string;
    content: string;
    importance_score?: number;
    distance?: number;
    confidence?: number;
    used?: boolean;
  }[];
  // source_documents: AUTHORITATIVE — only CRAG-validated, used=true chunks.
  // This is the ONLY field that should be used for the Sources UI.
  source_documents?: SourceDocument[];
}

export interface Message {
  id: string;
  chat_id: string;
  parent_id: string | null;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls: ToolCall[] | null;
  developer_metrics: DeveloperMetrics | null;
  created_at: string;
  images?: Array<{ base64: string; mimeType: string }>;  // persisted from backend
  imagePreviewUrls?: string[];                            // derived client-side
}

export interface ChatSession {
  id: string;
  title: string;
  is_pinned: boolean;
  is_favorite: boolean;
  is_shared: boolean;
  share_id: string | null;
  is_live_share: boolean;
  created_at: string;
  updated_at: string;
}
