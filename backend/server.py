import json
import secrets
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
DB_PATH = BASE_DIR.parent / "cityhop.db"
SESSION_HEADER = "X-Session-Token"
SESSIONS = {}


def connect_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scooters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                location TEXT NOT NULL,
                battery INTEGER NOT NULL,
                available INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS prices (
                duration_hours INTEGER PRIMARY KEY,
                price INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                scooter_code TEXT NOT NULL,
                duration_hours INTEGER NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scooter_code TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open'
            );
            """
        )

        issue_columns = [row["name"] for row in conn.execute("PRAGMA table_info(issues)").fetchall()]
        if "status" not in issue_columns:
            conn.execute("ALTER TABLE issues ADD COLUMN status TEXT NOT NULL DEFAULT 'Open'")

        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO users (code, role, name, email, password) VALUES (?, ?, ?, ?, ?)",
                [
                    ("U-001", "customer", "Demo User", "demo@cityhop.app", "demo"),
                    ("M-001", "manager", "Operations Lead", "manager@cityhop.app", "manager"),
                ],
            )

        if conn.execute("SELECT COUNT(*) FROM scooters").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO scooters (code, location, battery, available) VALUES (?, ?, ?, ?)",
                [
                    ("SC-101", "City Square", 88, 1),
                    ("SC-102", "Train Station", 74, 1),
                    ("SC-103", "Riverside", 59, 0),
                    ("SC-104", "University Hub", 93, 1),
                    ("SC-105", "Museum Lane", 67, 1),
                ],
            )

        if conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO prices (duration_hours, price) VALUES (?, ?)",
                [(1, 4), (4, 12), (24, 20), (168, 60)],
            )

        if conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO bookings (customer_name, scooter_code, duration_hours, price, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("Demo User", "SC-103", 4, 12, "Active"),
            )

        if conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO issues (scooter_code, description, priority, status) VALUES (?, ?, ?, ?)",
                ("SC-103", "Front light is flickering during evening use.", "High", "Open"),
            )


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def get_prices(conn):
    rows = conn.execute("SELECT duration_hours, price FROM prices ORDER BY duration_hours").fetchall()
    return {str(row["duration_hours"]): row["price"] for row in rows}


def get_summary(conn):
    available = conn.execute("SELECT COUNT(*) FROM scooters WHERE available = 1").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM scooters").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'Active'").fetchone()[0]
    total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    revenue = conn.execute("SELECT COALESCE(SUM(price), 0) FROM bookings").fetchone()[0]
    issues = conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'Open'").fetchone()[0]
    return {
        "availableScooters": available,
        "activeBookings": active,
        "totalBookings": total_bookings,
        "totalRevenue": revenue,
        "openIssues": issues,
        "fleetAvailability": round((available / total) * 100) if total else 0,
    }


def build_state(conn):
    users = rows_to_dicts(conn.execute("SELECT code, role, name, email FROM users ORDER BY id").fetchall())
    scooters = [
        {
            "id": row["code"],
            "location": row["location"],
            "battery": row["battery"],
            "available": bool(row["available"]),
        }
        for row in conn.execute("SELECT code, location, battery, available FROM scooters ORDER BY id").fetchall()
    ]
    bookings = [
        {
            "id": row["id"],
            "customer": row["customer_name"],
            "scooterId": row["scooter_code"],
            "durationHours": row["duration_hours"],
            "price": row["price"],
            "status": row["status"],
        }
        for row in conn.execute("SELECT * FROM bookings ORDER BY id").fetchall()
    ]
    issues = [
        {
            "id": row["id"],
            "scooterId": row["scooter_code"],
            "description": row["description"],
            "priority": row["priority"],
            "status": row["status"],
        }
        for row in conn.execute("SELECT * FROM issues ORDER BY id DESC").fetchall()
    ]
    return {
        "users": users,
        "scooters": scooters,
        "bookings": bookings,
        "issues": issues,
        "priceMap": get_prices(conn),
        "summary": get_summary(conn),
    }


def sanitize_user(row):
    return {"id": row["code"], "role": row["role"], "name": row["name"], "email": row["email"]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            with connect_db() as conn:
                self.send_json(build_state(conn))
            return
        if parsed.path == "/api/session":
            return self.handle_session()
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/register":
            return self.handle_register()
        if parsed.path == "/api/login":
            return self.handle_login()
        if parsed.path == "/api/logout":
            return self.handle_logout()
        if parsed.path == "/api/bookings":
            return self.handle_create_booking()
        if parsed.path == "/api/bookings/end":
            return self.handle_end_booking()
        if parsed.path == "/api/bookings/cancel":
            return self.handle_cancel_booking()
        if parsed.path == "/api/issues":
            return self.handle_create_issue()
        if parsed.path == "/api/issues/resolve":
            return self.handle_resolve_issue()
        if parsed.path == "/api/prices":
            return self.handle_update_prices()
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def get_session_user(self):
        token = self.headers.get(SESSION_HEADER, "").strip()
        return token, SESSIONS.get(token)

    def require_session(self):
        _, user = self.get_session_user()
        if not user:
            self.send_json({"error": "Please log in to continue."}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def require_manager(self):
        user = self.require_session()
        if not user:
            return None
        if user["role"] != "manager":
            self.send_json({"error": "Manager access is required for this action."}, HTTPStatus.FORBIDDEN)
            return None
        return user

    def handle_session(self):
        _, user = self.get_session_user()
        if not user:
            return self.send_json({"error": "Session not found."}, HTTPStatus.UNAUTHORIZED)
        self.send_json({"user": user})

    def handle_register(self):
        payload = self.read_json()
        role = payload.get("role", "customer").strip()
        name = payload.get("name", "").strip()
        email = payload.get("email", "").strip()
        password = payload.get("password", "").strip()

        if not name or not email or not password:
            return self.send_json({"error": "Name, email, and password are required."}, HTTPStatus.BAD_REQUEST)

        prefix = "M" if role == "manager" else "U"
        with connect_db() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                return self.send_json({"error": "Email already exists."}, HTTPStatus.BAD_REQUEST)

            count = conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", (role,)).fetchone()[0] + 1
            code = f"{prefix}-{count:03d}"
            conn.execute(
                "INSERT INTO users (code, role, name, email, password) VALUES (?, ?, ?, ?, ?)",
                (code, role, name, email, password),
            )
            user = {"id": code, "role": role, "name": name, "email": email}
            self.send_json({"user": user})

    def handle_login(self):
        payload = self.read_json()
        role = payload.get("role", "customer").strip()
        email = payload.get("email", "").strip()
        password = payload.get("password", "").strip()

        if not email or not password:
            return self.send_json({"error": "Email and password are required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            row = conn.execute(
                "SELECT code, role, name, email, password FROM users WHERE email = ? AND role = ?",
                (email, role),
            ).fetchone()

        if not row or row["password"] != password:
            return self.send_json({"error": "Invalid email, password, or role."}, HTTPStatus.UNAUTHORIZED)

        user = sanitize_user(row)
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = user
        self.send_json({"user": user, "sessionToken": token})

    def handle_logout(self):
        token, _ = self.get_session_user()
        if token:
            SESSIONS.pop(token, None)
        self.send_json({"message": "Logged out."})

    def handle_create_booking(self):
        user = self.require_session()
        if not user:
            return

        payload = self.read_json()
        scooter_id = payload.get("scooterId", "").strip()
        duration_hours = int(payload.get("durationHours", 0))
        customer = user["name"]

        with connect_db() as conn:
            scooter = conn.execute("SELECT code, available FROM scooters WHERE code = ?", (scooter_id,)).fetchone()
            if not scooter or not scooter["available"]:
                return self.send_json({"error": "Please choose an available scooter."}, HTTPStatus.BAD_REQUEST)

            price_row = conn.execute("SELECT price FROM prices WHERE duration_hours = ?", (duration_hours,)).fetchone()
            if not price_row:
                return self.send_json({"error": "Invalid booking duration."}, HTTPStatus.BAD_REQUEST)

            conn.execute("UPDATE scooters SET available = 0 WHERE code = ?", (scooter_id,))
            conn.execute(
                """
                INSERT INTO bookings (customer_name, scooter_code, duration_hours, price, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer, scooter_id, duration_hours, price_row["price"], "Active"),
            )
            self.send_json({"message": f"Booking created for {customer}.", "state": build_state(conn)})

    def handle_end_booking(self):
        user = self.require_session()
        if not user:
            return

        payload = self.read_json()
        booking_id = int(payload.get("bookingId", -1))

        with connect_db() as conn:
            booking = conn.execute(
                "SELECT id, scooter_code, status, customer_name FROM bookings WHERE id = ?",
                (booking_id,),
            ).fetchone()
            if not booking or booking["status"] != "Active":
                return self.send_json({"error": "No active booking is available."}, HTTPStatus.BAD_REQUEST)
            if user["role"] != "manager" and booking["customer_name"] != user["name"]:
                return self.send_json({"error": "You can only end your own booking."}, HTTPStatus.FORBIDDEN)

            conn.execute("UPDATE bookings SET status = 'Completed' WHERE id = ?", (booking["id"],))
            conn.execute("UPDATE scooters SET available = 1 WHERE code = ?", (booking["scooter_code"],))
            self.send_json({"message": f"Booking for {booking['customer_name']} has been ended.", "state": build_state(conn)})

    def handle_cancel_booking(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        booking_id = int(payload.get("bookingId", -1))

        with connect_db() as conn:
            booking = conn.execute(
                "SELECT id, scooter_code, status, customer_name FROM bookings WHERE id = ?",
                (booking_id,),
            ).fetchone()
            if not booking:
                return self.send_json({"error": "Booking not found."}, HTTPStatus.BAD_REQUEST)
            if booking["status"] != "Active":
                return self.send_json({"error": "Only active bookings can be cancelled."}, HTTPStatus.BAD_REQUEST)

            conn.execute("UPDATE bookings SET status = 'Cancelled' WHERE id = ?", (booking["id"],))
            conn.execute("UPDATE scooters SET available = 1 WHERE code = ?", (booking["scooter_code"],))
            self.send_json({"message": f"Booking for {booking['customer_name']} has been cancelled.", "state": build_state(conn)})

    def handle_create_issue(self):
        user = self.require_session()
        if not user:
            return

        payload = self.read_json()
        scooter_id = payload.get("scooterId", "").strip()
        description = payload.get("description", "").strip()
        if not scooter_id or not description:
            return self.send_json({"error": "Issue description is required."}, HTTPStatus.BAD_REQUEST)

        priority = "High" if "brake" in description.lower() else "Medium"
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO issues (scooter_code, description, priority, status) VALUES (?, ?, ?, ?)",
                (scooter_id, description, priority, "Open"),
            )
            self.send_json({"message": "Issue submitted.", "state": build_state(conn)})

    def handle_resolve_issue(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        issue_id = int(payload.get("issueId", -1))

        with connect_db() as conn:
            issue = conn.execute("SELECT id, status FROM issues WHERE id = ?", (issue_id,)).fetchone()
            if not issue:
                return self.send_json({"error": "Issue not found."}, HTTPStatus.BAD_REQUEST)
            if issue["status"] == "Resolved":
                return self.send_json({"error": "Issue is already resolved."}, HTTPStatus.BAD_REQUEST)

            conn.execute("UPDATE issues SET status = 'Resolved' WHERE id = ?", (issue_id,))
            self.send_json({"message": "Issue resolved.", "state": build_state(conn)})

    def handle_update_prices(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        prices = payload.get("prices", {})
        expected_durations = [1, 4, 24, 168]

        try:
            normalized = [(duration, int(prices[str(duration)])) for duration in expected_durations]
        except (KeyError, TypeError, ValueError):
            return self.send_json({"error": "Please provide valid prices for all durations."}, HTTPStatus.BAD_REQUEST)

        if any(price <= 0 for _, price in normalized):
            return self.send_json({"error": "Prices must be positive numbers."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            conn.executemany(
                "UPDATE prices SET price = ? WHERE duration_hours = ?",
                [(price, duration) for duration, price in normalized],
            )
            self.send_json({"message": "Price configuration updated.", "state": build_state(conn)})

    def serve_static(self, request_path):
        path = "/index.html" if request_path in {"/", ""} else request_path
        target = (FRONTEND_DIR / path.lstrip("/")).resolve()
        if target != FRONTEND_DIR and FRONTEND_DIR not in target.parents:
            return self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
        if not target.exists() or target.is_dir():
            return self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("CityHop backend running at http://127.0.0.1:8000")
    server.serve_forever()
