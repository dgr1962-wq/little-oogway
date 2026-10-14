import unittest

from oogway_core.adapter import RoundtableParticipantAdapter
from oogway_core.models import ModelResponse
from oogway_core.session import ConversationSession

from test_session import FakeModel, FakeStore


class RoundtableParticipantAdapterTests(unittest.TestCase):
    def test_implements_roundtable_response_shape(self):
        adapter = RoundtableParticipantAdapter(
            ConversationSession(model=FakeModel(), store=FakeStore())
        )
        content, metadata = adapter.respond("What matters?")
        self.assertEqual(adapter.name, "little-oogway")
        self.assertEqual(content, "answer")
        self.assertEqual(metadata["kind"], "oogway-core")
        self.assertIn("conversation_id", metadata)
        self.assertIn("round_id", metadata)


if __name__ == "__main__":
    unittest.main()
