import unittest

from oogway_core.citations import finalize_memory_citations


class Memory:
    memory_id = "known-id"
    source_locator = "data/transcripts/source.txt"
    source_ordinal = 7


class CitationTests(unittest.TestCase):
    def test_validates_citations_and_appends_sources(self):
        result = finalize_memory_citations(
            "Supported [memory:known-id], dubious [memory:unknown-id].", [Memory()]
        )
        self.assertIn("[memory:known-id]", result.content)
        self.assertIn("[memory:unverified]", result.content)
        self.assertIn("source.txt#chunk-7", result.content)
        self.assertEqual(result.metadata["valid_model_citations"], ["known-id"])
        self.assertEqual(result.metadata["invalid_model_citations"], ["unknown-id"])


if __name__ == "__main__":
    unittest.main()
