import unittest

from oogway_core.public_retrieval_api import (
    MAX_EXCERPT_CHARS,
    PublicSearchRuntime,
    public_title,
    serialize_hit,
)
from oogway_core.repository import MemoryHit


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def retrieve(self, query, *, limit):
        self.calls.append((query, limit))
        return self.hits[:limit]


def hit(content="public content"):
    return MemoryHit(
        memory_id="memory-1",
        content=content,
        source_locator="https://anykeycafe.com/little-oogway/",
        source_ordinal=3,
        lexical_score=0.5,
        semantic_score=0.7,
        combined_score=0.63,
    )


class PublicRetrievalTests(unittest.TestCase):
    def test_runtime_bounds_query_and_result_count(self):
        retriever = FakeRetriever([hit()])
        runtime = PublicSearchRuntime(retriever=retriever)
        result = runtime.search("  Little Oogway  ", 5)
        self.assertEqual(retriever.calls, [("Little Oogway", 5)])
        self.assertEqual(result[0]["url"], "https://anykeycafe.com/little-oogway/")
        with self.assertRaisesRegex(ValueError, "500"):
            runtime.search("x" * 501)
        with self.assertRaisesRegex(ValueError, "between 1 and 6"):
            runtime.search("hello", 7)

    def test_serialization_truncates_and_derives_public_title(self):
        result = serialize_hit(hit("x" * (MAX_EXCERPT_CHARS + 20)))
        self.assertEqual(len(result["text"]), MAX_EXCERPT_CHARS)
        self.assertEqual(result["title"], "Little Oogway")
        self.assertEqual(public_title("https://anykeycafe.com/"), "Any Key Cafe")


if __name__ == "__main__":
    unittest.main()
