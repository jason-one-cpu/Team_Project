import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import server


class CityHopServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = server.DB_PATH
        cls.original_frontend_dir = server.FRONTEND_DIR

        server.DB_PATH = Path(cls.temp_dir.name) / "test_cityhop.db"
        server.FRONTEND_DIR = cls.original_frontend_dir
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
        server.FRONTEND_DIR = cls.original_frontend_dir
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
            body={"role": "manager", "email": "admin", "password": "admin"},
        )
        self.assertEqual(status, 200)
        self.assertIn("sessionToken", payload)
        return payload["sessionToken"]

    def sample_payment(self, save_card=False):
        return {
            "useSavedCard": False,
            "cardholderName": "Test User",
            "cardNumber": "4111111111111111",
            "expiry": "12/29",
            "cvv": "123",
            "saveCard": save_card,
        }

    def test_register_customer_account(self):
        status, payload = self.request(
            "/api/register",
            method="POST",
            body={
                "role": "customer",
                "name": "Sprint Tester",
                "accountType": "student",
                "email": "tester@example.com",
                "password": "secret123",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["name"], "Sprint Tester")
        self.assertEqual(payload["user"]["role"], "customer")
        self.assertEqual(payload["user"]["accountType"], "student")

    def test_manager_registration_is_forbidden(self):
        status, payload = self.request(
            "/api/register",
            method="POST",
            body={
                "role": "manager",
                "name": "Not Allowed",
                "email": "manager@example.com",
                "password": "secret123",
            },
        )

        self.assertEqual(status, 403)
        self.assertIn("cannot be registered", payload["error"])

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
            body={"scooterId": "SC-101", "durationHours": 1, "payment": self.sample_payment(save_card=True)},
        )

        self.assertEqual(status, 200)
        self.assertIn("Booking created for Demo User.", payload["message"])
        created = next((booking for booking in payload["state"]["bookings"] if booking["scooterId"] == "SC-101"), None)
        self.assertIsNotNone(created)
        self.assertEqual(created["status"], "Active")
        self.assertEqual(created["price"], 4)
        self.assertEqual(created["paymentStatus"], "Paid")
        self.assertEqual(created["confirmationEmailStatus"], "Sent")
        self.assertEqual(created["discountType"], "None")

    def test_customer_can_end_own_booking(self):
        token = self.login_demo_customer()
        create_status, create_payload = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "durationHours": 1, "payment": self.sample_payment()},
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
            body={"scooterId": "SC-101", "durationHours": 1, "payment": self.sample_payment()},
        )
        self.assertEqual(create_status, 200)
        active = next(
            booking
            for booking in reversed(create_payload["state"]["bookings"])
            if booking["customer"] == "Admin" and booking["status"] == "Active"
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

    def test_manager_can_escalate_issue_to_high_priority(self):
        customer_token = self.login_demo_customer()
        create_status, create_payload = self.request(
            "/api/issues",
            method="POST",
            token=customer_token,
            body={"scooterId": "SC-101", "description": "Handlebar feels loose."},
        )
        self.assertEqual(create_status, 200)
        issue_id = create_payload["state"]["issues"][0]["id"]

        manager_token = self.login_demo_manager()
        status, payload = self.request(
            "/api/issues/escalate",
            method="POST",
            token=manager_token,
            body={"issueId": issue_id},
        )

        self.assertEqual(status, 200)
        escalated_issue = next(issue for issue in payload["state"]["issues"] if issue["id"] == issue_id)
        self.assertEqual(escalated_issue["priority"], "High")

    def test_customer_can_extend_own_booking(self):
        token = self.login_demo_customer()
        create_status, create_payload = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "durationHours": 1, "payment": self.sample_payment()},
        )
        self.assertEqual(create_status, 200)
        active = next(
            booking
            for booking in reversed(create_payload["state"]["bookings"])
            if booking["customer"] == "Demo User" and booking["scooterId"] == "SC-101" and booking["status"] == "Active"
        )

        status, payload = self.request(
            "/api/bookings/extend",
            method="POST",
            token=token,
            body={"bookingId": active["id"], "additionalHours": 4},
        )

        self.assertEqual(status, 200)
        updated_booking = next(booking for booking in payload["state"]["bookings"] if booking["id"] == active["id"])
        self.assertEqual(updated_booking["durationHours"], 5)

    def test_saved_card_can_be_reused_for_booking(self):
        token = self.login_demo_customer()
        first_status, first_payload = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "durationHours": 1, "payment": self.sample_payment(save_card=True)},
        )
        self.assertEqual(first_status, 200)
        active_booking = next(
            booking
            for booking in reversed(first_payload["state"]["bookings"])
            if booking["customer"] == "Demo User" and booking["scooterId"] == "SC-101" and booking["status"] == "Active"
        )
        end_status, _ = self.request(
            "/api/bookings/end",
            method="POST",
            token=token,
            body={"bookingId": active_booking["id"]},
        )
        self.assertEqual(end_status, 200)

        second_status, second_payload = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={"scooterId": "SC-101", "durationHours": 1, "payment": {"useSavedCard": True}},
        )
        self.assertEqual(second_status, 200)
        latest_booking = next(
            booking
            for booking in reversed(second_payload["state"]["bookings"])
            if booking["customer"] == "Demo User" and booking["scooterId"] == "SC-101"
        )
        self.assertIn("ending 1111", latest_booking["paymentMethod"])

    def test_manager_can_create_walk_in_booking(self):
        token = self.login_demo_manager()
        status, payload = self.request(
            "/api/staff/bookings",
            method="POST",
            token=token,
            body={
                "guestName": "Walk In Guest",
                "guestEmail": "walkin@example.com",
                "scooterId": "SC-101",
                "startTime": "2026-04-28T10:00",
                "endTime": "2026-04-28T14:00",
                "payment": self.sample_payment(),
            },
        )

        self.assertEqual(status, 200)
        guest_booking = next(booking for booking in payload["state"]["bookings"] if booking["customer"] == "Walk In Guest")
        self.assertTrue(guest_booking["isGuest"])
        self.assertEqual(guest_booking["customerEmail"], "walkin@example.com")

    def test_nearby_store_generation_creates_new_stores_when_area_is_empty(self):
        token = self.login_demo_customer()
        status, payload = self.request(
            "/api/stores/ensure-nearby",
            method="POST",
            token=token,
            body={"latitude": 53.0200, "longitude": -1.0800},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["created"])
        generated = [scooter for scooter in payload["state"]["scooters"] if scooter["location"].startswith("Auto Store")]
        generated_store_names = {scooter["location"] for scooter in generated}
        self.assertEqual(len(generated_store_names), 3)
        self.assertTrue(all(3 <= scooter["hourlyPrice"] <= 8 for scooter in generated))

    def test_manager_can_update_individual_scooter_hourly_prices(self):
        token = self.login_demo_manager()
        status, payload = self.request(
            "/api/scooters/hourly-prices",
            method="POST",
            token=token,
            body={"scooterPrices": {"SC-101": 7, "SC-102": 9}},
        )

        self.assertEqual(status, 200)
        scooters = {scooter["id"]: scooter for scooter in payload["state"]["scooters"]}
        self.assertEqual(scooters["SC-101"]["hourlyPrice"], 7)
        self.assertEqual(scooters["SC-102"]["hourlyPrice"], 9)

    def test_manager_can_create_store_and_add_scooter(self):
        token = self.login_demo_manager()
        create_status, create_payload = self.request(
            "/api/stores",
            method="POST",
            token=token,
            body={"name": "North Hub", "latitude": 52.9701, "longitude": -1.1402},
        )

        self.assertEqual(create_status, 200)
        created_store = next(store for store in create_payload["state"]["stores"] if store["name"] == "North Hub")

        scooter_status, scooter_payload = self.request(
            "/api/stores/scooters",
            method="POST",
            token=token,
            body={"storeId": created_store["id"], "hourlyPrice": 8, "battery": 84},
        )

        self.assertEqual(scooter_status, 200)
        scooter = next(
            scooter
            for scooter in scooter_payload["state"]["scooters"]
            if scooter["storeId"] == created_store["id"]
        )
        self.assertEqual(scooter["location"], "North Hub")
        self.assertEqual(scooter["hourlyPrice"], 8)

    def test_manager_can_update_existing_store(self):
        token = self.login_demo_manager()
        create_status, create_payload = self.request(
            "/api/stores",
            method="POST",
            token=token,
            body={"name": "South Hub", "latitude": 52.9401, "longitude": -1.1602},
        )

        self.assertEqual(create_status, 200)
        created_store = next(store for store in create_payload["state"]["stores"] if store["name"] == "South Hub")

        update_status, update_payload = self.request(
            "/api/stores/update",
            method="POST",
            token=token,
            body={
                "storeId": created_store["id"],
                "name": "South Hub Updated",
                "latitude": 52.9412,
                "longitude": -1.1613,
            },
        )

        self.assertEqual(update_status, 200)
        updated_store = next(store for store in update_payload["state"]["stores"] if store["id"] == created_store["id"])
        self.assertEqual(updated_store["name"], "South Hub Updated")
        self.assertAlmostEqual(updated_store["latitude"], 52.9412)
        self.assertAlmostEqual(updated_store["longitude"], -1.1613)

    def test_manager_can_delete_scooter(self):
        token = self.login_demo_manager()
        create_status, create_payload = self.request(
            "/api/stores",
            method="POST",
            token=token,
            body={"name": "Delete Scooter Hub", "latitude": 52.9601, "longitude": -1.1302},
        )
        self.assertEqual(create_status, 200)
        created_store = next(store for store in create_payload["state"]["stores"] if store["name"] == "Delete Scooter Hub")

        scooter_status, scooter_payload = self.request(
            "/api/stores/scooters",
            method="POST",
            token=token,
            body={"storeId": created_store["id"], "hourlyPrice": 6, "battery": 78},
        )
        self.assertEqual(scooter_status, 200)
        created_scooter = next(
            scooter
            for scooter in scooter_payload["state"]["scooters"]
            if scooter["storeId"] == created_store["id"]
        )

        delete_status, delete_payload = self.request(
            "/api/scooters/delete",
            method="POST",
            token=token,
            body={"scooterId": created_scooter["id"]},
        )
        self.assertEqual(delete_status, 200)
        remaining_ids = {scooter["id"] for scooter in delete_payload["state"]["scooters"]}
        self.assertNotIn(created_scooter["id"], remaining_ids)

    def test_manager_can_delete_store(self):
        token = self.login_demo_manager()
        create_status, create_payload = self.request(
            "/api/stores",
            method="POST",
            token=token,
            body={"name": "Delete Store Hub", "latitude": 52.9671, "longitude": -1.1322},
        )
        self.assertEqual(create_status, 200)
        created_store = next(store for store in create_payload["state"]["stores"] if store["name"] == "Delete Store Hub")

        scooter_status, scooter_payload = self.request(
            "/api/stores/scooters",
            method="POST",
            token=token,
            body={"storeId": created_store["id"], "hourlyPrice": 7, "battery": 82},
        )
        self.assertEqual(scooter_status, 200)
        created_scooter = next(
            scooter
            for scooter in scooter_payload["state"]["scooters"]
            if scooter["storeId"] == created_store["id"]
        )

        delete_status, delete_payload = self.request(
            "/api/stores/delete",
            method="POST",
            token=token,
            body={"storeId": created_store["id"]},
        )
        self.assertEqual(delete_status, 200)
        remaining_store_ids = {store["id"] for store in delete_payload["state"]["stores"]}
        remaining_scooter_ids = {scooter["id"] for scooter in delete_payload["state"]["scooters"]}
        self.assertNotIn(created_store["id"], remaining_store_ids)
        self.assertNotIn(created_scooter["id"], remaining_scooter_ids)

    def test_customer_can_view_generated_booking_route(self):
        token = self.login_demo_customer()
        status, payload = self.request("/api/bookings/route?bookingId=1", token=token)

        self.assertEqual(status, 200)
        self.assertEqual(payload["booking"]["scooterId"], "SC-103")
        self.assertGreaterEqual(len(payload["route"]), 1)
        self.assertIn("latitude", payload["route"][0])
        self.assertIn("battery", payload["route"][0])

    def test_statistics_include_weekly_option_and_daily_income(self):
        token = self.login_demo_customer()
        create_status, _ = self.request(
            "/api/bookings",
            method="POST",
            token=token,
            body={
                "scooterId": "SC-101",
                "startTime": "2026-04-28T09:00",
                "endTime": "2026-04-28T13:00",
                "payment": self.sample_payment(),
            },
        )
        self.assertEqual(create_status, 200)

        state_status, state_payload = self.request("/api/state")
        self.assertEqual(state_status, 200)
        self.assertEqual(len(state_payload["statistics"]["weeklyIncomeByOption"]), 4)
        self.assertEqual(len(state_payload["statistics"]["dailyIncome"]), 7)
        self.assertIn("highPriorityIssues", state_payload["summary"])

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
