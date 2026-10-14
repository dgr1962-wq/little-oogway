import json
import unittest
from unittest.mock import patch

from oogway_core.embeddings import OllamaEmbeddingModel, vector_literal


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.body).encode()


class EmbeddingTests(unittest.TestCase):
    def test_batch_embedding_validates_dimensions(self):
        model = OllamaEmbeddingModel(dimensions=3)
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"embeddings": [[0.1, 0.2, 0.3]]}),
        ):
            result = model.embed(["search_document: hello"])
        self.assertEqual(result, [[0.1, 0.2, 0.3]])

    def test_rejects_wrong_dimensions(self):
        model = OllamaEmbeddingModel(dimensions=3)
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"embeddings": [[0.1, 0.2]]}),
        ):
            with self.assertRaisesRegex(RuntimeError, "Expected 3"):
                model.embed(["hello"])

    def test_sends_cpu_resource_options(self):
        model = OllamaEmbeddingModel(dimensions=3, num_gpu=0, num_thread=2)
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"embeddings": [[0.1, 0.2, 0.3]]}),
        ) as opened:
            model.embed(["hello"])
        request = opened.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["options"], {"num_gpu": 0, "num_thread": 2})

    def test_vector_literal_rejects_wrong_dimensions(self):
        with self.assertRaisesRegex(ValueError, "Expected 3"):
            vector_literal([0.1], dimensions=3)


if __name__ == "__main__":
    unittest.main()
