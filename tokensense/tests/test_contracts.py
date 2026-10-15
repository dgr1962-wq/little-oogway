from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tokensense_infra import ContractKind, RegistryStore


class RegistryTests(unittest.TestCase):
    def test_relationship_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RegistryStore(Path(directory))
            store.append(ContractKind.MEMORY_RELATIONSHIP, {
                "relationship_id": "rel-1",
                "subject_memory_id": "memory-a",
                "object_memory_id": "memory-b",
                "relationship_type": "supports",
                "provenance": [{"source": "synthetic"}],
                "evidence": [{"id": "evidence-1"}],
                "confidence": 0.5,
                "review_status": "proposed",
            })
            self.assertEqual(len(store.records(ContractKind.MEMORY_RELATIONSHIP)), 1)

    def test_contradiction_cannot_auto_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RegistryStore(Path(directory))
            with self.assertRaises(ValueError):
                store.append(ContractKind.CONTRADICTION, {
                    "contradiction_id": "conflict-1",
                    "statement_ids": ["a", "b"],
                    "evidence": [],
                    "review_status": "open",
                    "resolution": "a wins",
                })

    def test_training_candidate_needs_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RegistryStore(Path(directory))
            with self.assertRaises(ValueError):
                store.append(ContractKind.TRAINING_CANDIDATE, {
                    "candidate_id": "candidate-1",
                    "source_references": [],
                    "validation_status": "approved",
                    "dataset_version": "synthetic-v1",
                    "permission_to_use": False,
                })

    def test_all_six_contract_kinds_have_testable_minimums(self) -> None:
        examples = {
            ContractKind.MEMORY_RELATIONSHIP: {
                "relationship_id": "r", "subject_memory_id": "a", "object_memory_id": "b",
                "relationship_type": "related", "provenance": [], "evidence": [],
                "confidence": 0.2, "review_status": "proposed",
            },
            ContractKind.HYPOTHESIS: {
                "hypothesis_id": "h", "statement": "synthetic hypothesis",
                "supporting_evidence": [], "conflicting_evidence": [], "predictions": [],
                "unresolved_questions": [], "review_status": "candidate",
            },
            ContractKind.CONTRADICTION: {
                "contradiction_id": "c", "statement_ids": ["a", "b"], "evidence": [],
                "review_status": "open",
            },
            ContractKind.TRAINING_CANDIDATE: {
                "candidate_id": "t", "source_references": [], "validation_status": "proposed",
                "dataset_version": "synthetic", "permission_to_use": False,
            },
            ContractKind.ADAPTER: {
                "adapter_id": "a", "base_model": {}, "training_configuration": {},
                "dataset_manifest": {}, "checkpoints": [], "evaluation_results": [],
                "status": "experimental",
            },
            ContractKind.EXPERIMENT: {
                "experiment_id": "e", "baseline": {}, "candidate": {},
                "resource_measurements": {}, "failures": [], "reproducibility": {},
                "status": "planned",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            store = RegistryStore(Path(directory))
            for kind, record in examples.items():
                store.append(kind, record)
                self.assertEqual(len(store.records(kind)), 1)


if __name__ == "__main__":
    unittest.main()
