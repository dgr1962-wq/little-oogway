import json
import unittest

from oogway_core.archive import AnyKeyArchiveController, canonical_url


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue_ingestion_job(self, **values):
        self.calls.append(values)
        return f"job-{len(self.calls)}", True


class FakeWeb:
    def __init__(self):
        self.responses = {
            "https://anykeycafe.com/wp-json/wp/v2/types": (
                {"page": {"rest_base": "pages", "rest_namespace": "wp/v2"}}, {}
            ),
            "https://anykeycafe.com/wp-json/wp/v2/pages?status=publish&per_page=100&page=1&_fields=id%2Clink%2Cstatus%2Cslug%2Ctype%2Cmodified_gmt": (
                [{"id": 1, "link": "https://anykeycafe.com/about/", "status": "publish"}],
                {"x-wp-totalpages": "1"},
            ),
            "https://anykeycafe.com/wp-sitemap.xml": (
                "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                "<sitemap><loc>https://anykeycafe.com/wp-sitemap-posts-page-1.xml</loc></sitemap>"
                "<sitemap><loc>https://anykeycafe.com/wp-sitemap-taxonomies-category-1.xml</loc></sitemap>"
                "</sitemapindex>", {}
            ),
            "https://anykeycafe.com/wp-sitemap-posts-page-1.xml": (
                "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                "<url><loc>https://anykeycafe.com/about/#top</loc></url>"
                "<url><loc>https://anykeycafe.com/research/</loc></url>"
                "</urlset>", {}
            ),
            "https://anykeycafe.com/ai/sitemap.xml": (
                "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                "<url><loc>https://anykeycafe.com/ai/little-oogway/</loc></url>"
                "</urlset>", {}
            ),
        }

    def __call__(self, url):
        value, headers = self.responses[url]
        raw = json.dumps(value).encode() if not isinstance(value, str) else value.encode()
        return raw, headers


class ArchiveControllerTests(unittest.TestCase):
    def test_canonical_url_removes_fragment_and_normalizes_slash(self):
        self.assertEqual(
            canonical_url("https://www.anykeycafe.com/about#top"),
            "https://www.anykeycafe.com/about/",
        )

    def test_discovers_api_and_content_sitemaps_without_taxonomy_archives(self):
        controller = AnyKeyArchiveController(FakeQueue(), opener=FakeWeb())
        inventory = controller.discover()
        self.assertEqual(
            [item.url for item in inventory],
            [
                "https://anykeycafe.com/about/",
                "https://anykeycafe.com/ai/little-oogway/",
                "https://anykeycafe.com/research/",
            ],
        )
        self.assertEqual(
            inventory[0].discovered_by,
            ("sitemap:wp-sitemap-posts-page-1.xml", "wordpress:page"),
        )

    def test_sample_uses_existing_queue_one_source_at_a_time(self):
        queue = FakeQueue()
        result = AnyKeyArchiveController(queue, opener=FakeWeb()).enqueue(sample=2)
        self.assertEqual(result.discovered, 3)
        self.assertEqual(result.selected, 2)
        self.assertEqual(result.queued, 2)
        self.assertEqual(len(queue.calls), 2)
        self.assertTrue(all(call["source_kind"] == "url" for call in queue.calls))
        self.assertTrue(all(
            call["requested_by"] == "oogway-core-archive-controller"
            for call in queue.calls
        ))


if __name__ == "__main__":
    unittest.main()
