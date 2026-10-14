import tempfile
import unittest
from pathlib import Path

from oogway_core.tools import AbsorbSourceTool


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue_ingestion_job(self, **values):
        self.calls.append(values)
        return "job-123", True


class AbsorbSourceToolTests(unittest.TestCase):
    def test_queues_explicit_approved_url(self):
        queue = FakeQueue()
        result = AbsorbSourceTool(queue, autostart=False).try_execute(
            "Hey Little Oogway, please absorb https://anykeycafe.com/little-o/."
        )
        self.assertEqual(result.metadata["job_id"], "job-123")
        self.assertEqual(queue.calls[0]["source_kind"], "url")
        self.assertEqual(queue.calls[0]["requested_by"], "oogway-conversation-tool")

    def test_queues_quoted_local_path(self):
        queue = FakeQueue()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "notes with spaces.txt")
            path.write_text("memory", encoding="utf-8")
            result = AbsorbSourceTool(queue, autostart=False).try_execute(
                f'Absorb "{path}"'
            )
        self.assertEqual(result.metadata["status"], "queued")
        self.assertEqual(queue.calls[0]["source_locator"], str(path.resolve()))

    def test_rejects_unapproved_remote_host_without_queueing(self):
        queue = FakeQueue()
        result = AbsorbSourceTool(queue, autostart=False).try_execute(
            "Absorb https://example.com/private"
        )
        self.assertEqual(result.metadata["status"], "rejected")
        self.assertEqual(queue.calls, [])

    def test_requests_source_for_explicit_absorb_this(self):
        result = AbsorbSourceTool(FakeQueue(), autostart=False).try_execute(
            "Could you absorb this?"
        )
        self.assertEqual(result.metadata["status"], "needs_source")

    def test_ignores_discussion_without_a_source(self):
        result = AbsorbSourceTool(FakeQueue(), autostart=False).try_execute(
            "Should an AI absorb knowledge gradually?"
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
