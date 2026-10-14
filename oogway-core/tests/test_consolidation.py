import unittest
from datetime import datetime, timezone

from oogway_core.consolidation import CanonicalCandidate, choose_canonical, shingle_containment
from oogway_core.repository import TokenSpaceRepository


class ConsolidationTests(unittest.TestCase):
    def test_detects_passage_containment_despite_case_and_spacing(self):
        shared = "one two three four five six seven eight nine ten eleven twelve " * 3
        larger = "unrelated opening words " * 3 + shared.upper() + " ending words " * 3
        self.assertGreater(shingle_containment(shared, larger), 0.95)

    def test_rejects_short_or_topically_similar_text(self):
        self.assertEqual(shingle_containment("too short", "too short"), 0.0)
        left = "memory retrieval uses vectors to find relevant historical context " * 4
        right = "database storage keeps conversation records and source provenance " * 4
        self.assertLess(shingle_containment(left, right), 0.1)

    def test_review_requires_terminal_status_and_rationale(self):
        repository = TokenSpaceRepository("unused")
        with self.assertRaisesRegex(ValueError, "confirmed or rejected"):
            repository.review_semantic_relation(
                relation_id="unused", status="proposed", rationale="reviewed"
            )
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            repository.review_semantic_relation(
                relation_id="unused", status="confirmed", rationale="  "
            )

    def test_canonical_policy_prefers_explicit_timestamp_then_completeness(self):
        older = CanonicalCandidate(
            "older", "### [Echo - 2025-06-17 10:41]\n" + "content " * 100,
            "a.txt", 1, datetime(2025, 9, 30, tzinfo=timezone.utc)
        )
        newer = CanonicalCandidate(
            "newer", "### [Echo - 2025-06-18 10:41]\n" + "content " * 20,
            "b.txt", 1, datetime(2025, 9, 29, tzinfo=timezone.utc)
        )
        self.assertEqual(choose_canonical(older, newer).preferred.memory_id, "newer")

        fuller = CanonicalCandidate("full", "word " * 100, "a.txt", 1)
        shorter = CanonicalCandidate("short", "word " * 50, "b.txt", 1)
        decision = choose_canonical(fuller, shorter)
        self.assertEqual(decision.preferred.memory_id, "full")
        self.assertEqual(decision.reason, "more_complete_passage")

    def test_canonical_policy_uses_source_time_only_as_tie_breaker(self):
        earlier = CanonicalCandidate(
            "earlier", "same length", "a.txt", 1,
            datetime(2025, 9, 29, tzinfo=timezone.utc)
        )
        later = CanonicalCandidate(
            "later", "same length", "b.txt", 1,
            datetime(2025, 9, 30, tzinfo=timezone.utc)
        )
        decision = choose_canonical(earlier, later)
        self.assertEqual(decision.preferred.memory_id, "later")
        self.assertEqual(decision.reason, "newer_source_export")


if __name__ == "__main__":
    unittest.main()
