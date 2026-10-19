/**
 * 与 APIs/retrieval.schema.json、APIs/query.schema.json 一一对应的前端类型。
 * 后端契约变更时必须同步修改本文件，字段名不要重命名。
 */

export type MemoryType = "state" | "event" | "goal" | "preference" | "requirement";
export type RelationType = "RETAIN" | "UPDATE" | "SUPERSEDE" | "CONFLICT";
export type MatchSource = "keyword" | "embedding" | "subject_boost";
export type Strategy = "bm25" | "embedding" | "hybrid";

export interface EvidenceRef {
  session_id: string;
  dia_id: string;
  quote?: string | null;
}

export interface MemoryTime {
  session_id: string;
  /** 对话 / Session 发生时间 */
  date_time?: string | null;
  /** 事件发生或状态生效时间（YYYY-MM-DD）；无法确定时为 null */
  effective_at?: string | null;
}

export interface Memory {
  memory_id: string;
  subject: string;
  type: MemoryType;
  content: string;
  attribute?: string | null;
  value?: string | null;
  time: MemoryTime;
  evidence: EvidenceRef[];
  confidence?: number | null;
}

export interface RetrievalRequest {
  sample_id: string;
  question: string;
  top_k?: number;
}

export interface CandidateMemory {
  memory: Memory;
  score: number;
  rank: number;
  matched_by?: MatchSource[];
}

export interface RetrievalResult {
  sample_id: string;
  question: string;
  top_k: number;
  strategy: Strategy;
  candidates: CandidateMemory[];
  degraded?: boolean;
}

export interface QueryRequest {
  sample_id: string;
  question: string;
  top_k?: number;
}

export interface Relation {
  from: string;
  to: string;
  relation: RelationType;
  reason: string;
}

export interface EffectiveMemory {
  memory_id: string;
  role: string;
}

export interface AnswerEvidenceRef {
  session_id: string;
  dia_id: string;
}

export interface QueryResponse {
  sample_id: string;
  question: string;
  candidate_memories: CandidateMemory[];
  relations: Relation[];
  effective_memories: EffectiveMemory[];
  answer: string | null;
  evidence: AnswerEvidenceRef[];
  degraded?: boolean;
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    detail?: Record<string, unknown> | null;
  };
}

export interface SampleSummary {
  sample_id: string;
  memory_count: number;
}

export const API_PATHS = {
  health: "/api/health",
  samples: "/api/samples",
  sampleMemories: (sampleId: string) => `/api/samples/${encodeURIComponent(sampleId)}/memories`,
  retrieve: "/api/retrieve",
  query: "/api/query",
} as const;
