import json
import math
import random
import secrets
import hashlib
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
                password TEXT NOT NULL,
                account_type TEXT NOT NULL DEFAULT 'standard',
                card_brand TEXT,
                card_last4 TEXT,
                card_token TEXT
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
                customer_email TEXT,
                is_guest INTEGER NOT NULL DEFAULT 0,
                scooter_code TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                start_latitude REAL,
                start_longitude REAL,
                start_battery INTEGER,
                duration_hours INTEGER NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'Paid',
                payment_method TEXT NOT NULL DEFAULT 'Card',
                discount_type TEXT NOT NULL DEFAULT 'None',
                discount_rate REAL NOT NULL DEFAULT 0,
                confirmation_reference TEXT,
                confirmation_email_status TEXT NOT NULL DEFAULT 'Pending'
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

            CREATE TABLE IF NOT EXISTS email_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                sent_at TEXT NOT NULL
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
        user_columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "account_type" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN account_type TEXT NOT NULL DEFAULT 'standard'")
        if "card_brand" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN card_brand TEXT")
        if "card_last4" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN card_last4 TEXT")
        if "card_token" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN card_token TEXT")

        if "customer_email" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN customer_email TEXT")
        if "is_guest" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN is_guest INTEGER NOT NULL DEFAULT 0")
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
        if "payment_status" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Paid'")
        if "payment_method" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Card'")
        if "discount_type" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN discount_type TEXT NOT NULL DEFAULT 'None'")
        if "discount_rate" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN discount_rate REAL NOT NULL DEFAULT 0")
        if "confirmation_reference" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN confirmation_reference TEXT")
        if "confirmation_email_status" not in booking_columns:
            conn.execute("ALTER TABLE bookings ADD COLUMN confirmation_email_status TEXT NOT NULL DEFAULT 'Pending'")

        existing_users = {
            row["email"]: row
            for row in conn.execute("SELECT code, role, name, email, password FROM users").fetchall()
        }
        bootstrap_users = []
        if "demo@cityhop.app" not in existing_users:
            bootstrap_users.append(("U-001", "customer", "Demo User", "demo@cityhop.app", hash_password("demo")))
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
                (admin_code, "manager", "Admin", "admin", hash_password("admin")),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET role = 'manager',
                    name = 'Admin',
                    password = ?
                WHERE email = 'admin'
                """,
                (hash_password("admin"),),
            )
        conn.execute(
            """
            UPDATE users
            SET account_type = COALESCE(account_type, 'standard')
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
        conn.execute(
            """
            UPDATE bookings
            SET customer_email = COALESCE(customer_email, (
                SELECT email FROM users WHERE users.name = bookings.customer_name LIMIT 1
            )),
                payment_status = COALESCE(payment_status, 'Paid'),
                payment_method = COALESCE(payment_method, 'Card'),
                discount_type = COALESCE(discount_type, 'None'),
                discount_rate = COALESCE(discount_rate, 0),
                confirmation_email_status = COALESCE(confirmation_email_status, 'Sent')
            """
        )

        plaintext_users = conn.execute("SELECT id, password FROM users").fetchall()
        for user_row in plaintext_users:
            if user_row["password"] and not user_row["password"].startswith("pbkdf2_sha256$"):
                conn.execute(
                    "UPDATE users SET password = ? WHERE id = ?",
                    (hash_password(user_row["password"]), user_row["id"]),
                )

        if conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO issues (scooter_code, description, priority, status) VALUES (?, ?, ?, ?)",
                ("SC-103", "Front light is flickering during evening use.", "High", "Open"),
            )


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def infer_card_brand(card_number):
    if card_number.startswith("4"):
        return "Visa"
    if any(card_number.startswith(prefix) for prefix in ("51", "52", "53", "54", "55")):
        return "Mastercard"
    if card_number.startswith(("34", "37")):
        return "Amex"
    return "Card"


def tokenize_card(card_number):
    return hashlib.sha256(card_number.encode("utf-8")).hexdigest()


def client_password_digest(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def normalize_password_secret(password):
    if len(password) == 64 and all(character in "0123456789abcdefABCDEF" for character in password):
        return password.lower()
    return client_password_digest(password)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    normalized_password = normalize_password_secret(password)
    digest = hashlib.pbkdf2_hmac("sha256", normalized_password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password, stored_password):
    if not stored_password:
        return False
    if not stored_password.startswith("pbkdf2_sha256$"):
        return secrets.compare_digest(stored_password, normalize_password_secret(password))
    _, salt, digest = stored_password.split("$", 2)
    normalized_password = normalize_password_secret(password)
    candidate = hashlib.pbkdf2_hmac("sha256", normalized_password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return secrets.compare_digest(candidate, digest)


def booking_option_for_hours(duration_hours):
    if duration_hours <= 1:
        return "1 hour"
    if duration_hours <= 4:
        return "4 hours"
    if duration_hours <= 24:
        return "1 day"
    return "1 week"


def infer_issue_priority(description):
    normalized = description.lower()
    high_keywords = ["brake", "crash", "accident", "fire", "smoke", "injury", "unsafe"]
    medium_keywords = ["battery", "light", "lock", "gps", "tyre", "tire", "screen", "slow"]
    if any(keyword in normalized for keyword in high_keywords):
        return "High"
    if any(keyword in normalized for keyword in medium_keywords):
        return "Medium"
    return "Low"


def calculate_discount(conn, customer_name, account_type, added_duration_hours):
    now_dt = datetime.now()
    week_start = (now_dt - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    existing_hours = conn.execute(
        """
        SELECT COALESCE(SUM(duration_hours), 0)
        FROM bookings
        WHERE customer_name = ? AND start_time >= ?
        """,
        (customer_name, format_iso_minute(week_start)),
    ).fetchone()[0]
    total_hours = existing_hours + added_duration_hours

    discounts = [("None", 0.0)]
    if total_hours >= 8:
        discounts.append(("Frequent user", 0.12))
    if account_type == "student":
        discounts.append(("Student", 0.10))
    if account_type == "senior":
        discounts.append(("Senior", 0.15))
    return max(discounts, key=lambda item: item[1])


def create_confirmation_reference():
    return f"CH-{secrets.token_hex(4).upper()}"


def send_confirmation_email(conn, booking_id, recipient, scooter_code, start_time, end_time, price):
    reference = create_confirmation_reference()
    subject = f"CityHop booking confirmation {reference}"
    body = (
        f"Your booking for {scooter_code} is confirmed.\n"
        f"Start: {start_time}\nEnd: {end_time}\nPrice: GBP {price}\nReference: {reference}"
    )
    conn.execute(
        """
        INSERT INTO email_logs (booking_id, recipient, subject, body, status, sent_at)
        VALUES (?, ?, ?, ?, 'Sent', ?)
        """,
        (booking_id, recipient, subject, body, format_iso_minute(datetime.now())),
    )
    conn.execute(
        """
        UPDATE bookings
        SET confirmation_reference = ?, confirmation_email_status = 'Sent'
        WHERE id = ?
        """,
        (reference, booking_id),
    )
    return reference


def build_statistics(conn):
    today = datetime.now().date()
    dates = [(today - timedelta(days=offset)) for offset in range(6, -1, -1)]
    daily_lookup = {date.isoformat(): {"date": date.isoformat(), "income": 0, "bookings": 0} for date in dates}
    option_lookup = {
        "1 hour": {"option": "1 hour", "income": 0, "bookings": 0},
        "4 hours": {"option": "4 hours", "income": 0, "bookings": 0},
        "1 day": {"option": "1 day", "income": 0, "bookings": 0},
        "1 week": {"option": "1 week", "income": 0, "bookings": 0},
    }
    week_start = dates[0].isoformat()

    rows = conn.execute(
        """
        SELECT start_time, duration_hours, price
        FROM bookings
        WHERE start_time IS NOT NULL AND date(start_time) >= date(?)
        ORDER BY start_time
        """,
        (week_start,),
    ).fetchall()

    for row in rows:
        booking_date = row["start_time"][:10]
        if booking_date in daily_lookup:
            daily_lookup[booking_date]["income"] += row["price"]
            daily_lookup[booking_date]["bookings"] += 1
        option_key = booking_option_for_hours(row["duration_hours"])
        option_lookup[option_key]["income"] += row["price"]
        option_lookup[option_key]["bookings"] += 1

    return {
        "weeklyIncomeByOption": list(option_lookup.values()),
        "dailyIncome": [daily_lookup[date.isoformat()] for date in dates],
    }


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
    high_priority_issues = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE status = 'Open' AND priority = 'High'"
    ).fetchone()[0]
    return {
        "availableScooters": available,
        "activeBookings": active,
        "totalBookings": total_bookings,
        "totalRevenue": revenue,
        "openIssues": issues,
        "highPriorityIssues": high_priority_issues,
        "fleetAvailability": round((available / total) * 100) if total else 0,
    }


def build_state(conn):
    users = [
        {
            "id": row["code"],
            "role": row["role"],
            "name": row["name"],
            "email": row["email"],
            "accountType": row["account_type"],
            "hasSavedCard": bool(row["card_last4"]),
            "savedCardLabel": f"{row['card_brand']} ending {row['card_last4']}" if row["card_last4"] else "",
        }
        for row in conn.execute(
            "SELECT code, role, name, email, account_type, card_brand, card_last4 FROM users ORDER BY id"
        ).fetchall()
    ]
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
            "paymentStatus": row["payment_status"],
            "paymentMethod": row["payment_method"],
            "discountType": row["discount_type"],
            "discountRate": row["discount_rate"],
            "confirmationReference": row["confirmation_reference"],
            "confirmationEmailStatus": row["confirmation_email_status"],
            "customerEmail": row["customer_email"],
            "isGuest": bool(row["is_guest"]),
            "bookingOption": booking_option_for_hours(row["duration_hours"]),
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
        "statistics": build_statistics(conn),
    }


def sanitize_user(row):
    return {
        "id": row["code"],
        "role": row["role"],
        "name": row["name"],
        "email": row["email"],
        "accountType": row["account_type"] if "account_type" in row.keys() else "standard",
    }


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
        if parsed.path == "/api/bookings/extend":
            return self.handle_extend_booking()
        if parsed.path == "/api/bookings/cancel":
            return self.handle_cancel_booking()
        if parsed.path == "/api/staff/bookings":
            return self.handle_staff_booking()
        if parsed.path == "/api/issues":
            return self.handle_create_issue()
        if parsed.path == "/api/issues/escalate":
            return self.handle_escalate_issue()
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
        account_type = payload.get("accountType", "standard").strip().lower() or "standard"

        if role == "manager":
            return self.send_json({"error": "Manager accounts cannot be registered from the public form."}, HTTPStatus.FORBIDDEN)

        if not name or not email or not password:
            return self.send_json({"error": "Name, email, and password are required."}, HTTPStatus.BAD_REQUEST)
        if account_type not in {"standard", "student", "senior"}:
            return self.send_json({"error": "Please choose a valid account type."}, HTTPStatus.BAD_REQUEST)

        prefix = "M" if role == "manager" else "U"
        with connect_db() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                return self.send_json({"error": "Email already exists."}, HTTPStatus.BAD_REQUEST)

            count = conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", (role,)).fetchone()[0] + 1
            code = f"{prefix}-{count:03d}"
            conn.execute(
                "INSERT INTO users (code, role, name, email, password, account_type) VALUES (?, ?, ?, ?, ?, ?)",
                (code, role, name, email, hash_password(password), account_type),
            )
            user = {"id": code, "role": role, "name": name, "email": email, "accountType": account_type}
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
                "SELECT code, role, name, email, password, account_type FROM users WHERE email = ? AND role = ?",
                (email, role),
            ).fetchone()

        if not row or not verify_password(password, row["password"]):
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

    def resolve_payment(self, conn, user_row, payload, allow_card_save=True):
        payment = payload.get("payment", {}) or {}
        use_saved_card = bool(payment.get("useSavedCard"))
        if use_saved_card:
            if not user_row or not user_row["card_last4"]:
                raise ValueError("No saved card is available for this account.")
            return {
                "payment_status": "Paid",
                "payment_method": f"{user_row['card_brand']} ending {user_row['card_last4']}",
            }

        cardholder = payment.get("cardholderName", "").strip()
        card_number = "".join(ch for ch in str(payment.get("cardNumber", "")) if ch.isdigit())
        expiry = str(payment.get("expiry", "")).strip()
        cvv = "".join(ch for ch in str(payment.get("cvv", "")) if ch.isdigit())

        if len(card_number) < 12 or len(cvv) < 3 or not cardholder or not expiry:
            raise ValueError("Please provide valid simulated card payment details.")

        brand = infer_card_brand(card_number)
        if user_row and allow_card_save and payment.get("saveCard"):
            conn.execute(
                """
                UPDATE users
                SET card_brand = ?, card_last4 = ?, card_token = ?
                WHERE code = ?
                """,
                (brand, card_number[-4:], tokenize_card(card_number), user_row["code"]),
            )
        return {
            "payment_status": "Paid",
            "payment_method": f"{brand} ending {card_number[-4:]}",
        }

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
            user_row = conn.execute(
                "SELECT code, name, email, account_type, card_brand, card_last4, card_token FROM users WHERE code = ?",
                (user["id"],),
            ).fetchone()
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
            payment_data = None
            try:
                payment_data = self.resolve_payment(conn, user_row, payload)
            except ValueError as error:
                return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

            discount_type, discount_rate = calculate_discount(conn, customer, user_row["account_type"], duration_hours)
            base_price = scooter["hourly_price"] * duration_hours
            booking_price = max(1, round(base_price * (1 - discount_rate)))

            conn.execute("UPDATE scooters SET available = 0 WHERE code = ?", (scooter_id,))
            cursor = conn.execute(
                """
                INSERT INTO bookings (
                    customer_name, customer_email, is_guest, scooter_code, start_time, end_time,
                    start_latitude, start_longitude, start_battery, duration_hours, price, status,
                    payment_status, payment_method, discount_type, discount_rate, confirmation_email_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    customer,
                    user_row["email"],
                    0,
                    scooter_id,
                    start_time,
                    end_time,
                    scooter["latitude"],
                    scooter["longitude"],
                    scooter["battery"],
                    duration_hours,
                    booking_price,
                    "Active",
                    payment_data["payment_status"],
                    payment_data["payment_method"],
                    discount_type,
                    discount_rate,
                    "Pending",
                ),
            )
            reference = send_confirmation_email(
                conn,
                cursor.lastrowid,
                user_row["email"],
                scooter_id,
                start_time,
                end_time,
                booking_price,
            )
            self.send_json(
                {
                    "message": f"Booking created for {customer}. Confirmation email sent with reference {reference}.",
                    "state": build_state(conn),
                }
            )

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

    def handle_extend_booking(self):
        user = self.require_session()
        if not user:
            return

        payload = self.read_json()
        booking_id = int(payload.get("bookingId", -1))
        additional_hours = int(payload.get("additionalHours", 0))
        if additional_hours <= 0:
            return self.send_json({"error": "Additional booking hours must be greater than zero."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            booking = conn.execute(
                """
                SELECT id, scooter_code, status, customer_name, end_time, duration_hours, price, discount_rate
                FROM bookings
                WHERE id = ?
                """,
                (booking_id,),
            ).fetchone()
            if not booking or booking["status"] != "Active":
                return self.send_json({"error": "Only active bookings can be extended."}, HTTPStatus.BAD_REQUEST)
            if user["role"] != "manager" and booking["customer_name"] != user["name"]:
                return self.send_json({"error": "You can only extend your own booking."}, HTTPStatus.FORBIDDEN)

            scooter = conn.execute(
                "SELECT hourly_price FROM scooters WHERE code = ?",
                (booking["scooter_code"],),
            ).fetchone()
            if not scooter:
                return self.send_json({"error": "Scooter not found for this booking."}, HTTPStatus.NOT_FOUND)

            current_end = parse_iso_minute(booking["end_time"]) or datetime.now().replace(second=0, microsecond=0)
            new_end = current_end + timedelta(hours=additional_hours)
            extra_price = max(1, round(scooter["hourly_price"] * additional_hours * (1 - booking["discount_rate"])))
            conn.execute(
                """
                UPDATE bookings
                SET end_time = ?, duration_hours = duration_hours + ?, price = price + ?
                WHERE id = ?
                """,
                (format_iso_minute(new_end), additional_hours, extra_price, booking_id),
            )
            self.send_json(
                {
                    "message": f"Booking extended by {additional_hours} hour(s).",
                    "state": build_state(conn),
                }
            )

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

    def handle_staff_booking(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        guest_name = payload.get("guestName", "").strip()
        guest_email = payload.get("guestEmail", "").strip()
        scooter_id = payload.get("scooterId", "").strip()
        start_time = payload.get("startTime")
        end_time = payload.get("endTime")
        if not guest_name or not guest_email or not scooter_id or not start_time or not end_time:
            return self.send_json({"error": "Guest name, email, scooter, and booking time range are required."}, HTTPStatus.BAD_REQUEST)

        with connect_db() as conn:
            scooter = conn.execute(
                "SELECT code, available, hourly_price, latitude, longitude, battery FROM scooters WHERE code = ?",
                (scooter_id,),
            ).fetchone()
            if not scooter or not scooter["available"]:
                return self.send_json({"error": "Please choose an available scooter."}, HTTPStatus.BAD_REQUEST)

            try:
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
                seconds = (end_dt - start_dt).total_seconds()
                if seconds <= 0:
                    raise ValueError
                duration_hours = max(1, math.ceil(seconds / 3600))
            except (TypeError, ValueError):
                return self.send_json({"error": "Please provide a valid booking time range."}, HTTPStatus.BAD_REQUEST)

            try:
                payment_data = self.resolve_payment(conn, None, payload, allow_card_save=False)
            except ValueError as error:
                return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

            booking_price = scooter["hourly_price"] * duration_hours
            conn.execute("UPDATE scooters SET available = 0 WHERE code = ?", (scooter_id,))
            cursor = conn.execute(
                """
                INSERT INTO bookings (
                    customer_name, customer_email, is_guest, scooter_code, start_time, end_time,
                    start_latitude, start_longitude, start_battery, duration_hours, price, status,
                    payment_status, payment_method, discount_type, discount_rate, confirmation_email_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guest_name,
                    guest_email,
                    1,
                    scooter_id,
                    start_dt.isoformat(timespec="minutes"),
                    end_dt.isoformat(timespec="minutes"),
                    scooter["latitude"],
                    scooter["longitude"],
                    scooter["battery"],
                    duration_hours,
                    booking_price,
                    "Active",
                    payment_data["payment_status"],
                    payment_data["payment_method"],
                    "None",
                    0,
                    "Pending",
                ),
            )
            reference = send_confirmation_email(
                conn,
                cursor.lastrowid,
                guest_email,
                scooter_id,
                start_dt.isoformat(timespec="minutes"),
                end_dt.isoformat(timespec="minutes"),
                booking_price,
            )
            self.send_json(
                {
                    "message": f"Walk-in booking created for {guest_name}. Confirmation email sent with reference {reference}.",
                    "state": build_state(conn),
                }
            )

    def handle_create_issue(self):
        user = self.require_session()
        if not user:
            return

        payload = self.read_json()
        scooter_id = payload.get("scooterId", "").strip()
        description = payload.get("description", "").strip()
        if not scooter_id or not description:
            return self.send_json({"error": "Issue description is required."}, HTTPStatus.BAD_REQUEST)

        priority = infer_issue_priority(description)
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO issues (scooter_code, description, priority, status) VALUES (?, ?, ?, ?)",
                (scooter_id, description, priority, "Open"),
            )
            self.send_json({"message": "Issue submitted.", "state": build_state(conn)})

    def handle_escalate_issue(self):
        if not self.require_manager():
            return

        payload = self.read_json()
        issue_id = int(payload.get("issueId", -1))

        with connect_db() as conn:
            issue = conn.execute(
                "SELECT id, status, priority FROM issues WHERE id = ?",
                (issue_id,),
            ).fetchone()
            if not issue:
                return self.send_json({"error": "Issue not found."}, HTTPStatus.BAD_REQUEST)
            if issue["status"] == "Resolved":
                return self.send_json({"error": "Resolved issues cannot be escalated."}, HTTPStatus.BAD_REQUEST)
            if issue["priority"] == "High":
                return self.send_json({"error": "Issue is already high priority."}, HTTPStatus.BAD_REQUEST)

            conn.execute("UPDATE issues SET priority = 'High' WHERE id = ?", (issue_id,))
            self.send_json({"message": "Issue escalated to high priority.", "state": build_state(conn)})

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
