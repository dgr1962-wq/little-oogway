import unittest

from oogway_core.repository import MemoryHit
from oogway_core.retrieval import select_diverse_hits


def hit(source, ordinal, score, content="content"):
    return MemoryHit(
        memory_id=f"{source}-{ordinal}",
        content=content,
        source_locator=source,
        source_ordinal=ordinal,
        lexical_score=0.0,
        semantic_score=score,
        combined_score=score,
    )


class RetrievalQualityTests(unittest.TestCase):
    def test_rejects_weak_and_adjacent_chunks(self):
        selected = select_diverse_hits(
            [
                hit("a.txt", 10, 0.8, "first"),
                hit("a.txt", 11, 0.79, "overlap"),
                hit("b.txt", 3, 0.7, "second"),
                hit("a.txt", 20, 0.6, "third"),
                hit("c.txt", 1, 0.39, "weak"),
            ],
            limit=5,
        )
        self.assertEqual(
            [(item.source_locator, item.source_ordinal) for item in selected],
            [("a.txt", 10), ("b.txt", 3), ("a.txt", 20)],
        )

    def test_enforces_source_cap(self):
        selected = select_diverse_hits(
            [
                hit("a.txt", 1, 0.9, "one"),
                hit("a.txt", 10, 0.8, "two"),
                hit("a.txt", 20, 0.7, "three"),
            ],
            limit=5,
        )
        self.assertEqual(len(selected), 2)

    def test_suppresses_equivalent_content_across_sources(self):
        selected = select_diverse_hits(
            [
                hit("a.txt", 1, 0.9, "Same  remembered text"),
                hit("b.txt", 20, 0.8, "same remembered TEXT"),
                hit("c.txt", 3, 0.7, "different text"),
            ],
            limit=5,
        )
        self.assertEqual([item.source_locator for item in selected], ["a.txt", "c.txt"])


if __name__ == "__main__":
    unittest.main()
