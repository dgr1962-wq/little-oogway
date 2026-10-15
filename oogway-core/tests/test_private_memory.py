import unittest

from oogway_core.private_memory import PrivateMemorySearchRuntime
from oogway_core.repository import MemoryHit


class FakeRetriever:
    def retrieve(self, query, *, limit):
        return [MemoryHit("m1", "remembered text", "private-chat", 3, 0.1, 0.8, 0.7)]


class PrivateMemorySearchTests(unittest.TestCase):
    def test_returns_provenance_and_historical_context_notice(self):
        result = PrivateMemorySearchRuntime(FakeRetriever()).search("connections", 50)
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["memory_id"], "m1")
        self.assertEqual(result["results"][0]["source"], "private-chat")
        self.assertIn("historical", result["security_notice"])


if __name__ == "__main__":
    unittest.main()
