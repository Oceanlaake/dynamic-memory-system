"""Pydantic 契约模型，逐字段对应 APIs/*.schema.json。

契约以 APIs/ 下的 JSON Schema 为权威来源；本文件的改动必须同步更新 schema，
由 tests/test_contract.py 强制校验两者不会分叉。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal["state", "event", "goal", "preference", "requirement"]
RelationType = Literal["RETAIN", "UPDATE", "SUPERSEDE", "CONFLICT"]
MatchSource = Literal["keyword", "embedding", "subject_boost"]
Strategy = Literal["bm25", "embedding", "hybrid"]
QuestionType = Literal["current_state", "change", "duration", "factual"]
GraphNodeType = Literal["memory", "subject", "slot", "value", "session", "turn"]
GraphEdgeType = Literal[
    "ABOUT", "IN_SLOT", "HAS_VALUE", "OBSERVED_IN", "SUPPORTED_BY",
    "NEXT_STATE", "NEXT_TURN",
]
EvidenceStatus = Literal[
    "not_checked", "sufficient", "insufficient", "missing_anchor",
    "missing_transition", "conflict", "unorderable",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(_Strict):
    session_id: str
    dia_id: str
    quote: str | None = None


class MemoryTime(_Strict):
    session_id: str
    date_time: str | None = None
    effective_at: str | None = None


class Memory(_Strict):
    memory_id: str
    subject: str
    type: MemoryType
    content: str
    attribute: str | None = None
    value: str | None = None
    time: MemoryTime
    evidence: list[EvidenceRef] = Field(min_length=1)
    confidence: float | None = None


class RetrievalRequest(_Strict):
    sample_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class CandidateMemory(_Strict):
    memory: Memory
    score: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)
    matched_by: list[MatchSource] = Field(default_factory=list)
    candidate_source: Literal[
        "initial", "slot_expansion", "context_expansion", "graph_expansion",
    ] = "initial"
    expansion_reason: Literal[
        "same_slot", "same_turn", "adjacent_turn", "graph_path",
    ] | None = None
    graph_hops: int | None = Field(default=None, ge=1, le=4)
    graph_path: list[str] = Field(default_factory=list)


class RetrievalResult(_Strict):
    sample_id: str
    question: str
    top_k: int = Field(ge=1)
    strategy: Strategy
    candidates: list[CandidateMemory] = Field(default_factory=list)
    degraded: bool = False


class QueryRequest(_Strict):
    sample_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    expand_slots: bool = False
    max_expansion_memories: int = Field(default=50, ge=1, le=200)
    graph_expand: bool = False
    graph_max_hops: int = Field(default=3, ge=1, le=4)
    max_graph_memories: int = Field(default=5, ge=1, le=50)


class ExpandedSlot(_Strict):
    subject: str
    attribute: str


class ExpansionTrace(_Strict):
    enabled: bool
    question_type: QuestionType
    initial_count: int = Field(ge=0)
    added_memory_ids: list[str] = Field(default_factory=list)
    expanded_slots: list[ExpandedSlot] = Field(default_factory=list)
    truncated: bool = False
    expansion_policy: Literal["state_history", "query_evidence"] = "state_history"
    budget_limited: bool = False
    eligible_count: int = Field(default=0, ge=0)
    stop_reason: Literal[
        "disabled", "not_dynamic", "not_comparable", "no_seed", "no_new_memory", "expanded", "candidate_limit",
    ]


class GraphNode(_Strict):
    node_id: str
    node_type: GraphNodeType
    label: str
    memory_id: str | None = None


class GraphEdge(_Strict):
    source: str
    target: str
    relation: GraphEdgeType
    weight: float = Field(ge=0, le=1)


class GraphPath(_Strict):
    memory_id: str
    hops: int = Field(ge=1, le=4)
    node_ids: list[str] = Field(min_length=2)
    relations: list[GraphEdgeType] = Field(min_length=1)


class GraphTrace(_Strict):
    enabled: bool
    max_hops: int = Field(ge=1, le=4)
    seed_memory_ids: list[str] = Field(default_factory=list)
    added_memory_ids: list[str] = Field(default_factory=list)
    eligible_memory_count: int = Field(default=0, ge=0)
    visited_node_count: int = Field(default=0, ge=0)
    truncated: bool = False
    stop_reason: Literal[
        "disabled", "no_seed", "no_new_memory", "expanded", "candidate_limit",
    ]
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    paths: list[GraphPath] = Field(default_factory=list)


class GraphDocument(_Strict):
    sample_id: str
    memory_count: int = Field(ge=0)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Relation(_Strict):
    from_: str = Field(alias="from")
    to: str
    relation: RelationType
    reason: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EffectiveMemory(_Strict):
    memory_id: str
    role: str


class AnswerEvidenceRef(_Strict):
    session_id: str
    dia_id: str


class TokenUsage(_Strict):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    uncached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class GenerationTrace(_Strict):
    provider: str
    model: str
    response_model: str | None = None
    status: Literal["answered", "refused", "error", "skipped"]
    error_code: str | None = None
    finish_reason: str | None = None
    http_status: int | None = None
    provider_error_code: str | None = None
    raw_text: str | None = None
    api_called: bool = False
    reused: bool = False
    elapsed_ms: float = Field(default=0, ge=0)
    context_chars: int = Field(default=0, ge=0)
    context_sha256: str = ""
    max_output_tokens: int = Field(default=0, ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class GenerationResult(_Strict):
    answer: str | None = None
    memory_ids: list[str] = Field(default_factory=list)
    trace: GenerationTrace


class QueryResponse(_Strict):
    sample_id: str
    question: str
    candidate_memories: list[CandidateMemory] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    effective_memories: list[EffectiveMemory] = Field(default_factory=list)
    answer: str | None = None
    evidence: list[AnswerEvidenceRef] = Field(default_factory=list)
    degraded: bool = False
    evidence_status: EvidenceStatus = "not_checked"
    expansion: ExpansionTrace | None = None
    graph: GraphTrace | None = None
    answer_memory_ids: list[str] = Field(default_factory=list)
    generation: GenerationTrace | None = None


class ErrorBody(_Strict):
    code: str
    message: str
    detail: dict | None = None


class ErrorResponse(_Strict):
    error: ErrorBody


class SampleSummary(_Strict):
    sample_id: str
    memory_count: int
