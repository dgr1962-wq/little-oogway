import unittest

from oogway_core.models import ModelResponse
from oogway_core.session import ConversationSession
from oogway_core.tools import ToolResult


class FakeModel:
    provider = "fake"
    model_name = "test-model"

    def __init__(self, error=None):
        self.error = error
        self.system_prompt = None

    def respond(self, prompt, system_prompt):
        self.system_prompt = system_prompt
        if self.error:
            raise self.error
        return ModelResponse("answer", {"token_count": 3})


class FakeStore:
    def __init__(self):
        self.calls = []
        self.counter = 0

    def _id(self, prefix):
        self.counter += 1
        return f"{prefix}-{self.counter}"

    def register_participant(self, **values):
        self.calls.append(("participant", values))
        return self._id("participant")

    def create_conversation(self, **values):
        self.calls.append(("conversation", values))
        return self._id("conversation")

    def create_round(self, **values):
        self.calls.append(("round", values))
        return self._id("round")

    def add_turn(self, **values):
        self.calls.append(("turn", values))
        return self._id("turn")


class FakeMemory:
    memory_id = "memory-1"
    source_locator = "data/transcripts/example.txt"
    source_ordinal = 4
    content = "Remember the operator's stated intent."
    combined_score = 0.75


class FakeRetriever:
    def retrieve(self, query, *, limit=5):
        return [FakeMemory()]


class FakeTool:
    name = "test_tool"

    def try_execute(self, prompt):
        if prompt == "use tool":
            return ToolResult("tool completed", {"status": "complete"})
        return None


class ConversationSessionTests(unittest.TestCase):
    def test_persists_ordered_prompt_and_response(self):
        store = FakeStore()
        session = ConversationSession(model=FakeModel(), store=store)
        first = session.ask("  hello  ")
        second = session.ask("again")
        turns = [values for kind, values in store.calls if kind == "turn"]
        rounds = [values for kind, values in store.calls if kind == "round"]
        self.assertEqual([turn["ordinal"] for turn in turns], [0, 1, 0, 1])
        self.assertEqual([turn["content"] for turn in turns], ["hello", "answer", "again", "answer"])
        self.assertEqual([item["ordinal"] for item in rounds], [0, 1])
        self.assertEqual(first.conversation_id, second.conversation_id)

    def test_records_failed_model_turn_before_reraising(self):
        store = FakeStore()
        session = ConversationSession(
            model=FakeModel(RuntimeError("model unavailable")), store=store
        )
        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            session.ask("hello")
        turns = [values for kind, values in store.calls if kind == "turn"]
        self.assertEqual(turns[-1]["status"], "failed")
        self.assertEqual(turns[-1]["metadata"]["error_type"], "RuntimeError")

    def test_rejects_blank_prompt_without_writes(self):
        store = FakeStore()
        session = ConversationSession(model=FakeModel(), store=store)
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            session.ask("  ")
        self.assertEqual(store.calls, [])

    def test_retrieved_memory_is_untrusted_context_and_recorded(self):
        store = FakeStore()
        model = FakeModel()
        session = ConversationSession(
            model=model,
            store=store,
            memory_retriever=FakeRetriever(),
        )
        response = session.ask("What was intended?")
        self.assertIn("untrusted historical memory", model.system_prompt)
        self.assertIn("Remember the operator's stated intent.", model.system_prompt)
        self.assertEqual(
            response.metadata["retrieved_memories"][0]["memory_id"],
            "memory-1",
        )
        self.assertIn("Memory sources consulted:", response.content)
        self.assertIn("[memory:memory-1]", response.content)
        self.assertEqual(response.metadata["citation_validation"]["source_count"], 1)
        response_turn = [values for kind, values in store.calls if kind == "turn"][-1]
        self.assertIn("retrieved_memories", response_turn["metadata"])

    def test_bounded_tool_result_is_persisted_without_model_call(self):
        store = FakeStore()
        model = FakeModel(RuntimeError("model must not run"))
        session = ConversationSession(model=model, store=store, tools=(FakeTool(),))
        response = session.ask("use tool")
        self.assertEqual(response.content, "tool completed")
        self.assertEqual(response.metadata["tool_execution"]["status"], "complete")
        response_turn = [values for kind, values in store.calls if kind == "turn"][-1]
        self.assertEqual(response_turn["provenance"]["source"], "bounded-tool")
        self.assertEqual(response_turn["provenance"]["tool"], "test_tool")


if __name__ == "__main__":
    unittest.main()
