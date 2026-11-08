"""Graph Memory construction, traversal, and bounded expansion."""

import pytest

from backend.graph_memory import MemoryGraph, expand_graph_memories, graph_for
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.schemas import (
    CandidateMemory, GenerationResult, GenerationTrace, Memory, RetrievalResult,
)
from evaluation.graph_answer import run_pair, summarize
from evaluation.graph_memory import run as run_graph_evaluation


def memory(
    memory_id: str,
    *,
    subject: str = "Jon",
    attribute: str | None,
    value: str | None,
    content: str,
    session: int,
    turn: int,
) -> Memory:
    return Memory.model_validate({
        "memory_id": memory_id,
        "subject": subject,
        "type": "event" if attribute is None else "state",
        "attribute": attribute,
        "value": value,
        "content": content,
        "time": {"session_id": f"session_{session}", "date_time": f"2023-01-{session:02d}"},
        "evidence": [{"session_id": f"session_{session}", "dia_id": f"D{session}:{turn}"}],
    })


def retrieval(seed: Memory, question: str) -> RetrievalResult:
    return RetrievalResult(
        sample_id="sample",
        question=question,
        top_k=1,
        strategy="bm25",
        candidates=[CandidateMemory(memory=seed, score=1, rank=1)],
    )


def test_graph_builds_structural_and_temporal_edges():
    first = memory(
        "m1", attribute="studio.lifecycle", value="planned",
        content="Jon plans to open a dance studio.", session=1, turn=1,
    )
    second = memory(
        "m2", attribute="studio.lifecycle", value="open",
        content="Jon's dance studio is open.", session=2, turn=1,
    )
    document = MemoryGraph("sample", [first, second]).document()
    node_types = {node.node_type for node in document.nodes}
    relations = {edge.relation for edge in document.edges}

    assert {"memory", "subject", "slot", "value", "session", "turn"} <= node_types
    assert {"ABOUT", "IN_SLOT", "HAS_VALUE", "OBSERVED_IN", "SUPPORTED_BY", "NEXT_STATE"} <= relations
    assert document.memory_count == 2


def test_collection_slot_is_connected_but_not_falsely_labeled_as_state_evolution():
    first = memory(
        "m1", attribute="favorite_activity", value="hiking",
        content="Jon likes hiking.", session=1, turn=1,
    )
    second = memory(
        "m2", attribute="favorite_activity", value="dancing",
        content="Jon likes dancing.", session=2, turn=1,
    )
    document = MemoryGraph("sample", [first, second]).document()
    assert sum(edge.relation == "IN_SLOT" for edge in document.edges) == 2
    assert not any(edge.relation == "NEXT_STATE" for edge in document.edges)


def test_graph_recovers_same_slot_history_with_auditable_path():
    first = memory(
        "m1", attribute="studio.lifecycle", value="planned",
        content="Jon plans to open a dance studio.", session=1, turn=1,
    )
    second = memory(
        "m2", attribute="studio.lifecycle", value="open",
        content="Jon's dance studio is now open.", session=2, turn=1,
    )
    expanded, trace = expand_graph_memories(
        retrieval(first, "What is Jon's current studio status?"), [first, second],
        enabled=True, max_hops=2, max_new_memories=5,
    )

    assert trace.stop_reason == "expanded"
    assert trace.added_memory_ids == ["m2"]
    assert trace.paths[0].memory_id == "m2"
    assert trace.paths[0].relations[0] == "NEXT_STATE"
    assert expanded.candidates[1].candidate_source == "graph_expansion"
    assert expanded.candidates[1].graph_path == trace.paths[0].node_ids


def test_graph_ranks_question_relevant_state_ahead_of_closer_irrelevant_state():
    seed = memory(
        "m1", attribute="business.status", value="open",
        content="Jon opened a local business.", session=1, turn=1,
    )
    unrelated = memory(
        "m2", attribute="business.status", value="renovated",
        content="Jon renovated the building's roof.", session=2, turn=1,
    )
    relevant = memory(
        "m3", attribute="business.status", value="classes_available",
        content="Jon offers contemporary dance classes.", session=3, turn=1,
    )
    expanded, trace = expand_graph_memories(
        retrieval(seed, "What dance classes does Jon offer?"), [seed, unrelated, relevant],
        enabled=True, max_hops=2, max_new_memories=1,
    )

    assert [candidate.memory.memory_id for candidate in expanded.candidates] == ["m1", "m3"]
    assert trace.added_memory_ids == ["m3"]
    assert trace.truncated is True


def test_three_hop_turn_path_recovers_related_neighbor():
    seed = memory(
        "m1", attribute=None, value=None,
        content="Jon discussed a coding project.", session=1, turn=1,
    )
    neighbor = memory(
        "m2", attribute=None, value=None,
        content="Jon's friend joined the coding project.", session=1, turn=2,
    )
    expanded, trace = expand_graph_memories(
        retrieval(seed, "Who joined Jon's coding project?"), [seed, neighbor],
        enabled=True, max_hops=3, max_new_memories=5,
    )

    assert trace.added_memory_ids == ["m2"]
    assert trace.paths[0].relations == ["SUPPORTED_BY", "NEXT_TURN", "SUPPORTED_BY"]
    assert expanded.candidates[-1].graph_hops == 3


def test_graph_budget_is_bounded_without_dropping_initial_candidates():
    memories = [
        memory(
            f"m{index}", attribute="studio.lifecycle", value=f"stage_{index}",
            content=f"Jon's studio reached stage {index}.", session=index, turn=1,
        )
        for index in range(1, 5)
    ]
    expanded, trace = expand_graph_memories(
        retrieval(memories[0], "How did Jon's studio lifecycle change?"), memories,
        enabled=True, max_hops=4, max_new_memories=1,
    )

    assert len(expanded.candidates) == 2
    assert expanded.candidates[0].memory.memory_id == "m1"
    assert trace.truncated is True
    assert trace.stop_reason == "candidate_limit"
    assert trace.eligible_memory_count >= 2


def test_disabled_graph_is_a_noop():
    seed = memory(
        "m1", attribute="status", value="open", content="Jon's studio is open.",
        session=1, turn=1,
    )
    original = retrieval(seed, "What is Jon's status?")
    expanded, trace = expand_graph_memories(original, [seed], enabled=False)
    assert expanded == original
    assert trace.stop_reason == "disabled"
    assert trace.nodes == []


def test_enabled_graph_without_usable_seed_fails_closed():
    original = RetrievalResult(
        sample_id="sample",
        question="What changed?",
        top_k=1,
        strategy="bm25",
        candidates=[],
        degraded=True,
    )
    expanded, trace = expand_graph_memories(original, [], enabled=True)

    assert expanded == original
    assert trace.enabled is True
    assert trace.stop_reason == "no_seed"
    assert trace.added_memory_ids == []


@pytest.mark.parametrize(
    ("max_hops", "max_new_memories", "message"),
    [
        (0, 5, "max_hops"),
        (5, 5, "max_hops"),
        (1, 0, "max_new_memories"),
        (1, 51, "max_new_memories"),
    ],
)
def test_graph_rejects_out_of_range_traversal_limits(
    max_hops: int, max_new_memories: int, message: str,
):
    seed = memory(
        "m1", attribute="status", value="open", content="Jon's studio is open.",
        session=1, turn=1,
    )
    with pytest.raises(ValueError, match=message):
        expand_graph_memories(
            retrieval(seed, "What is Jon's status?"), [seed], enabled=True,
            max_hops=max_hops, max_new_memories=max_new_memories,
        )


def test_graph_document_is_deterministic_and_cache_tracks_memory_content():
    first = memory(
        "m1", attribute="studio.lifecycle", value="planned",
        content="Jon plans to open a dance studio.", session=1, turn=1,
    )
    second = memory(
        "m2", attribute="studio.lifecycle", value="open",
        content="Jon's dance studio is open.", session=2, turn=1,
    )

    forward = MemoryGraph("sample", [first, second]).document().model_dump_json()
    reverse = MemoryGraph("sample", [second, first]).document().model_dump_json()
    assert forward == reverse

    cached = graph_for("cache-sample", [first, second])
    assert graph_for("cache-sample", [first, second]) is cached
    changed = second.model_copy(update={"content": "Jon's studio has permanently closed."})
    assert graph_for("cache-sample", [first, changed]) is not cached


def test_offline_evaluation_scores_gold_only_after_graph_retrieval():
    seed = memory(
        "m1", attribute="studio.lifecycle", value="planned",
        content="Jon plans to open a dance studio.", session=1, turn=1,
    )
    target = memory(
        "m2", attribute="studio.lifecycle", value="open",
        content="Jon's dance studio is now open.", session=2, turn=1,
    )

    class Store:
        def memories(self, sample_id):
            return [seed, target] if sample_id == "sample" else None

    class Retriever:
        name = "bm25"

        def retrieve(self, question, memories, top_k, *, sample_id=""):
            return retrieval(seed, question)

    report = run_graph_evaluation(
        [{
            "sample_id": "sample",
            "question": "What is Jon's current studio status?",
            "required_memory_ids": ["m2"],
            "evidence": ["D2:1"],
        }],
        Store(), Retriever(), top_k=1, max_hops=2, max_graph_memories=1,
    )
    assert report["summary"]["fixed_k"]["mean_memory_recall"] == 0
    assert report["summary"]["graph_memory"]["mean_memory_recall"] == 1


def test_paired_answer_evaluation_measures_graph_f1_with_identical_generator():
    seed = memory(
        "m1", attribute="studio.lifecycle", value="planned",
        content="Jon plans to open a dance studio.", session=1, turn=1,
    )
    target = memory(
        "m2", attribute="studio.lifecycle", value="open",
        content="Jon's dance studio is now open.", session=2, turn=1,
    )

    class Store:
        def memories(self, sample_id):
            return [seed, target] if sample_id == "sample" else None

    class Retriever:
        def retrieve(self, question, memories, top_k, *, sample_id=""):
            return retrieval(seed, question)

    class Generator:
        provider = "test_double"
        model = "graph-aware"

        def generate(self, question, context):
            found = "[id:m2]" in context
            return GenerationResult(
                answer="open" if found else "planned",
                memory_ids=["m2" if found else "m1"],
                trace=GenerationTrace(
                    provider=self.provider, model=self.model, status="answered", api_called=True,
                ),
            )

    report = run_pair(
        [{
            "sample_id": "sample",
            "question": "What is Jon's current studio status?",
            "required_memory_ids": ["m2"],
            "evidence": ["D2:1"],
            "expected_answer": "open",
        }],
        Store(), Retriever(), RuleBasedDynamicStateResolver(), Generator(),
        top_k=1, max_hops=2, max_graph_memories=1,
    )
    summary = summarize(report)

    assert summary["methods"]["fixed_k"]["mean_f1"] == 0
    assert summary["methods"]["graph_memory"]["mean_f1"] == 1
    assert summary["paired"]["improved"] == 1
    assert report["cases"][0]["graph_memory"]["graph"]["added_memory_ids"] == ["m2"]
