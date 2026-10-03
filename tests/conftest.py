"""
Integration tests - asli MySQL par chalte hain (alag test database 'rentafriend_test').
Run:  DB_HOST=127.0.0.1 DB_USER=root DB_PASSWORD=... pytest -q
DB na mile to tests skip ho jaate hain.
"""
import os
import sys
from datetime import datetime
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DB_NAME"] = os.getenv("TEST_DB_NAME", "rentafriend_test")
os.environ["RATE_LIMIT_DISABLED"] = "true"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("DB_HOST", "127.0.0.1")

H = {"X-Requested-With": "GreenBEE"}


@pytest.fixture(scope="session")
def app_module():
    import mysql.connector
    from config import Config
    cfg = dict(Config.DB_CONFIG)
    cfg.pop("database", None)
    try:
        mysql.connector.connect(**cfg).close()
    except Exception as e:
        pytest.skip(f"MySQL available nahi: {e}")
    import init_db
    init_db.main()
    import app as A
    A.app.config["TESTING"] = True
    return A


@pytest.fixture(autouse=True)
def clean_db(app_module):
    import db
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in ("notification", "report", "booking", "customer", "companion"):
        cur.execute(f"TRUNCATE TABLE {t}")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    conn.close()
    import ratelimit
    ratelimit.reset()
    yield


@pytest.fixture
def clock(app_module):
    """Time freeze: 12:00 (booking tests time-of-day par depend na karein)."""
    import db
    state = {"now": datetime.combine(datetime.now().date(), datetime.min.time()).replace(hour=12)}
    with mock.patch.object(db, "now_local", lambda: state["now"]):
        yield state


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture
def google(app_module):
    """google('a@x.com') -> is email se verify hone wala token use karo."""
    people = {}

    def fake(token):
        return people.get(token)

    def make(email, name="Test User"):
        people[f"tok-{email}"] = {"email": email, "google_id": "g-" + email, "name": name}
        return f"tok-{email}"

    with mock.patch.object(app_module.auth, "verify_google_token", fake):
        yield make


def new_client(flask_app):
    return flask_app.test_client()


def register_companion(c, token, phone="9000000001", consent=True, dob="1995-05-05", **extra):
    form = {"credential": token, "full_name": "Asha Companion", "dob": dob, "gender": "Female", "phone": phone,
            "city": "Delhi", "latitude": "28.61", "longitude": "77.20", "hourly_rate": "200",
            "id_proof_type": "Aadhar", "id_proof_number": "123412341234"}
    if consent:
        form["consent"] = "true"
    form.update(extra)
    return c.post("/api/companions", data=form, headers=H)


def signup_customer(c, token, phone="9111111111", consent=True):
    body = {"credential": token, "phone": phone, "latitude": 28.6, "longitude": 77.2}
    if consent:
        body["consent"] = True
    return c.post("/api/auth/google", json=body, headers=H)


def admin_client(flask_app):
    c = flask_app.test_client()
    assert c.post("/api/admin/login", json={"key": "test-admin-key"}, headers=H).status_code == 200
    return c


def insert_booking(companion_id, customer_id, start="12:30", end="13:30", status="Pending", day=None):
    import db
    day = day or db.today_local()
    return db._exec(
        """INSERT INTO booking (companion_id, customer_id, booking_date, start_time, end_time,
                                rate_at_booking, total_amount, status)
           VALUES (%s,%s,%s,%s,%s,200,200,%s)""", (companion_id, customer_id, day, start, end, status), insert=True)
