import http.client
import http.cookiejar
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from oogway_core.operator_api import OperatorHandler
from http.server import ThreadingHTTPServer


class EmptyStore:
    def list(self, **_values):
        return []


class FakeRuntime:
    store = EmptyStore()


class FakeResearch:
    pass


class FakeMemory:
    pass


class OperatorApiHttpTests(unittest.TestCase):
    def setUp(self):
        OperatorHandler.runtime = FakeRuntime()
        OperatorHandler.research = FakeResearch()
        OperatorHandler.memory = FakeMemory()
        OperatorHandler.token = "a" * 48
        OperatorHandler.sessions = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), OperatorHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_dashboard_requires_login_and_never_contains_bearer_token(self):
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        unauthenticated = opener.open(self.base + "/").read().decode()
        self.assertIn("Operator sign in", unauthenticated)
        self.assertNotIn(OperatorHandler.token, unauthenticated)

        body = urllib.parse.urlencode({"token": OperatorHandler.token}).encode()
        request = urllib.request.Request(self.base + "/login", data=body, method="POST")
        authenticated = opener.open(request).read().decode()
        self.assertIn("Little Oogway Operator", authenticated)
        self.assertNotIn(OperatorHandler.token, authenticated)

    def test_rejects_rebound_host_header(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=2
        )
        connection.request("GET", "/", headers={"Host": "attacker.example"})
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(response.status, 403)

    def test_rejects_cross_site_origin(self):
        request = urllib.request.Request(
            self.base + "/health", headers={"Origin": "https://attacker.example"}
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
