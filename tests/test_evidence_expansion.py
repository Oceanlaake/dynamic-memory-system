"""Factual queries and unstructured events must reach bounded evidence retrieval."""

from backend.query import resolve_query
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.retrieval.expansion import expand_state_slots
from tests.test_contract import validator_for
from tests.test_expansion import memory, retrieval


def sourced(key, content, *, attribute=None, subject="Maya", turn="D2:5", value=None):
    item = memory(key, value, attribute=attribute, subject=subject, content=content,
                  session="session_2")
    return item.model_copy(update={"evidence": [item.evidence[0].model_copy(update={"dia_id": turn})]})


def test_factual_names_question_recovers_same_slot_without_dynamic_gate():
    seed = sourced("s", "Maya has two dogs.", attribute="pet_ownership", value="two_dogs")
    names = sourced("n", "Maya's dogs are named Max and Daisy.", attribute="pet_ownership",
                    value="dogs_named_max_and_daisy", turn="D9:3")
    initial = retrieval(seed, question="What are the names of Maya's dogs?")
    result = resolve_query(initial, [seed, names], RuleBasedDynamicStateResolver(), expand_slots=True)
    assert result.expansion.question_type == "factual"
    assert result.expansion.expansion_policy == "query_evidence"
    assert result.expansion.added_memory_ids == ["n"]
    assert result.candidate_memories[1].candidate_source == "slot_expansion"
    assert result.candidate_memories[1].expansion_reason == "same_slot"
    assert result.answer is not None
    assert not any(r.relation == "CONFLICT" for r in result.relations)
    assert len(initial.candidates) == 1


def test_null_attribute_event_is_found_from_adjacent_source_turn():
    seed = sourced("s", "Maya attended a yoga class.")
    event = sourced("e", "Maya went to yoga with her colleague Rob.", turn="D2:6")
    unrelated = sourced("u", "Maya bought a bicycle.", turn="D2:6")
    result, trace = expand_state_slots(
        retrieval(seed, question="Who did Maya go to yoga with?"),
        [seed, event, unrelated], enabled=True,
    )
    assert trace.added_memory_ids == ["e"]
    assert result.candidates[1].candidate_source == "context_expansion"
    assert result.candidates[1].expansion_reason == "adjacent_turn"
    validator_for("retrieval.schema.json", "CandidateMemory").validate(
        result.candidates[1].model_dump(mode="json"),
    )
    validator_for("query.schema.json", "ExpansionTrace").validate(trace.model_dump())


def test_null_attributes_do_not_form_a_global_shared_slot():
    seed = sourced("s", "Maya attended yoga.")
    distant = sourced("e", "Maya attended yoga with Rob.", turn="D9:6")
    _, trace = expand_state_slots(retrieval(seed, question="Who did Maya attend yoga with?"),
                                 [seed, distant], enabled=True)
    assert trace.stop_reason == "no_new_memory"


def test_neighbor_with_other_subject_must_explicitly_mention_queried_person():
    seed = sourced("s", "Maya attended yoga.")
    correct = sourced("c", "Rob invited Maya to yoga.", subject="Rob", turn="D2:6")
    unrelated = sourced("u", "Rob invited Julia to yoga.", subject="Rob", turn="D2:6")
    _, trace = expand_state_slots(retrieval(seed, question="Who invited Maya to yoga?"),
                                 [seed, correct, unrelated], enabled=True)
    assert trace.added_memory_ids == ["c"]


def test_collection_is_a_retrieval_cue_without_becoming_an_exclusive_state():
    seed = sourced("s", "Maya enjoys gardening.", attribute="hobby", value="gardening")
    extra = sourced("e", "Maya grows roses in her garden.", attribute="hobby", value="growing_roses")
    result = resolve_query(retrieval(seed, question="Which garden hobbies does Maya enjoy?"),
                           [seed, extra], RuleBasedDynamicStateResolver(), expand_slots=True)
    assert result.expansion.added_memory_ids == ["e"]
    assert result.relations == []
    assert result.answer is not None


def test_factual_budget_does_not_claim_truncated_state_history_or_force_refusal():
    seed = sourced("s", "Maya enjoys gardening.", attribute="hobby", value="gardening")
    extras = [sourced(f"e{i}", f"Maya grows garden plants variety {i}.", attribute="hobby", value=f"plant{i}")
              for i in range(4)]
    result = resolve_query(retrieval(seed, question="Which garden hobbies does Maya enjoy?"),
                           [seed, *extras], RuleBasedDynamicStateResolver(),
                           expand_slots=True, max_expansion_memories=1)
    assert len(result.candidate_memories) == 2
    assert result.expansion.budget_limited
    assert not result.expansion.truncated
    assert result.expansion.eligible_count == 4
    assert result.answer is not None


def test_possessive_s_does_not_create_a_subject_only_evidence_seed():
    seed = sourced("s", "Maya's studio is open.", attribute="studio.status", value="open")
    _, trace = expand_state_slots(retrieval(seed, question="What is Maya's gender?"),
                                 [seed], enabled=True)
    assert trace.stop_reason == "no_seed"


def test_factual_expansion_preserves_explicit_contradiction_checks():
    opened = sourced("o", "Maya's library is open.", attribute="library.status", value="open")
    closed = sourced("c", "Maya's library is closed.", attribute="library.status", value="closed")
    result = resolve_query(retrieval(opened, question="Is Maya's library open?"),
                           [opened, closed], RuleBasedDynamicStateResolver(), expand_slots=True)
    assert result.expansion.added_memory_ids == ["c"]
    assert result.evidence_status == "conflict"
    assert result.answer is None
