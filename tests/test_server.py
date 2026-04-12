import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import server


class CityHopServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = server.DB_PATH
        cls.original_src_dir = server.SRC_DIR

        server.DB_PATH = Path(cls.temp_dir.name) / "test_cityhop.db"
        server.SRC_DIR = cls.original_src_dir
        server.SESSIONS.clear()
        server.init_db()

        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        server.SESSIONS.clear()
        server.DB_PATH = cls.original_db_path
        server.SRC_DIR = cls.original_src_dir
        time.sleep(0.1)
        try:
            cls.temp_dir.cleanup()
        except PermissionError:
            pass

    def setUp(self):
        server.SESSIONS.clear()
        server.DB_PATH = Path(self.temp_dir.name) / f"{self._testMethodName}.db"
        if server.DB_PATH.exists():
            server.DB_PATH.unlink()
        server.init_db()

    def request(self, path, method="GET", body=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}

        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"
        else:
            data = None

        if token:
            headers[server.SESSION_HEADER] = token

        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return response.status, payload
        finally:
            connection.close()

    def login_demo_customer(self):
        status, payload = self.request(
            "/api/login",
            method="POST",
            body={"role": "customer", "email": "demo@cityhop.app", "password": "demo"},
        )
        self.assertEqual(status, 200)
        self.assertIn("sessionToken", payload)
        return payload["sessionToken"]

    def login_demo_manager(self):
        status, payload = self.request(
            "/api/login",
            method="POST",
            body={"role": "manager", "email": "manager@cityhop.app", "password": "manager"},
        )
        self.assertEqual(status, 200)
        self.assertIn("sessionToken", payload)
        return payload["sessionToken"]

    def test_register_customer_account(self):
        status, payload = self.request(
            "/api/register",
            method="POST",
            body={
                "role": "customer",
                "name": "Sprint Tester",
                "email": "tester@example.com",
                "password": "secret123",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["name"], "Sprint Tester")
        self.assertEqual(payload["user"]["role"], "customer")

    def test_login_requires_correct_password(self):
        status, payload = self.request(
            "/api/login",
            method="POST",
            body={"role": "customer", "email": "demo@cityhop.app", "password": "wrong-password"},
        )

        self.assertEqual(status, 401)
        self.assertIn("Invalid email, password, or role.", payload["error"])

    def test_session_endpoint_restores_logged_in_customer(self):
        token = self.login_demo_customer()
        status, payload = self.request("/api/session", token=token)

        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["email"], "demo@cityhop.app")
        self.assertEqual(payload["user"]["role"], "customer")

    def test_logout_invalidates_session(self):
        token = self.login_demo_customer()
        logout_status, _ = self.request("/api/logout", method="POST", token=token, body={})
        session_status, session_payload = self.request("/api/session", token=token)

        self.assertEqual(logout_status, 200)
        self.assertEqual(session_status, 401)
        self.assertIn("Session not found.", session_payload["error"])

    def test_booking_requires_authenticated_session(self):
        status, payload = self.request(
            "/api/bookings",
            method="POST",
            body={"scooterId": "SC-101", "durationHours": 1},
        )

        self.assertEqual(status, 401)
        self.assertIn("Please log in to continue.", payload["error"])

    def test_customer_can_create_booking(self):
        token = self.login_demo_customer()
        status, payload = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "durationHours": 1},
        )

        self.assertEqual(status, 200)
        self.assertIn("Booking created for Demo User.", payload["message"])
        created = next((booking for booking in payload["state"]["bookings"] if booking["scooterId"] == "SC-101"), None)
        self.assertIsNotNone(created)
        self.assertEqual(created["status"], "Active")

    def test_customer_can_end_own_booking(self):
        token = self.login_demo_customer()
        create_status, create_payload = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "durationHours": 1},
        )
        self.assertEqual(create_status, 200)
        active = next(
            booking
            for booking in reversed(create_payload["state"]["bookings"])
            if booking["customer"] == "Demo User" and booking["scooterId"] == "SC-101" and booking["status"] == "Active"
        )

        end_status, end_payload = self.request(
            "/api/bookings/end",
            method="POST",
            token=token,
            body={"bookingId": active["id"]},
        )

        self.assertEqual(end_status, 200)
        self.assertIn("has been ended", end_payload["message"])

    def test_customer_cannot_end_someone_elses_booking(self):
        manager_token = self.login_demo_manager()
        create_status, create_payload = self.request(
            "/api/bookings",
            method="POST",
            token=manager_token,
            body={"scooterId": "SC-101", "durationHours": 1},
        )
        self.assertEqual(create_status, 200)
        active = next(
            booking
            for booking in reversed(create_payload["state"]["bookings"])
            if booking["customer"] == "Operations Lead" and booking["status"] == "Active"
        )

        customer_token = self.login_demo_customer()
        end_status, end_payload = self.request(
            "/api/bookings/end",
            method="POST",
            token=customer_token,
            body={"bookingId": active["id"]},
        )

        self.assertEqual(end_status, 403)
        self.assertIn("You can only end your own booking.", end_payload["error"])

    def test_manager_can_update_prices(self):
        token = self.login_demo_manager()
        status, payload = self.request(
            "/api/prices",
            method="POST",
            token=token,
            body={"prices": {"1": 6, "4": 14, "24": 24, "168": 70}},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["state"]["priceMap"]["1"], 6)
        self.assertEqual(payload["state"]["priceMap"]["168"], 70)

    def test_customer_cannot_update_prices(self):
        token = self.login_demo_customer()
        status, payload = self.request(
            "/api/prices",
            method="POST",
            token=token,
            body={"prices": {"1": 6, "4": 14, "24": 24, "168": 70}},
        )

        self.assertEqual(status, 403)
        self.assertIn("Manager access is required", payload["error"])

    def test_price_update_requires_all_durations(self):
        token = self.login_demo_manager()
        status, payload = self.request(
            "/api/prices",
            method="POST",
            token=token,
            body={"prices": {"1": 6, "4": 14}},
        )

        self.assertEqual(status, 400)
        self.assertIn("Please provide valid prices for all durations.", payload["error"])

    def test_manager_can_cancel_active_booking(self):
        token = self.login_demo_manager()
        status, payload = self.request(
            "/api/bookings/cancel",
            method="POST",
            token=token,
            body={"bookingId": 1},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["state"]["bookings"][0]["status"], "Cancelled")

    def test_customer_cannot_cancel_booking(self):
        token = self.login_demo_customer()
        status, payload = self.request(
            "/api/bookings/cancel",
            method="POST",
            token=token,
            body={"bookingId": 1},
        )

        self.assertEqual(status, 403)
        self.assertIn("Manager access is required", payload["error"])

    def test_manager_can_resolve_issue(self):
        token = self.login_demo_manager()
        status, payload = self.request(
            "/api/issues/resolve",
            method="POST",
            token=token,
            body={"issueId": 1},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["state"]["issues"][0]["status"], "Resolved")

    def test_customer_can_submit_issue(self):
        token = self.login_demo_customer()
        status, payload = self.request(
            "/api/issues",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "description": "Brake feels loose during ride."},
        )

        self.assertEqual(status, 200)
        newest_issue = payload["state"]["issues"][0]
        self.assertEqual(newest_issue["scooterId"], "SC-101")
        self.assertEqual(newest_issue["priority"], "High")

    def test_static_index_page_is_served(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type", "")
        connection.close()

        self.assertEqual(response.status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("<title>CityHop E-Scooter</title>", raw)


if __name__ == "__main__":
    unittest.main()
