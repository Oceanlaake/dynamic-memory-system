"""Explicit LLM test double; never used by production or F1 benchmarks."""

from backend.schemas import GenerationResult, GenerationTrace


class FixtureAnswerGenerator:
    provider = "test_double"
    model = "fixture-not-a-real-model"

    def generate(self, question, context):
        answer, ids = None, []
        if question == "How long did it take for Jon to open his studio?":
            answer = "It took Jon six months to open his studio."
            ids = ["mem-conv30-001", "mem-conv30-004"]
        elif question == "What is Jon's favorite style of dance?":
            answer, ids = "Jon's favorite dance style is contemporary dance.", ["mem-conv30-003"]
        elif question == "When is Jon's dance studio opening?":
            answer, ids = "20 June, 2023", ["mem-conv30-004"]
        elif "studio status" in question and "[id:m2]" in context:
            answer, ids = "Jon's studio is open.", ["m2"]
        elif "studio status" in question and "[id:m1]" in context:
            answer, ids = "Jon's studio is planned.", ["m1"]
        return GenerationResult(answer=answer, memory_ids=ids, trace=GenerationTrace(
            provider=self.provider, model=self.model, status="answered" if answer else "refused",
            api_called=True, context_chars=len(context),
        ))
