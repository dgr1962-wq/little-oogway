import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).with_name("little_oogway_worker.py")
spec = importlib.util.spec_from_file_location("little_oogway_worker", path)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WebsiteWorkerContextTests(unittest.TestCase):
    def test_accepts_only_anykeycafe_https_and_bounds_text(self):
        result = worker.bounded_context([
            {"title": "Good", "url": "https://anykeycafe.com/good/", "text": "x" * 2000},
            {"title": "Private", "url": "file:///home/darren/private.txt", "text": "secret"},
            {"title": "Other", "url": "https://example.com/", "text": "outside"},
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["text"]), worker.MAX_CONTEXT_CHARS)

    def test_deduplicates_and_caps_combined_context(self):
        items = [
            {"title": str(index), "url": f"https://anykeycafe.com/{index}/", "text": "same"}
            for index in range(12)
        ]
        items.insert(1, dict(items[0]))
        result = worker.bounded_context(items)
        self.assertEqual(len(result), worker.MAX_CONTEXT_ITEMS)
        self.assertEqual(result[0]["url"], "https://anykeycafe.com/0/")
        self.assertEqual(result[1]["url"], "https://anykeycafe.com/1/")


if __name__ == "__main__":
    unittest.main()
