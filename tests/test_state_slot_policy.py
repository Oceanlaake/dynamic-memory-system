"""State versus collection behavior; keep genuine contradictions observable."""

import pytest

from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.dynamic_state.question import question_type
from backend.retrieval.expansion import expand_state_slots
from tests.test_expansion import memory, query, retrieval


@pytest.mark.parametrize("question", [
    "What does Maya's library offer?", "What is Maya offering to readers?",
    "What is Maya working on opening?", "What does Maya's tattoo symbolize?",
])
def test_plain_present_tense_does_not_request_a_state_history(question):
    assert question_type(question) == "factual"


@pytest.mark.parametrize("question, kind", [
    ("What is Maya's library status now?", "current_state"),
    ("What is Maya's favorite genre?", "current_state"),
    ("Where does Maya live?", "current_state"),
    ("Does Maya still work at Acme?", "current_state"),
    ("How has Maya's library status changed?", "change"),
    ("How long did it take for Maya to open the library?", "duration"),
])
def test_explicit_state_questions_remain_dynamic(question, kind):
    assert question_type(question) == kind


def test_primary_dimension_prevents_unrelated_conflict_from_vetoing_answer():
    financial = memory("f1", "profitable", attribute="studio.finance", session="unknown")
    contradictory = memory("f2", "bankrupt", attribute="studio.finance", session="unknown")
    old = memory("m1", "planned", date="2023-01-01")
    new = memory("m2", "open", date="2023-02-01", session="session_2")
    # A generic subject/topic hit ranks above the specific state dimension.
    initial = retrieval(financial, contradictory, old)
    result = query(initial, [financial, contradictory, old, new], expand_slots=True)
    assert result.expansion.added_memory_ids == ["m2"]
    assert [s.attribute for s in result.expansion.expanded_slots] == ["studio.status"]
    assert result.answer == new.content
    assert any(r.relation == "CONFLICT" for r in result.relations)
    assert result.evidence_status == "sufficient"


def test_preference_query_does_not_expand_other_favorite_dimensions():
    activity = memory("a1", "reading", attribute="favorite_activity")
    genre = memory("g1", "fantasy", attribute="favorite_book_genre")
    result, trace = expand_state_slots(
        retrieval(activity, genre, question="What is Jon's favorite book genre?"),
        [activity, genre, memory("a2", "running", attribute="favorite_activity")], enabled=True,
    )
    assert [s.attribute for s in trace.expanded_slots] == ["favorite_book_genre"]
    assert len(result.candidates) == 2


def test_broad_collection_without_a_comparable_seed_keeps_initial_answer():
    first = memory("m1", "build_library", subject="Maya", attribute="future_plan",
                   content="Maya plans to build a library.")
    other = memory("m2", "learn_piano", subject="Maya", attribute="future_plan")
    result = query(retrieval(first, question="What is Maya's current library plan?"),
                   [first, other], expand_slots=True)
    assert result.expansion.stop_reason == "not_comparable"
    assert result.expansion.added_memory_ids == []
    assert result.answer == first.content


@pytest.mark.parametrize("attribute", ["business_venture", "future_plan", "creative_project"])
def test_unordered_different_collection_facts_are_not_invented_conflicts(attribute):
    first = memory("m1", "open_library", subject="Maya", attribute=attribute, session="unknown",
                   content="Maya wants to open a library.")
    second = memory("m2", "garden_location", subject="Maya", attribute=attribute, session="unknown",
                    content="Maya wants the library to be next to a garden.")
    result = RuleBasedDynamicStateResolver().resolve(
        retrieval(first, second, question="What is Maya's library project?"),
    )
    assert result.relations == []  # Neither compatibility nor incompatibility was established.
    assert result.answer == first.content


@pytest.mark.parametrize("attribute", ["library.status", "business_venture"])
def test_explicit_opposites_remain_conflicts_including_in_a_collection_field(attribute):
    first = memory("m1", "open", subject="Maya", attribute=attribute, session="unknown",
                   content="Maya's library is open.")
    second = memory("m2", "closed", subject="Maya", attribute=attribute, session="unknown",
                    content="Maya's library is closed.")
    result = query(retrieval(first, second, question="What is Maya's library status now?"),
                   [first, second], expand_slots=True)
    assert result.answer is None
    assert result.evidence_status == "conflict"
    assert any(r.relation == "CONFLICT" for r in result.relations)


def test_missing_values_do_not_imply_that_different_memories_confirm_each_other():
    first = memory("m1", None, content="Jon's studio is open.", session="unknown")
    second = memory("m2", None, content="Jon's studio is closed.", session="unknown")
    result = query(retrieval(first, second), [first, second])
    assert result.evidence_status == "conflict"
    assert result.answer is None


@pytest.mark.parametrize("first_value, second_value", [
    ("library_open", "library_closed"),
    ("opening_library", "not_opening_library"),
    ("library_visit_planned", "library_visit_cancelled"),
])
def test_collection_contradictions_with_context_survive_an_unrelated_middle_node(first_value, second_value):
    first = memory("m1", first_value, attribute="future_plan", session="unknown",
                   content=f"Jon's library fact: {first_value}.")
    middle = memory("m2", "garden_location", attribute="future_plan", session="unknown",
                    content="Jon wants the library to have a garden.")
    second = memory("m3", second_value, attribute="future_plan", session="unknown",
                    content=f"Jon's library fact: {second_value}.")
    result = query(retrieval(first, middle, second, question="What is Jon's library plan?"),
                   [first, middle, second])
    assert result.evidence_status == "conflict"
    assert result.answer is None
    assert any(r.from_ == "m1" and r.to == "m3" and r.relation == "CONFLICT"
               for r in result.relations)


def test_different_objects_are_not_a_contextual_contradiction():
    first = memory("m1", "library_open", attribute="business_venture", session="unknown")
    second = memory("m2", "cafe_closed", attribute="business_venture", session="unknown")
    result = query(retrieval(first, second, question="What is Jon's studio venture?"),
                   [first, second])
    assert result.evidence_status == "sufficient"
    assert result.relations == []


def test_new_scalar_state_is_still_recovered_for_a_different_subject_and_domain():
    old = memory("m1", "open", subject="Maya", attribute="library.status",
                 content="Maya's library is open.", date="2023-01-01")
    new = memory("m2", "closed", subject="Maya", attribute="library.status",
                 content="Maya's library is closed.", date="2023-02-01", session="session_2")
    initial = retrieval(old, question="What is Maya's library status now?")
    result = query(initial, [old, new], expand_slots=True)
    assert result.answer == new.content
    assert result.expansion.added_memory_ids == ["m2"]
    assert result.effective_memories[0].memory_id == "m2"
