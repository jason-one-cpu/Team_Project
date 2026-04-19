import json
import math
import random
import secrets
import sqlite3
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
DB_PATH = BASE_DIR.parent / "cityhop.db"
SESSION_HEADER = "X-Session-Token"
SESSIONS = {}
DEFAULT_STORE_COORDINATES = {
    "City Square": (52.9548, -1.1581),
    "Train Station": (52.9479, -1.1460),
    "Riverside": (52.9499, -1.1557),
    "University Hub": (52.9386, -1.1966),
    "Museum Lane": (52.9536, -1.1495),
}


def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        DB_PATH.touch()
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
                store_id INTEGER,
                location TEXT NOT NULL,
                latitude REAL NOT NULL DEFAULT 52.9530,
                longitude REAL NOT NULL DEFAULT -1.1500,
                battery INTEGER NOT NULL,
                hourly_price INTEGER NOT NULL DEFAULT 4,
                available INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prices (
                duration_hours INTEGER PRIMARY KEY,
                price INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                scooter_code TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                start_latitude REAL,
                start_longitude REAL,
                start_battery INTEGER,
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

            CREATE TABLE IF NOT EXISTS gps_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                logged_at TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                battery INTEGER NOT NULL
            );
            """
        )

        issue_columns = [row["name"] for row in conn.execute("PRAGMA table_info(issues)").fetchall()]
        if "status" not in issue_columns:
            conn.execute("ALTER TABLE issues ADD COLUMN status TEXT NOT NULL DEFAULT 'Open'")

        scooter_columns = [row["name"] for row in conn.execute("PRAGMA table_info(scooters)").fetchall()]
        if "store_id" not in scooter_columns:
            conn.execute("ALTER TABLE scooters ADD COLUMN store_id INTEGER")
        if "latitude" not in scooter_columns:
            conn.execute("ALTER TABLE scooters ADD COLUMN latitude REAL NOT NULL DEFAULT 52.9530")
        if "longitude" not in scooter_columns:
            conn.execute("ALTER TABLE scooters ADD COLUMN longitude REAL NOT NULL DEFAULT -1.1500")
        if "hourly_price" not in scooter_columns:
            conn.execute("ALTER TABLE scooters ADD COLUMN hourly_price INTEGER NOT NULL DEFAULT 4")

        booking_columns = [row["name"] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "start_time" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN start_time TEXT")
        if "end_time" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN end_time TEXT")
        if "start_latitude" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN start_latitude REAL")
        if "start_longitude" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN start_longitude REAL")
        if "start_battery" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN start_battery INTEGER")

        existing_users = {
            row["email"]: row
            for row in conn.execute("SELECT code, role, name, email, password FROM users").fetchall()
        }
        bootstrap_users = []
        if "demo@cityhop.app" not in existing_users:
            bootstrap_users.append(("U-001", "customer", "Demo User", "demo@cityhop.app", "demo"))
        if bootstrap_users:
            conn.executemany(
                "INSERT INTO users (code, role, name, email, password) VALUES (?, ?, ?, ?, ?)",
                bootstrap_users,
            )

        admin_row = existing_users.get("admin")
        if admin_row is None:
            existing_codes = {
                row["code"] for row in conn.execute("SELECT code FROM users").fetchall()
            }
            manager_code_number = 1
            admin_code = f"M-{manager_code_number:03d}"
            while admin_code in existing_codes:
                manager_code_number += 1
                admin_code = f"M-{manager_code_number:03d}"
            conn.execute(
                "INSERT INTO users (code, role, name, email, password) VALUES (?, ?, ?, ?, ?)",
                (admin_code, "manager", "Admin", "admin", "admin"),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET role = 'manager',
                    name = 'Admin',
                    password = 'admin'
                WHERE email = 'admin'
                """
            )

        if conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO stores (name, latitude, longitude) VALUES (?, ?, ?)",
                [(name, latitude, longitude) for name, (latitude, longitude) in DEFAULT_STORE_COORDINATES.items()],
            )

        if conn.execute("SELECT COUNT(*) FROM scooters").fetchone()[0] == 0:
            store_ids = {
                row["name"]: row["id"]
                for row in conn.execute("SELECT id, name FROM stores").fetchall()
            }
            conn.executemany(
                "INSERT INTO scooters (code, store_id, location, latitude, longitude, battery, hourly_price, available) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("SC-101", store_ids["City Square"], "City Square", 52.9548, -1.1581, 88, 4, 1),
                    ("SC-102", store_ids["Train Station"], "Train Station", 52.9479, -1.1460, 74, 5, 1),
                    ("SC-103", store_ids["Riverside"], "Riverside", 52.9499, -1.1557, 59, 4, 0),
                    ("SC-104", store_ids["University Hub"], "University Hub", 52.9386, -1.1966, 93, 3, 1),
                    ("SC-105", store_ids["Museum Lane"], "Museum Lane", 52.9536, -1.1495, 67, 5, 1),
                ],
            )

        for location, (latitude, longitude) in DEFAULT_STORE_COORDINATES.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO stores (name, latitude, longitude)
                VALUES (?, ?, ?)
                """,
                (location, latitude, longitude),
            )
            conn.execute(
                """
                UPDATE scooters
                SET latitude = ?, longitude = ?
                WHERE location = ? AND (latitude = 52.9530 OR longitude = -1.1500)
                """,
                (latitude, longitude, location),
            )
            conn.execute(
                """
                UPDATE scooters
                SET store_id = (
                    SELECT id FROM stores WHERE stores.name = scooters.location
                )
                WHERE location = ? AND (store_id IS NULL OR store_id = 0)
                """,
                (location,),
            )

        if conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO prices (duration_hours, price) VALUES (?, ?)",
                [(1, 4), (4, 12), (24, 20), (168, 60)],
            )

        if conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0:
            demo_start = (datetime.now() - timedelta(hours=4)).replace(second=0, microsecond=0).isoformat(timespec="minutes")
            demo_end = (datetime.now() + timedelta(hours=1)).replace(second=0, microsecond=0).isoformat(timespec="minutes")
            conn.execute(
                """
                INSERT INTO bookings (customer_name, scooter_code, start_time, end_time, start_latitude, start_longitude, start_battery, duration_hours, price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("Demo User", "SC-103", demo_start, demo_end, 52.9499, -1.1557, 59, 4, 12, "Active"),
            )

        conn.execute(
            """
            UPDATE bookings
            SET start_time = COALESCE(start_time, ?),
                end_time = COALESCE(end_time, ?)
            WHERE start_time IS NULL OR end_time IS NULL
            """,
            (
                (datetime.now() - timedelta(hours=2)).replace(second=0, microsecond=0).isoformat(timespec="minutes"),
                (datetime.now() + timedelta(hours=1)).replace(second=0, microsecond=0).isoformat(timespec="minutes"),
            ),
        )

        conn.execute(
            """
            UPDATE bookings
            SET start_latitude = COALESCE(start_latitude, (
                SELECT latitude FROM scooters WHERE scooters.code = bookings.scooter_code
            )),
                start_longitude = COALESCE(start_longitude, (
                SELECT longitude FROM scooters WHERE scooters.code = bookings.scooter_code
            )),
                start_battery = COALESCE(start_battery, (
                SELECT battery FROM scooters WHERE scooters.code = bookings.scooter_code
            ))
            WHERE start_latitude IS NULL OR start_longitude IS NULL OR start_battery IS NULL
            """
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


def next_scooter_code(conn):
    rows = conn.execute("SELECT code FROM scooters").fetchall()
    numbers = []
    for row in rows:
        code = row["code"]
        if code.startswith("SC-"):
            try:
                numbers.append(int(code.split("-", 1)[1]))
            except ValueError:
                continue
    next_number = max(numbers, default=100) + 1
    return f"SC-{next_number}"


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
            "storeId": row["store_id"],
            "location": row["location"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "battery": row["battery"],
            "hourlyPrice": row["hourly_price"],
            "available": bool(row["available"]),
        }
        for row in conn.execute(
            "SELECT code, store_id, location, latitude, longitude, battery, hourly_price, available FROM scooters ORDER BY id"
        ).fetchall()
    ]
    stores = [
        {
            "id": row["id"],
            "name": row["name"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "scooterCount": row["scooter_count"],
            "availableCount": row["available_count"],
        }
        for row in conn.execute(
            """
            SELECT
                stores.id,
                stores.name,
                stores.latitude,
                stores.longitude,
                COUNT(scooters.id) AS scooter_count,
                SUM(CASE WHEN scooters.available = 1 THEN 1 ELSE 0 END) AS available_count
            FROM stores
            LEFT JOIN scooters ON scooters.store_id = stores.id
            GROUP BY stores.id, stores.name, stores.latitude, stores.longitude
            ORDER BY stores.name
            """
        ).fetchall()
    ]
    bookings = [
        {
            "id": row["id"],
            "customer": row["customer_name"],
            "scooterId": row["scooter_code"],
            "startTime": row["start_time"],
            "endTime": row["end_time"],
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
        "stores": stores,
        "scooters": scooters,
        "bookings": bookings,
        "issues": issues,
        "priceMap": get_prices(conn),
        "summary": get_summary(conn),
    }


def sanitize_user(row):
    return {"id": row["code"], "role": row["role"], "name": row["name"], "email": row["email"]}


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def store_rows(conn):
    return conn.execute("SELECT name AS location, latitude, longitude FROM stores").fetchall()


def ensure_nearby_stores(conn, latitude, longitude):
    nearby_exists = any(
        haversine_km(latitude, longitude, row["latitude"], row["longitude"]) <= 5
        for row in store_rows(conn)
    )
    if nearby_exists:
        return False

    existing_codes = conn.execute("SELECT code FROM scooters ORDER BY id").fetchall()
    next_scooter_number = len(existing_codes) + 101
    offsets = [
        (0.0060, -0.0040),
        (-0.0045, 0.0055),
        (0.0035, 0.0070),
    ]
    created_any = False

    for index, (lat_offset, lon_offset) in enumerate(offsets, start=1):
        store_name = f"Auto Store {index}"
        store_lat = latitude + lat_offset
        store_lon = longitude + lon_offset
        cursor = conn.execute(
            "INSERT OR IGNORE INTO stores (name, latitude, longitude) VALUES (?, ?, ?)",
            (store_name, round(store_lat, 6), round(store_lon, 6)),
        )
        if cursor.lastrowid:
            store_id = cursor.lastrowid
        else:
            store_id = conn.execute("SELECT id FROM stores WHERE name = ?", (store_name,)).fetchone()["id"]
        scooter_count = random.randint(3, 10)
        scooter_rows = []
        for _ in range(scooter_count):
            scooter_rows.append(
                (
                    f"SC-{next_scooter_number}",
                    store_id,
                    store_name,
                    round(store_lat, 6),
                    round(store_lon, 6),
                    random.randint(48, 98),
                    random.randint(3, 8),
                    1,
                )
            )
            next_scooter_number += 1
        conn.executemany(
            """
            INSERT INTO scooters (code, store_id, location, latitude, longitude, battery, hourly_price, available)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            scooter_rows,
        )
        created_any = True

    return created_any


def parse_iso_minute(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def format_iso_minute(value):
    return value.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def point_offset(origin_lat, origin_lon, distance_meters, angle_degrees):
    distance_km = distance_meters / 1000
    delta_lat = (distance_km / 111.0) * math.cos(math.radians(angle_degrees))
    delta_lon = (distance_km / (111.0 * max(math.cos(math.radians(origin_lat)), 0.1))) * math.sin(math.radians(angle_degrees))
    return origin_lat + delta_lat, origin_lon + delta_lon


def generate_gps_logs(conn, booking_id):
    booking = conn.execute(
        """
        SELECT id, scooter_code, start_time, end_time, start_latitude, start_longitude, start_battery, status
        FROM bookings
        WHERE id = ?
        """,
        (booking_id,),
    ).fetchone()
    if not booking:
        return []

    start_dt = parse_iso_minute(booking["start_time"])
    end_dt = parse_iso_minute(booking["end_time"])
    if not start_dt:
        return []

    now_dt = datetime.now().replace(second=0, microsecond=0)
    generation_limit = end_dt or now_dt
    if booking["status"] == "Active":
        generation_limit = min(generation_limit, now_dt)

    if generation_limit < start_dt:
        generation_limit = start_dt

    last_log = conn.execute(
        """
        SELECT logged_at, latitude, longitude, battery
        FROM gps_logs
        WHERE booking_id = ?
        ORDER BY logged_at DESC
        LIMIT 1
        """,
        (booking_id,),
    ).fetchone()

    if last_log:
        current_dt = parse_iso_minute(last_log["logged_at"])
        current_lat = last_log["latitude"]
        current_lon = last_log["longitude"]
        current_battery = last_log["battery"]
    else:
        current_dt = start_dt
        current_lat = booking["start_latitude"]
        current_lon = booking["start_longitude"]
        current_battery = booking["start_battery"] or 100
        conn.execute(
            """
            INSERT INTO gps_logs (booking_id, logged_at, latitude, longitude, battery)
            VALUES (?, ?, ?, ?, ?)
            """,
            (booking_id, format_iso_minute(current_dt), current_lat, current_lon, current_battery),
        )

    while current_dt < generation_limit:
        next_dt = current_dt + timedelta(minutes=1)
        step_distance = random.randint(100, 500)
        step_angle = random.randint(0, 359)
        next_lat, next_lon = point_offset(current_lat, current_lon, step_distance, step_angle)
        next_battery = max(5, current_battery - random.choice([0, 1, 1, 2]))
        conn.execute(
            """
            INSERT INTO gps_logs (booking_id, logged_at, latitude, longitude, battery)
            VALUES (?, ?, ?, ?, ?)
            """,
            (booking_id, format_iso_minute(next_dt), round(next_lat, 6), round(next_lon, 6), next_battery),
        )
        current_dt = next_dt
        current_lat = next_lat
        current_lon = next_lon
        current_battery = next_battery

    rows = conn.execute(
        """
        SELECT logged_at, latitude, longitude, battery
        FROM gps_logs
        WHERE booking_id = ?
        ORDER BY logged_at
        """,
        (booking_id,),
    ).fetchall()
    return [
        {
            "loggedAt": row["logged_at"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "battery": row["battery"],
        }
        for row in rows
    ]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            with connect_db() as conn:
                self.send_json(build_state(conn))
            return
        if parsed.path == "/api/session":
            return self.handle_session()
        if parsed.path == "/api/bookings/route":
            return self.handle_booking_route(parsed.query)
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
        if parsed.path == "/api/stores/ensure-nearby":
            return self.handle_ensure_nearby_stores()
        if parsed.path == "/api/stores":
            return self.handle_create_store()
        if parsed.path == "/api/stores/update":
            return self.handle_update_store()
        if parsed.path == "/api/stores/delete":
            return self.handle_delete_store()
        if parsed.path == "/api/stores/scooters":
            return self.handle_create_store_scooter()
        if parsed.path == "/api/scooters/delete":
            return self.handle_delete_scooter()
        if parsed.path == "/api/scooters/hourly-prices":
            return self.handle_update_scooter_hourly_prices()
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

        if role == "manager":
            return self.send_json({"error": "Manager accounts cannot be registered from the public form."}, HTTPStatus.FORBIDDEN)

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
        start_time = payload.get("startTime")
        end_time = payload.get("endTime")
        duration_hours = payload.get("durationHours", 0)
        customer = user["name"]

        with connect_db() as conn:
            scooter = conn.execute(
                "SELECT code, available, hourly_price, latitude, longitude, battery FROM scooters WHERE code = ?",
                (scooter_id,),
            ).fetchone()
            if not scooter or not scooter["available"]:
                return self.send_json({"error": "Please choose an available scooter."}, HTTPStatus.BAD_REQUEST)

            try:
                if start_time and end_time:
                    start_dt = datetime.fromisoformat(start_time)
                    end_dt = datetime.fromisoformat(end_time)
                    seconds = (end_dt - start_dt).total_seconds()
                    if seconds <= 0:
                        raise ValueError
                    duration_hours = max(1, math.ceil(seconds / 3600))
                    start_time = start_dt.isoformat(timespec="minutes")
                    end_time = end_dt.isoformat(timespec="minutes")
                else:
                    duration_hours = int(duration_hours)
                    start_time = None
                    end_time = None
            except (TypeError, ValueError):
                return self.send_json({"error": "Please provide a valid booking time range."}, HTTPStatus.BAD_REQUEST)

            if duration_hours <= 0:
                return self.send_json({"error": "Invalid booking duration."}, HTTPStatus.BAD_REQUEST)
            booking_price = scooter["hourly_price"] * duration_hours

            conn.execute("UPDATE scooters SET available = 0 WHERE code = ?", (scooter_id,))
            conn.execute(
                """
                INSERT INTO bookings (customer_name, scooter_code, start_time, end_time, start_latitude, start_longitude, start_battery, duration_hours, price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    customer,
                    scooter_id,
                    start_time,
                    end_time,
                    scooter["latitude"],
                    scooter["longitude"],
                    scooter["battery"],
                    duration_hours,
                    booking_price,
                    "Active",
                ),
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

            conn.execute(
                "UPDATE bookings SET status = 'Completed', end_time = ? WHERE id = ?",
                (format_iso_minute(datetime.now()), booking["id"]),
            )
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

            conn.execute(
                "UPDATE bookings SET status = 'Cancelled', end_time = ? WHERE id = ?",
                (format_iso_minute(datetime.now()), booking["id"]),
            )
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

    def handle_ensure_nearby_stores(self):
        user = self.require_session()
        if not user:
            return

        payload = self.read_json()
        try:
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
        except (TypeError, ValueError):
            return self.send_json({"error": "Latitude and longitude are required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            created = ensure_nearby_stores(conn, latitude, longitude)
            message = (
                "Generated three nearby stores for this area."
                if created
                else "Existing stores are already available within 5 km."
            )
            self.send_json({"message": message, "created": created, "state": build_state(conn)})

    def handle_update_scooter_hourly_prices(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        scooter_prices = payload.get("scooterPrices", {})
        if not isinstance(scooter_prices, dict) or not scooter_prices:
            return self.send_json({"error": "Please provide scooter hourly prices."}, HTTPStatus.BAD_REQUEST)

        try:
            normalized = [(int(price), code.strip()) for code, price in scooter_prices.items()]
        except (TypeError, ValueError, AttributeError):
            return self.send_json({"error": "Invalid scooter price data."}, HTTPStatus.BAD_REQUEST)

        if any(price <= 0 or not code for price, code in normalized):
            return self.send_json({"error": "Hourly prices must be positive numbers."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            conn.executemany(
                "UPDATE scooters SET hourly_price = ? WHERE code = ?",
                normalized,
            )
            self.send_json({"message": "Scooter hourly prices updated.", "state": build_state(conn)})

    def handle_create_store(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        name = payload.get("name", "").strip()
        try:
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
        except (TypeError, ValueError):
            return self.send_json({"error": "Store latitude and longitude are required."}, HTTPStatus.BAD_REQUEST)

        if not name:
            return self.send_json({"error": "Store name is required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            try:
                conn.execute(
                    "INSERT INTO stores (name, latitude, longitude) VALUES (?, ?, ?)",
                    (name, latitude, longitude),
                )
            except sqlite3.IntegrityError:
                return self.send_json({"error": "A store with this name already exists."}, HTTPStatus.BAD_REQUEST)
            self.send_json({"message": f"Store {name} created.", "state": build_state(conn)})

    def handle_update_store(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        try:
            store_id = int(payload.get("storeId"))
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
        except (TypeError, ValueError):
            return self.send_json(
                {"error": "Store id, latitude, and longitude are required."},
                HTTPStatus.BAD_REQUEST,
            )

        name = payload.get("name", "").strip()
        if not name:
            return self.send_json({"error": "Store name is required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            existing_store = conn.execute(
                "SELECT id, name FROM stores WHERE id = ?",
                (store_id,),
            ).fetchone()
            if not existing_store:
                return self.send_json({"error": "Store not found."}, HTTPStatus.NOT_FOUND)

            duplicate_store = conn.execute(
                "SELECT id FROM stores WHERE name = ? AND id <> ?",
                (name, store_id),
            ).fetchone()
            if duplicate_store:
                return self.send_json(
                    {"error": "Another store already uses this name."},
                    HTTPStatus.BAD_REQUEST,
                )

            conn.execute(
                "UPDATE stores SET name = ?, latitude = ?, longitude = ? WHERE id = ?",
                (name, latitude, longitude, store_id),
            )
            conn.execute(
                """
                UPDATE scooters
                SET location = ?, latitude = ?, longitude = ?
                WHERE store_id = ?
                """,
                (name, latitude, longitude, store_id),
            )

            self.send_json(
                {"message": f"Store {name} updated.", "state": build_state(conn)},
            )

    def handle_delete_store(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        try:
            store_id = int(payload.get("storeId"))
        except (TypeError, ValueError):
            return self.send_json({"error": "Store id is required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            store = conn.execute(
                "SELECT id, name FROM stores WHERE id = ?",
                (store_id,),
            ).fetchone()
            if not store:
                return self.send_json({"error": "Store not found."}, HTTPStatus.NOT_FOUND)

            scooter_codes = [
                row["code"]
                for row in conn.execute(
                    "SELECT code FROM scooters WHERE store_id = ?",
                    (store_id,),
                ).fetchall()
            ]

            if scooter_codes:
                placeholders = ",".join("?" for _ in scooter_codes)
                active_booking = conn.execute(
                    f"""
                    SELECT 1
                    FROM bookings
                    WHERE scooter_code IN ({placeholders}) AND status = 'Active'
                    LIMIT 1
                    """,
                    scooter_codes,
                ).fetchone()
                if active_booking:
                    return self.send_json(
                        {"error": "This store has scooter(s) with active bookings and cannot be deleted yet."},
                        HTTPStatus.BAD_REQUEST,
                    )
                conn.execute(
                    f"DELETE FROM issues WHERE scooter_code IN ({placeholders})",
                    scooter_codes,
                )
                conn.execute("DELETE FROM scooters WHERE store_id = ?", (store_id,))

            conn.execute("DELETE FROM stores WHERE id = ?", (store_id,))
            self.send_json({"message": f"Store {store['name']} deleted.", "state": build_state(conn)})

    def handle_create_store_scooter(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        try:
            store_id = int(payload.get("storeId"))
            hourly_price = int(payload.get("hourlyPrice"))
        except (TypeError, ValueError):
            return self.send_json({"error": "Store id and scooter hourly price are required."}, HTTPStatus.BAD_REQUEST)

        battery = payload.get("battery")
        try:
            battery_value = int(battery) if battery is not None else random.randint(60, 95)
        except (TypeError, ValueError):
            return self.send_json({"error": "Battery must be a valid number."}, HTTPStatus.BAD_REQUEST)

        if hourly_price <= 0:
            return self.send_json({"error": "Hourly price must be greater than zero."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            store = conn.execute(
                "SELECT id, name, latitude, longitude FROM stores WHERE id = ?",
                (store_id,),
            ).fetchone()
            if not store:
                return self.send_json({"error": "Store not found."}, HTTPStatus.NOT_FOUND)

            scooter_code = next_scooter_code(conn)
            conn.execute(
                """
                INSERT INTO scooters (code, store_id, location, latitude, longitude, battery, hourly_price, available)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    scooter_code,
                    store["id"],
                    store["name"],
                    store["latitude"],
                    store["longitude"],
                    max(10, min(100, battery_value)),
                    hourly_price,
                ),
            )
            self.send_json({"message": f"{scooter_code} added to {store['name']}.", "state": build_state(conn)})

    def handle_delete_scooter(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        scooter_code = payload.get("scooterId", "").strip()
        if not scooter_code:
            return self.send_json({"error": "Scooter id is required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            scooter = conn.execute(
                "SELECT code FROM scooters WHERE code = ?",
                (scooter_code,),
            ).fetchone()
            if not scooter:
                return self.send_json({"error": "Scooter not found."}, HTTPStatus.NOT_FOUND)

            active_booking = conn.execute(
                "SELECT 1 FROM bookings WHERE scooter_code = ? AND status = 'Active' LIMIT 1",
                (scooter_code,),
            ).fetchone()
            if active_booking:
                return self.send_json(
                    {"error": "This scooter has an active booking and cannot be deleted yet."},
                    HTTPStatus.BAD_REQUEST,
                )

            conn.execute("DELETE FROM issues WHERE scooter_code = ?", (scooter_code,))
            conn.execute("DELETE FROM scooters WHERE code = ?", (scooter_code,))
            self.send_json({"message": f"Scooter {scooter_code} deleted.", "state": build_state(conn)})

    def handle_booking_route(self, query_string):
        user = self.require_session()
        if not user:
            return

        params = parse_qs(query_string)
        try:
            booking_id = int(params.get("bookingId", ["-1"])[0])
        except ValueError:
            return self.send_json({"error": "A valid booking id is required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            booking = conn.execute(
                """
                SELECT id, customer_name, scooter_code, status, start_time, end_time
                FROM bookings
                WHERE id = ?
                """,
                (booking_id,),
            ).fetchone()
            if not booking:
                return self.send_json({"error": "Booking not found."}, HTTPStatus.NOT_FOUND)
            if user["role"] != "manager" and booking["customer_name"] != user["name"]:
                return self.send_json({"error": "You can only view your own booking route."}, HTTPStatus.FORBIDDEN)

            route = generate_gps_logs(conn, booking_id)
            self.send_json(
                {
                    "booking": {
                        "id": booking["id"],
                        "customer": booking["customer_name"],
                        "scooterId": booking["scooter_code"],
                        "status": booking["status"],
                        "startTime": booking["start_time"],
                        "endTime": booking["end_time"],
                    },
                    "route": route,
                }
            )

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
