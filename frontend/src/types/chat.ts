export interface ToolCall {
  name: string;
  args: Record<string, any>;
  result?: string;
  status: 'running' | 'completed' | 'failed';
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
  retrieved_context?: {
    type: 'memory' | 'chunk';
    filename: string;
    category?: string;
    content: string;
    importance_score?: number;
    distance?: number;
  }[];
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
}

export interface ChatSession {
  id: string;
  title: string;
  is_pinned: boolean;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
}
