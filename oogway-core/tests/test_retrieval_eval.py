import unittest

from oogway_core.repository import MemoryHit
from oogway_core.retrieval_eval import evaluate_retrieval


class FakeRetriever:
    def retrieve(self, query, *, limit=5):
        if query == "known":
            return [MemoryHit("id", "text", "source.txt", 1, 0.2, 0.8, 0.6)]
        return []


class RetrievalEvaluationTests(unittest.TestCase):
    def test_scores_positive_and_negative_cases(self):
        report = evaluate_retrieval(
            FakeRetriever(),
            {
                "cases": [
                    {"id": "positive", "query": "known", "expected_sources": ["source.txt"]},
                    {"id": "negative", "query": "unknown"},
                ]
            },
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.positive_hit_rate, 1.0)
        self.assertEqual(report.negative_rejection_rate, 1.0)
        self.assertEqual(report.mean_reciprocal_rank, 1.0)


if __name__ == "__main__":
    unittest.main()
