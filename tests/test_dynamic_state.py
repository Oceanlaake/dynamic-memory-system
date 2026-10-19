"""B2 dynamic-state behavior tests."""

from __future__ import annotations

from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.retrieval.keyword import BM25Retriever
from backend.schemas import CandidateMemory, Memory, RetrievalResult
from backend.store import MemoryStore


QUESTION = "How long did it take for Jon to open his studio?"


def _memory(
    memory_id: str,
    *,
    value: str,
    session_id: str = "session_1",
    date_time: str | None = None,
) -> Memory:
    return Memory.model_validate(
        {
            "memory_id": memory_id,
            "subject": "Jon",
            "type": "state",
            "attribute": "project.status",
            "value": value,
            "content": f"The project status is {value}.",
            "time": {"session_id": session_id, "date_time": date_time},
            "evidence": [{"session_id": session_id, "dia_id": f"D{session_id[-1]}:1"}],
        }
    )


def _retrieval(*memories: Memory, question: str = "What is the project status?") -> RetrievalResult:
    return RetrievalResult(
        sample_id="sample",
        question=question,
        top_k=max(1, len(memories)),
        strategy="bm25",
        candidates=[
            CandidateMemory(memory=memory, score=1.0 - index / 10, rank=index + 1)
            for index, memory in enumerate(memories)
        ],
    )


def test_demo_resolves_expected_relations_answer_and_evidence():
    memories = MemoryStore().memories("conv-30")
    assert memories
    retrieval = BM25Retriever().retrieve(QUESTION, memories, 5, sample_id="conv-30")

    response = RuleBasedDynamicStateResolver().resolve(retrieval)

    relations = {(item.from_, item.to): item.relation for item in response.relations}
    assert relations[("mem-conv30-002", "mem-conv30-004")] == "SUPERSEDE"
    assert relations[("mem-conv30-004", "mem-conv30-005")] == "UPDATE"
    assert [(item.memory_id, item.role) for item in response.effective_memories] == [
        ("mem-conv30-001", "start_time"),
        ("mem-conv30-004", "opening_time"),
    ]
    assert response.answer == "It took Jon six months to open his studio."
    assert [(item.session_id, item.dia_id) for item in response.evidence] == [
        ("session_1", "D1:2"),
        ("session_15", "D15:13"),
    ]
    assert response.degraded is False


def test_later_value_supersedes_earlier_value():
    earlier = _memory("m1", value="planned", session_id="session_1")
    later = _memory("m2", value="opened", session_id="session_2")

    response = RuleBasedDynamicStateResolver().resolve(_retrieval(earlier, later))

    assert response.relations[0].relation == "SUPERSEDE"
    assert [item.memory_id for item in response.effective_memories] == ["m2"]


def test_same_value_is_retained():
    earlier = _memory("m1", value="open", session_id="session_1")
    later = _memory("m2", value="open", session_id="session_2")

    response = RuleBasedDynamicStateResolver().resolve(_retrieval(earlier, later))

    assert response.relations[0].relation == "RETAIN"
    assert response.answer is not None


def test_unordered_incompatible_values_are_conflict_and_not_answered():
    first = _memory("m1", value="open", session_id="unknown")
    second = _memory("m2", value="closed", session_id="unknown")

    response = RuleBasedDynamicStateResolver().resolve(_retrieval(first, second))

    assert response.relations[0].relation == "CONFLICT"
    assert response.effective_memories == []
    assert response.answer is None


def test_degraded_retrieval_does_not_hallucinate():
    retrieval = RetrievalResult(
        sample_id="sample",
        question="Unknown question",
        top_k=5,
        strategy="bm25",
        candidates=[],
        degraded=True,
    )

    response = RuleBasedDynamicStateResolver().resolve(retrieval)

    assert response.candidate_memories == []
    assert response.relations == []
    assert response.effective_memories == []
    assert response.answer is None
    assert response.evidence == []
    assert response.degraded is True


def test_subject_only_match_is_not_an_effective_memory():
    memories = MemoryStore().memories("conv-30")
    assert memories
    question = "What is Jon's gender?"
    retrieval = BM25Retriever().retrieve(question, memories, 5, sample_id="conv-30")
    assert retrieval.candidates

    response = RuleBasedDynamicStateResolver().resolve(retrieval)

    assert response.candidate_memories
    assert response.effective_memories == []
    assert response.answer is None
    assert response.evidence == []
    assert response.degraded is True


def test_duration_question_without_both_anchors_is_not_answered():
    memories = MemoryStore().memories("conv-30")
    assert memories
    retrieval = BM25Retriever().retrieve(QUESTION, memories, 4, sample_id="conv-30")

    response = RuleBasedDynamicStateResolver().resolve(retrieval)

    assert response.effective_memories == []
    assert response.answer is None
    assert response.evidence == []
