"""
Database layer - saari MySQL queries yahan hain,
routes (app.py) sirf inhe call karenge.
"""

import os
from datetime import datetime, timedelta
import mysql.connector
from config import Config
import crypto_util

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))
except Exception:  # tzdata na ho to server ka local time
    _TZ = None


def now_local():
    """Booking ke saare time-checks isi se hote hain (default Asia/Kolkata, APP_TIMEZONE se badlo)."""
    return datetime.now(_TZ).replace(tzinfo=None) if _TZ else datetime.now()


def today_local():
    return now_local().date()


BOOKING_BUFFER_MINUTES = 60  # 1 ghanta - sirf booking ke END ke BAAD lagta hai (start se pehle koi buffer nahi)


def _to_minutes(value):
    """
    Time value (string 'HH:MM'/'HH:MM:SS', ya DB se aaya hua timedelta/time object)
    ko din ke shuru se minutes mein convert karta hai. MySQL connector TIME columns
    ko Python 'timedelta' ke roop mein return karta hai, isliye wo case bhi handle karna zaroori hai.
    MySQL ke TIMESTAMPDIFF() ko bare TIME strings (bina DATE ke) dena kabhi kabhi
    date-context parsing ki wajah se NULL return kar deta hai - isliye duration
    hamesha Python mein hi nikalte hain, MySQL ki type-coercion pe depend nahi karte.
    """
    if isinstance(value, timedelta):
        return value.total_seconds() / 60
    if hasattr(value, "hour") and hasattr(value, "minute"):  # datetime.time
        return value.hour * 60 + value.minute + value.second / 60
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(str(value), fmt)
            return dt.hour * 60 + dt.minute + dt.second / 60
        except ValueError:
            continue
    raise ValueError(f"Invalid time format: {value}")


def _combine_date_minutes(date_value, minutes):
    """Date + minutes-since-midnight ko ek pura datetime bana deta hai, comparison ke liye."""
    return datetime.combine(date_value, datetime.min.time()) + timedelta(minutes=minutes)


# ---------------- SHIFTS (aaj ki availability) ----------------
SHIFTS = {"morning": (6 * 60, 14 * 60), "evening": (14 * 60, 22 * 60)}  # minutes since midnight
MIN_FREE_MINUTES = 60  # itna gap bache tabhi shift "available" maani jaayegi


def shift_availability(bookings, now_minutes):
    """
    bookings: aaj ki active (Pending/Confirmed) bookings, [(start_min, end_min), ...].
    Returns {"morning": "available"|"booked"|"ended", "evening": ...}.
    Blocked window = [start, end + BOOKING_BUFFER_MINUTES) - bilkul wahi rule jo create_booking_atomic
    conflict check mein lagata hai, taaki card jo dikhaye wahi booking mein chale.
    """
    blocked = sorted((s, e + BOOKING_BUFFER_MINUTES) for s, e in bookings)
    out = {}
    for name, (shift_start, shift_end) in SHIFTS.items():
        lo = max(shift_start, int(now_minutes) + 1)  # start time past mein nahi ho sakta
        if lo + MIN_FREE_MINUTES > shift_end:
            out[name] = "ended"
            continue
        cursor, best_gap = lo, 0
        for b_start, b_end in blocked:
            if b_end <= cursor:
                continue
            if b_start >= shift_end:
                break
            best_gap = max(best_gap, min(b_start, shift_end) - cursor)
            cursor = max(cursor, b_end)
        best_gap = max(best_gap, shift_end - cursor)
        out[name] = "available" if best_gap >= MIN_FREE_MINUTES else "booked"
    return out


DAY_START, DAY_END = 6 * 60, 22 * 60  # companion ka bookable din: 6 AM - 10 PM


def free_windows(bookings, now_minutes):
    """
    Aaj ke asli khaali time-slots, DB ki Pending/Confirmed bookings se.
    bookings: [(start_min, end_min), ...]. Returns [["HH:MM", "HH:MM"], ...] (kam se kam MIN_FREE_MINUTES ke gap).
    Blocked window = [start, end + buffer) - bilkul wahi rule jo create_booking_atomic mein hai.
    """
    cursor, out = max(DAY_START, int(now_minutes) + 1), []
    for b_start, b_end in sorted((s, e + BOOKING_BUFFER_MINUTES) for s, e in bookings):
        if b_end <= cursor:
            continue
        if b_start - cursor >= MIN_FREE_MINUTES:
            out.append((cursor, b_start))
        cursor = max(cursor, b_end)
    if DAY_END - cursor >= MIN_FREE_MINUTES:
        out.append((cursor, DAY_END))
    fmt = lambda m: f"{int(m) // 60:02d}:{int(m) % 60:02d}"
    return [[fmt(a), fmt(min(b, DAY_END))] for a, b in out]


def day_status(shifts):
    """'available' (koi shift khali), 'booked' (aaj poora booked), 'ended' (aaj ke shifts khatam)."""
    values = set(shifts.values())
    if "available" in values:
        return "available"
    return "booked" if "booked" in values else "ended"


def _attach_shifts(cursor, rows):
    """Nearby results mein har companion ke liye aaj ke shift-wise availability jodta hai (ek hi extra query)."""
    if not rows:
        return rows
    now = now_local()
    ids = [r["companion_id"] for r in rows]
    cursor.execute(
        "SELECT companion_id, start_time, end_time FROM booking "
        "WHERE booking_date = %s AND status IN ('Pending','Confirmed') AND companion_id IN (" +
        ",".join(["%s"] * len(ids)) + ")", [now.date(), *ids])
    by_comp = {}
    for b in cursor.fetchall():
        by_comp.setdefault(b["companion_id"], []).append((_to_minutes(b["start_time"]), _to_minutes(b["end_time"])))
    now_min = now.hour * 60 + now.minute
    for r in rows:
        booked = by_comp.get(r["companion_id"], [])
        r["shifts"] = shift_availability(booked, now_min)
        r["day_status"] = day_status(r["shifts"])
        r["free_windows"] = free_windows(booked, now_min)
    return rows



def get_connection():
    return mysql.connector.connect(**Config.DB_CONFIG)


# ---------------- CUSTOMER ----------------
def find_customer_by_google_id(google_id):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM customer WHERE google_id = %s", (google_id,))
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            conn.close()


def find_customer_by_email(email):
    """Google email se customer dhundhta hai (role detection ke liye)."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM customer WHERE email = %s", (email,))
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_customer_by_id(customer_id):
    """Session se aaye customer_id ko verify/load karne ke liye (naam + status)."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT customer_id, full_name, status FROM customer WHERE customer_id = %s",
            (customer_id,)
        )
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_customer(name, phone, email, google_id, city, latitude, longitude, consent_at=None):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO customer
               (full_name, phone, email, google_id, email_verified, city, latitude, longitude, consent_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name, phone, email, google_id, True, city, latitude, longitude, consent_at)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_customer_location(customer_id, latitude, longitude):
    """Existing customer ki location sign-in par refresh karta hai."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE customer SET latitude = %s, longitude = %s WHERE customer_id = %s",
            (latitude, longitude, customer_id)
        )
        conn.commit()
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------- COMPANION (registration + fetch) ----------------
def find_companion_by_email(email):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        # 'photo' blob column jaan-boojh kar exclude kiya - jsonify() bytes pe crash karta hai.
        # Photo alag se /api/companions/<id>/photo endpoint se serve hota hai.
        cursor.execute("""
            SELECT companion_id, full_name, dob, gender, phone, bio,
                   (photo IS NOT NULL) AS has_photo, languages, skills, ngo_reference,
                   email, google_id, email_verified, city, latitude, longitude,
                   service_type, hourly_rate, service_radius_km, id_proof_type, id_proof_number,
                   background_check, verified_by, verified_date,
                   emergency_name, emergency_relation, emergency_phone,
                   is_available, status, created_at, updated_at
            FROM companion WHERE email = %s
        """, (email,))
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_companion_location(companion_id, latitude, longitude):
    """Existing companion ki location Google sign-in par refresh karta hai.
    Sirf lat/lng badalta hai - is_available (Show/Hide) ko touch nahi karta."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE companion SET latitude = %s, longitude = %s WHERE companion_id = %s",
            (latitude, longitude, companion_id)
        )
        conn.commit()
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_companion(data, photo_bytes=None, photo_type=None):
    """
    data: dict with keys matching the companion table columns
    (full_name, dob, gender, phone, bio, languages, skills,
     ngo_reference, email, google_id, city, latitude, longitude, service_type,
     hourly_rate, service_radius_km, id_proof_type, id_proof_number, emergency_name,
     emergency_relation, emergency_phone)
    photo_bytes/photo_type: raw uploaded image bytes + its mimetype (optional)
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO companion
               (full_name, dob, gender, phone, bio, photo, photo_type, languages, skills,
                ngo_reference, email, google_id, email_verified, city, latitude, longitude,
                service_type, hourly_rate, service_radius_km, id_proof_type, id_proof_number,
                emergency_name, emergency_relation, emergency_phone, consent_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                data["full_name"], data["dob"], data["gender"], data["phone"],
                data.get("bio"), photo_bytes, photo_type, data.get("languages"),
                data.get("skills"), data.get("ngo_reference"), data["email"],
                data.get("google_id"), True, data["city"], data.get("latitude"),
                data.get("longitude"), data.get("service_type"), data["hourly_rate"],
                data.get("service_radius_km") or 15,
                data["id_proof_type"], crypto_util.encrypt_id(data["id_proof_number"]),
                data.get("emergency_name"), data.get("emergency_relation"),
                data.get("emergency_phone"), data.get("consent_at"),
            )
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_companion_by_id(companion_id):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT companion_id, full_name, dob, gender, phone, bio,
                   (photo IS NOT NULL) AS has_photo, languages, skills, ngo_reference,
                   email, google_id, email_verified, city, latitude, longitude,
                   service_type, hourly_rate, service_radius_km, id_proof_type, id_proof_number,
                   background_check, verified_by, verified_date,
                   emergency_name, emergency_relation, emergency_phone,
                   is_available, status, created_at, updated_at
            FROM companion WHERE companion_id = %s
        """, (companion_id,))
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_companion_photo(companion_id):
    """Returns (photo_bytes, photo_type) or (None, None) if no photo / not found."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT photo, photo_type FROM companion WHERE companion_id = %s", (companion_id,))
        row = cursor.fetchone()
        if not row or row[0] is None:
            return None, None
        return row[0], row[1]
    finally:
        if conn and conn.is_connected():
            conn.close()


def list_companions(city=None, status=None):
    """Admin/listing use - saare companions, optional city/status filter ke saath."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT companion_id, full_name, dob, gender, phone, bio,
                   (photo IS NOT NULL) AS has_photo, languages, skills, ngo_reference,
                   email, google_id, email_verified, city, latitude, longitude,
                   service_type, hourly_rate, service_radius_km, id_proof_type, id_proof_number,
                   background_check, verified_by, verified_date,
                   emergency_name, emergency_relation, emergency_phone,
                   is_available, status, created_at, updated_at
            FROM companion WHERE 1=1
        """
        params = []
        if city:
            query += " AND city = %s"
            params.append(city)
        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------- COMPANION SEARCH ----------------
def find_nearby_companions(latitude, longitude, radius_km):
    """
    Companion tabhi dikhta hai jab CLIENT ke chune hue radius ke andar ho
    AND client companion ke apne service_radius_km ke andar ho.
    Dono taraf se dynamic - client jitna dhoondhna chahta hai, aur companion
    jitni door tak jaana chahta hai, dono ka intersection hi match banata hai.

    Availability ab do alag concepts hain, dono independent:
      1. companion.is_available - companion ka apna Show/Hide switch.
         Hide (FALSE) matlab wo search results mein aayega hi nahi.
         Show (TRUE) matlab wo dikhega - chahe abhi Busy ho ya Available.
      2. current_status ("Busy"/"Available") - sirf DISPLAY ke liye, real-time
         compute hota hai: agar companion ki AAJ ki koi Pending/Confirmed booking
         ka [start_time, end_time) window abhi NOW() ko cover kar raha hai to
         "Busy", warna "Available". Ye booking khatam hote hi NOW() aage badhne
         par khud-ba-khud "Available" ho jaata hai - koi cron/manual update
         ki zaroorat nahi. (1-hour buffer sirf naya booking banate waqt
         conflict-check ke liye use hota hai, display status ko affect nahi karta -
         is buffer ke dauraan companion apna Show/Hide switch normally use kar sakta hai.)
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT companion_id, full_name, city, service_type, hourly_rate,
                   service_radius_km,
                   (photo IS NOT NULL) AS has_photo, skills, background_check,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM booking b
                       WHERE b.companion_id = companion.companion_id
                         AND b.status IN ('Pending', 'Confirmed')
                         AND b.booking_date = %s
                         AND %s >= TIMESTAMP(b.booking_date, b.start_time)
                         AND %s <  TIMESTAMP(b.booking_date, b.end_time)
                   ) THEN 'Busy' ELSE 'Available' END AS current_status,
                   (SELECT ROUND(AVG(r.rating), 1) FROM booking r
                     WHERE r.companion_id = companion.companion_id AND r.rating IS NOT NULL) AS avg_rating,
                   (SELECT COUNT(r2.rating) FROM booking r2
                     WHERE r2.companion_id = companion.companion_id AND r2.rating IS NOT NULL) AS review_count,
                   ROUND(
                       6371 * ACOS(
                           COS(RADIANS(%s)) * COS(RADIANS(latitude)) *
                           COS(RADIANS(longitude) - RADIANS(%s)) +
                           SIN(RADIANS(%s)) * SIN(RADIANS(latitude))
                       ), 2
                   ) AS distance_km
            FROM companion
            WHERE status = 'Active'
              AND is_available = TRUE
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
            HAVING distance_km <= LEAST(%s, service_radius_km)
            ORDER BY distance_km ASC
            LIMIT 100
        """
        _now = now_local()
        cursor.execute(query, (_now.date(), _now, _now, latitude, longitude, latitude, radius_km))
        return _attach_shifts(cursor, cursor.fetchall())
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------- COMPANION AVAILABILITY (Show/Hide) ----------------
def set_companion_availability(companion_id, show, latitude=None, longitude=None):
    """
    Companion ka manual Show/Hide switch.
    Show (True) karte waqt current location (lat/lng) bhi turant update ho jaati hai,
    taaki customers ko accurate jagah par dikhe. Hide (False) sirf switch off karta
    hai, location ko touch nahi karta.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if show:
            cursor.execute(
                "UPDATE companion SET is_available = TRUE, latitude = %s, longitude = %s "
                "WHERE companion_id = %s",
                (latitude, longitude, companion_id)
            )
        else:
            cursor.execute(
                "UPDATE companion SET is_available = FALSE WHERE companion_id = %s",
                (companion_id,)
            )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_companion_status(companion_id):
    """Companion ke apne status-page ke liye: is_available switch + real-time Busy/Available."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT companion_id, full_name, is_available, status,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM booking b
                       WHERE b.companion_id = companion.companion_id
                         AND b.status IN ('Pending', 'Confirmed')
                         AND b.booking_date = %s
                         AND %s >= TIMESTAMP(b.booking_date, b.start_time)
                         AND %s <  TIMESTAMP(b.booking_date, b.end_time)
                   ) THEN 'Busy' ELSE 'Available' END AS current_status
            FROM companion WHERE companion_id = %s
        """, (now_local().date(), now_local(), now_local(), companion_id))
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------- BOOKING ----------------
def create_booking_atomic(companion_id, customer_id, booking_date, start_time, end_time):
    """
    Poori booking (validation + check + insert) ek hi transaction mein hoti hai,
    row-level lock (FOR UPDATE) ke saath - taaki do clients simultaneously ek hi companion
    ko double-book na kar paayein (race condition fix).
    Success par dict {booking_id, total_amount} return karta hai.
    Business-rule failure par ValueError raise karta hai (404/409/400 jaisa app.py map karega).
    """
    conn = None
    try:
        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT hourly_rate, is_available, status, full_name, phone FROM companion WHERE companion_id = %s FOR UPDATE",
            (companion_id,)
        )
        companion = cursor.fetchone()
        if not companion:
            conn.rollback()
            raise ValueError("not_found")
        if companion["status"] != "Active" or not companion["is_available"]:
            conn.rollback()
            raise ValueError("not_available")

        try:
            new_date = datetime.strptime(str(booking_date), "%Y-%m-%d").date()
            start_minutes = _to_minutes(start_time)
            end_minutes = _to_minutes(end_time)
        except ValueError:
            conn.rollback()
            raise ValueError("invalid_time")

        # Bookings sirf AAJ ke liye allowed hain - koi future-date booking nahi
        today = today_local()
        if new_date != today:
            conn.rollback()
            raise ValueError("date_not_today")

        duration_minutes = end_minutes - start_minutes
        if duration_minutes <= 0:
            conn.rollback()
            raise ValueError("invalid_time")
        hours = duration_minutes / 60

        # Start time already beet chuka ho (aaj ke andar) to booking allow nahi
        now = now_local()
        now_minutes = now.hour * 60 + now.minute + now.second / 60
        if start_minutes < now_minutes:
            conn.rollback()
            raise ValueError("time_in_past")

        new_start_dt = _combine_date_minutes(new_date, start_minutes)
        new_end_dt = _combine_date_minutes(new_date, end_minutes)
        buffer = timedelta(minutes=BOOKING_BUFFER_MINUTES)

        # Isi companion ki existing (cancelled chhodkar) bookings check karo -
        # 1 din aage/peeche bhi dekhte hain taaki midnight ke paas wale buffer
        # conflicts (jaise raat 11:30 ki booking aur agle din 12:30 ki booking) bhi pakde jaayein.
        # Companion row FOR UPDATE se pehle hi lock ho chuki hai, isliye ye check race-safe hai -
        # koi aur transaction isi companion ke liye tab tak wait karega jab tak ye commit/rollback na ho.
        cursor.execute(
            """SELECT booking_date, start_time, end_time FROM booking
               WHERE companion_id = %s AND status != 'Cancelled'
                 AND booking_date BETWEEN DATE_SUB(%s, INTERVAL 1 DAY) AND DATE_ADD(%s, INTERVAL 1 DAY)""",
            (companion_id, new_date, new_date)
        )
        for existing in cursor.fetchall():
            existing_start_dt = _combine_date_minutes(
                existing["booking_date"], _to_minutes(existing["start_time"])
            )
            existing_end_dt = _combine_date_minutes(
                existing["booking_date"], _to_minutes(existing["end_time"])
            )
            # Buffer-aware overlap check: buffer SIRF existing booking ke END ke baad
            # lagta hai (companion ko rest/travel ke liye), START se PEHLE koi buffer
            # nahi hai - matlab koi doosra customer existing slot shuru hone se theek
            # pehle tak (zero-gap bhi) apna slot book kar sakta hai.
            # e.g. existing 2-4pm hai to naya slot 4-5pm ke beech kabhi bhi start nahi ho sakta
            # (1hr buffer after), lekin 12-2pm jaisa slot (2pm se pehle khatam) bilkul valid hai.
            if new_start_dt < existing_end_dt + buffer and existing_start_dt < new_end_dt:
                conn.rollback()
                raise ValueError("time_conflict")

        rate = companion["hourly_rate"]
        total_amount = round(float(rate) * float(hours), 2)

        cursor.execute(
            """INSERT INTO booking
               (companion_id, customer_id, booking_date, start_time, end_time,
                rate_at_booking, total_amount, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'Pending')""",
            (companion_id, customer_id, booking_date, start_time, end_time, rate, total_amount)
        )
        booking_id = cursor.lastrowid

        # NOTE: companion.is_available yahan JAAN-BOOJH KAR update nahi hota.
        # Wo companion/admin ka manual switch hai. Is waqt companion "busy" hai ya
        # nahi - ye find_nearby_companions() mein NOW()-based real-time check se
        # dynamically decide hota hai, jo booking window khatam hote hi apne aap
        # available dikha deta hai, bina kisi extra update ke.

        conn.commit()
        # Booking hote hi companion ka number customer ko mil jaata hai (companion ko customer ka number accept ke baad)
        return {"booking_id": booking_id, "total_amount": total_amount,
                "companion_name": companion["full_name"], "companion_phone": companion["phone"]}
    finally:
        if conn and conn.is_connected():
            conn.close()


# =====================================================================
#  V2: bookings management, reviews, reports/SOS, notifications, profile,
#      account deactivate/delete, admin  (sab MySQL 8 compatible)
# =====================================================================
from datetime import date as _date, time as _time
from decimal import Decimal as _Decimal

BOOKING_ACCEPT_GRACE_MINUTES = 15  # start time ke itne minute baad tak companion accept kar sakta hai


def _clean(row):
    """JSON-safe dict: timedelta->'HH:MM', date/datetime->iso, Decimal->float, bytes hata do."""
    if row is None:
        return None
    out = {}
    for k, v in row.items():
        if isinstance(v, timedelta):
            mins = int(v.total_seconds() // 60)
            out[k] = f"{mins // 60:02d}:{mins % 60:02d}"
        elif isinstance(v, _time):
            out[k] = v.strftime("%H:%M")
        elif isinstance(v, datetime):
            out[k] = v.isoformat(sep=" ", timespec="seconds")
        elif isinstance(v, _date):
            out[k] = v.isoformat()
        elif isinstance(v, _Decimal):
            out[k] = float(v)
        elif isinstance(v, (bytes, bytearray)):
            continue
        else:
            out[k] = v
    return out


def _clean_rows(rows):
    return [_clean(r) for r in rows]


def _exec(sql, params=(), fetch=None, insert=False):
    """Chhota helper: fetch=None (write, rowcount), 'one', 'all'. insert=True -> lastrowid."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        if fetch == "one":
            return cursor.fetchone()
        if fetch == "all":
            return cursor.fetchall()
        conn.commit()
        return cursor.lastrowid if insert else cursor.rowcount
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------- AUTO EXPIRE / COMPLETE ----------------
def expire_stale_bookings():
    """
    - Pending booking jo start time + grace tak accept nahi hui -> Cancelled (cancelled_by='System')
    - Confirmed booking jiska end time nikal gaya -> Completed (+ commission ke baad payout_amount)
    Lazy chalta hai (list/nearby ke waqt), koi cron nahi chahiye.
    """
    now = now_local()
    grace_cut = now - timedelta(minutes=BOOKING_ACCEPT_GRACE_MINUTES)
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE booking SET status='Cancelled', cancelled_by='System'
               WHERE status='Pending' AND TIMESTAMP(booking_date, start_time) <= %s""", (grace_cut,))
        cursor.execute(
            """UPDATE booking SET status='Completed', completed_at=%s,
                      payout_amount = ROUND(total_amount * (100 - commission_pct) / 100, 2)
               WHERE status='Confirmed' AND TIMESTAMP(booking_date, end_time) <= %s""", (now, now))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            conn.close()


# ---------------- BOOKING LISTS ----------------
def list_bookings_for_customer(customer_id):
    rows = _exec(
        """SELECT b.booking_id, b.companion_id, b.booking_date, b.start_time, b.end_time,
                  b.total_amount, b.status, b.rating, b.review_comment, b.payment_status,
                  b.cancelled_by, b.created_at,
                  c.full_name AS other_name, c.city AS other_city, c.service_type,
                  CASE WHEN b.status IN ('Pending','Confirmed') THEN c.phone END AS other_phone
           FROM booking b JOIN companion c ON c.companion_id = b.companion_id
           WHERE b.customer_id = %s
           ORDER BY b.created_at DESC, b.booking_id DESC LIMIT 100""", (customer_id,), fetch="all")
    return _clean_rows(rows)


def list_bookings_for_companion(companion_id):
    rows = _exec(
        """SELECT b.booking_id, b.customer_id, b.booking_date, b.start_time, b.end_time,
                  b.total_amount, b.status, b.rating, b.review_comment, b.payment_status,
                  b.cancelled_by, b.created_at,
                  cu.full_name AS other_name, cu.city AS other_city,
                  CASE WHEN b.status = 'Confirmed' THEN cu.phone END AS other_phone
           FROM booking b JOIN customer cu ON cu.customer_id = b.customer_id
           WHERE b.companion_id = %s
           ORDER BY b.created_at DESC, b.booking_id DESC LIMIT 100""", (companion_id,), fetch="all")
    return _clean_rows(rows)


# ---------------- BOOKING ACTIONS ----------------
def change_booking_status(booking_id, actor_role, actor_id, action):
    """
    action: 'accept' | 'reject' (companion) | 'cancel' (customer: Pending/Confirmed, companion: Confirmed)
    Row-lock ke saath, race-safe. Success par updated booking dict; business-rule fail par ValueError(code).
    """
    conn = None
    try:
        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM booking WHERE booking_id = %s FOR UPDATE", (booking_id,))
        b = cursor.fetchone()

        def fail(code):
            conn.rollback()
            raise ValueError(code)

        if not b:
            fail("not_found")
        owner = b["companion_id"] if actor_role == "companion" else b["customer_id"]
        if owner != actor_id:
            fail("forbidden")

        status = b["status"]
        new_status, cancelled_by = None, None
        if action == "accept":
            if actor_role != "companion" or status != "Pending":
                fail("invalid_state")
            start_dt = _combine_date_minutes(b["booking_date"], _to_minutes(b["start_time"]))
            if start_dt + timedelta(minutes=BOOKING_ACCEPT_GRACE_MINUTES) <= now_local():
                fail("expired")
            new_status = "Confirmed"
        elif action == "reject":
            if actor_role != "companion" or status != "Pending":
                fail("invalid_state")
            new_status, cancelled_by = "Cancelled", "Companion"
        elif action == "cancel":
            allowed = ("Pending", "Confirmed") if actor_role == "customer" else ("Confirmed",)
            if status not in allowed:
                fail("invalid_state")
            new_status, cancelled_by = "Cancelled", actor_role.capitalize()
        else:
            fail("invalid_action")

        cursor.execute("UPDATE booking SET status = %s, cancelled_by = %s WHERE booking_id = %s",
                       (new_status, cancelled_by, booking_id))
        conn.commit()
        b["status"] = new_status
        return _clean(b)
    finally:
        if conn and conn.is_connected():
            conn.close()


def mark_booking_paid(companion_id, booking_id):
    """Companion confirm karta hai ki customer ne meeting par (cash/UPI) payment kar diya."""
    return _exec(
        """UPDATE booking SET payment_status = 'Paid'
           WHERE booking_id = %s AND companion_id = %s
             AND status IN ('Confirmed', 'Completed') AND payment_status = 'Unpaid'""",
        (booking_id, companion_id)) > 0


def add_review(customer_id, booking_id, rating, comment):
    b = _exec("SELECT customer_id, companion_id, status, rating FROM booking WHERE booking_id = %s",
              (booking_id,), fetch="one")
    if not b or b["customer_id"] != customer_id:
        raise ValueError("not_found")
    if b["status"] != "Completed":
        raise ValueError("not_completed")
    if b["rating"] is not None:
        raise ValueError("already_reviewed")
    _exec("UPDATE booking SET rating = %s, review_comment = %s WHERE booking_id = %s AND rating IS NULL",
          (rating, comment, booking_id))
    return b["companion_id"]


def get_companion_reviews(companion_id, limit=10):
    """Companion ki average rating + recent reviews (reviewer ka sirf pehla naam - privacy)."""
    summary = _exec(
        "SELECT ROUND(AVG(rating), 1) AS avg_rating, COUNT(rating) AS review_count "
        "FROM booking WHERE companion_id = %s AND rating IS NOT NULL", (companion_id,), fetch="one")
    rows = _exec(
        """SELECT b.rating, b.review_comment, b.booking_date, cu.full_name
           FROM booking b JOIN customer cu ON cu.customer_id = b.customer_id
           WHERE b.companion_id = %s AND b.rating IS NOT NULL
           ORDER BY b.booking_date DESC, b.booking_id DESC LIMIT %s""", (companion_id, int(limit)), fetch="all")
    reviews = [{"rating": r["rating"], "comment": r["review_comment"], "date": r["booking_date"],
                "name": (r["full_name"] or "Customer").split()[0]} for r in rows]
    return _clean({"avg_rating": summary["avg_rating"], "review_count": summary["review_count"] or 0,
                   "reviews": [_clean(r) for r in reviews]})


# ---------------- REPORTS / SOS ----------------
def create_report(booking_id, role, user_id, issue_type, description, is_sos=False, lat=None, lng=None):
    """Booking ka participant hi report kar sakta hai. Returns dict with ids for notifications."""
    b = _exec("SELECT booking_id, companion_id, customer_id FROM booking WHERE booking_id = %s",
              (booking_id,), fetch="one")
    if not b:
        raise ValueError("not_found")
    owner = b["companion_id"] if role == "companion" else b["customer_id"]
    if owner != user_id:
        raise ValueError("forbidden")
    report_id = _exec(
        """INSERT INTO report (booking_id, companion_id, customer_id, reported_by, issue_type,
                               description, is_sos, latitude, longitude)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (booking_id, b["companion_id"], b["customer_id"], role.capitalize(), issue_type,
         description, bool(is_sos), lat, lng), insert=True)
    return {"report_id": report_id, "companion_id": b["companion_id"], "customer_id": b["customer_id"]}


# ---------------- NOTIFICATIONS ----------------
def add_notification(user_type, user_id, message, link=None):
    _exec("INSERT INTO notification (user_type, user_id, message, link) VALUES (%s,%s,%s,%s)",
          (user_type, user_id, message, link))


def list_notifications(user_type, user_id, limit=30):
    rows = _exec(
        """SELECT notification_id, message, link, is_read, created_at FROM notification
           WHERE user_type = %s AND user_id = %s ORDER BY notification_id DESC LIMIT %s""",
        (user_type, user_id, limit), fetch="all")
    return _clean_rows(rows)


def count_unread_notifications(user_type, user_id):
    row = _exec("SELECT COUNT(*) AS n FROM notification WHERE user_type=%s AND user_id=%s AND is_read=FALSE",
                (user_type, user_id), fetch="one")
    return row["n"]


def mark_notifications_read(user_type, user_id):
    _exec("UPDATE notification SET is_read = TRUE WHERE user_type=%s AND user_id=%s AND is_read=FALSE",
          (user_type, user_id))


# ---------------- PROFILE EDIT ----------------
COMPANION_EDITABLE = ("bio", "hourly_rate", "service_radius_km", "languages", "skills", "service_type",
                      "emergency_name", "emergency_relation", "emergency_phone", "phone")
CUSTOMER_EDITABLE = ("full_name", "phone")


def _update_fields(table, id_col, row_id, fields, allowed):
    cols = [k for k in allowed if k in fields]
    if not cols:
        return 0
    sets = ", ".join(f"{c} = %s" for c in cols)
    return _exec(f"UPDATE {table} SET {sets} WHERE {id_col} = %s",
                 tuple(fields[c] for c in cols) + (row_id,))


def update_companion_profile(companion_id, fields):
    return _update_fields("companion", "companion_id", companion_id, fields, COMPANION_EDITABLE)


def update_customer_profile(customer_id, fields):
    return _update_fields("customer", "customer_id", customer_id, fields, CUSTOMER_EDITABLE)


# ---------------- ACCOUNT: DEACTIVATE / REACTIVATE / DELETE ----------------
def _role_cols(role):
    return ("companion", "companion_id", "Companion") if role == "companion" else ("customer", "customer_id", "Customer")


def has_active_bookings(role, user_id):
    _, col, _ = _role_cols(role)
    row = _exec(f"SELECT COUNT(*) AS n FROM booking WHERE {col} = %s AND status IN ('Pending','Confirmed')",
                (user_id,), fetch="one")
    return row["n"] > 0


def deactivate_account(role, user_id):
    table, col, _ = _role_cols(role)
    extra = ", is_available = FALSE" if role == "companion" else ""
    _exec(f"UPDATE {table} SET status = 'Deactivated'{extra} WHERE {col} = %s", (user_id,))


def reactivate_account(role, user_id):
    """Deactivated user dobara Google sign-in kare to wapas active (companion: pehle verified tha to Active)."""
    if role == "customer":
        _exec("UPDATE customer SET status='Active' WHERE customer_id=%s AND status='Deactivated'", (user_id,))
    else:
        _exec("""UPDATE companion SET status = IF(background_check='Passed','Active','Inactive')
                 WHERE companion_id=%s AND status='Deactivated'""", (user_id,))


def anonymize_account(role, user_id):
    """'Delete my data': personal info hata deta hai (booking history ke liye row bachti hai, par anonymous)."""
    table, col, utype = _role_cols(role)
    if role == "customer":
        _exec("""UPDATE customer SET full_name='Deleted user', phone=CONCAT('D', customer_id),
                    email=CONCAT('deleted-', customer_id, '@deleted.invalid'), google_id=NULL,
                    email_verified=FALSE, city=NULL, latitude=NULL, longitude=NULL, status='Deactivated'
                 WHERE customer_id=%s""", (user_id,))
    else:
        _exec("""UPDATE companion SET full_name='Deleted user', phone=CONCAT('D', companion_id),
                    email=CONCAT('deleted-', companion_id, '@deleted.invalid'), google_id=NULL,
                    email_verified=FALSE, bio=NULL, photo=NULL, photo_type=NULL, languages=NULL,
                    skills=NULL, ngo_reference=NULL, city='-', latitude=NULL, longitude=NULL,
                    id_proof_number='deleted', emergency_name=NULL, emergency_relation=NULL,
                    emergency_phone=NULL, is_available=FALSE, status='Deactivated'
                 WHERE companion_id=%s""", (user_id,))
    _exec("DELETE FROM notification WHERE user_type=%s AND user_id=%s", (utype, user_id))


# ---------------- ADMIN ----------------
def _cancel_active_bookings(role, user_id):
    """Suspend/blacklist par us user ki Pending/Confirmed bookings cancel. Returns [(booking_id, other_id)]."""
    _, col, _ = _role_cols(role)
    other = "customer_id" if role == "companion" else "companion_id"
    rows = _exec(f"SELECT booking_id, {other} AS other_id FROM booking WHERE {col}=%s AND status IN ('Pending','Confirmed')",
                 (user_id,), fetch="all")
    if rows:
        _exec(f"UPDATE booking SET status='Cancelled', cancelled_by='Admin' WHERE {col}=%s AND status IN ('Pending','Confirmed')",
              (user_id,))
    return [(r["booking_id"], r["other_id"]) for r in rows]


def admin_list_companions(status=None, limit=50, offset=0):
    where, params = "", []
    if status == "pending":
        where = "WHERE status = 'Inactive' AND background_check = 'Pending'"
    elif status:
        where = "WHERE status = %s"
        params.append(status)
    rows = _exec(
        f"""SELECT companion_id, full_name, dob, gender, phone, email, city, service_type, hourly_rate,
                   id_proof_type, id_proof_number, background_check, verified_by, verified_date,
                   emergency_name, emergency_phone, is_available, status, created_at,
                   (photo IS NOT NULL) AS has_photo
            FROM companion {where} ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        tuple(params) + (limit, offset), fetch="all")
    return _clean_rows(rows)


def admin_set_companion_status(companion_id, action, admin_name="admin"):
    """action: approve | reject | suspend | blacklist | reactivate. Returns list of cancelled (booking_id, customer_id)."""
    c = _exec("SELECT companion_id FROM companion WHERE companion_id=%s", (companion_id,), fetch="one")
    if not c:
        raise ValueError("not_found")
    cancelled = []
    if action == "approve":
        _exec("""UPDATE companion SET status='Active', background_check='Passed', verified_by=%s, verified_date=%s
                 WHERE companion_id=%s""", (admin_name, today_local(), companion_id))
    elif action == "reject":
        _exec("UPDATE companion SET status='Inactive', background_check='Failed', is_available=FALSE WHERE companion_id=%s",
              (companion_id,))
    elif action in ("suspend", "blacklist"):
        _exec("UPDATE companion SET status=%s, is_available=FALSE WHERE companion_id=%s",
              ("Suspended" if action == "suspend" else "Blacklisted", companion_id))
        cancelled = _cancel_active_bookings("companion", companion_id)
    elif action == "reactivate":
        _exec("""UPDATE companion SET status = IF(background_check='Passed','Active','Inactive')
                 WHERE companion_id=%s""", (companion_id,))
    else:
        raise ValueError("invalid_action")
    return cancelled


def admin_list_customers(limit=50, offset=0):
    rows = _exec("""SELECT customer_id, full_name, phone, email, city, status, created_at
                    FROM customer ORDER BY created_at DESC LIMIT %s OFFSET %s""", (limit, offset), fetch="all")
    return _clean_rows(rows)


def admin_set_customer_status(customer_id, action):
    c = _exec("SELECT customer_id FROM customer WHERE customer_id=%s", (customer_id,), fetch="one")
    if not c:
        raise ValueError("not_found")
    cancelled = []
    if action in ("suspend", "blacklist"):
        _exec("UPDATE customer SET status=%s WHERE customer_id=%s",
              ("Suspended" if action == "suspend" else "Blacklisted", customer_id))
        cancelled = _cancel_active_bookings("customer", customer_id)
    elif action == "reactivate":
        _exec("UPDATE customer SET status='Active' WHERE customer_id=%s", (customer_id,))
    else:
        raise ValueError("invalid_action")
    return cancelled


def admin_list_reports(status=None, limit=100):
    where, params = "", []
    if status:
        where = "WHERE r.status = %s"
        params.append(status)
    rows = _exec(
        f"""SELECT r.report_id, r.booking_id, r.reported_by, r.issue_type, r.description, r.status,
                   r.action_taken, r.is_sos, r.latitude, r.longitude, r.created_at,
                   r.companion_id, c.full_name AS companion_name, c.phone AS companion_phone,
                   r.customer_id, cu.full_name AS customer_name, cu.phone AS customer_phone
            FROM report r JOIN companion c ON c.companion_id = r.companion_id
                          JOIN customer cu ON cu.customer_id = r.customer_id
            {where}
            ORDER BY (r.status IN ('Open','Under Review')) DESC, r.is_sos DESC, r.created_at DESC
            LIMIT %s""", tuple(params) + (limit,), fetch="all")
    return _clean_rows(rows)


def admin_update_report(report_id, status, action_taken):
    return _exec("UPDATE report SET status=%s, action_taken=%s WHERE report_id=%s",
                 (status, action_taken, report_id)) >= 0


def admin_list_bookings(limit=100):
    rows = _exec(
        """SELECT b.booking_id, b.booking_date, b.start_time, b.end_time, b.total_amount, b.status,
                  b.payment_status, b.commission_pct, b.payout_amount, b.rating, b.cancelled_by,
                  c.full_name AS companion_name, cu.full_name AS customer_name
           FROM booking b JOIN companion c ON c.companion_id = b.companion_id
                          JOIN customer cu ON cu.customer_id = b.customer_id
           ORDER BY b.booking_id DESC LIMIT %s""", (limit,), fetch="all")
    return _clean_rows(rows)


def admin_stats():
    one = lambda sql, p=(): _exec(sql, p, fetch="one")["n"]
    return {
        "pending_companions": one("SELECT COUNT(*) AS n FROM companion WHERE status='Inactive' AND background_check='Pending'"),
        "active_companions": one("SELECT COUNT(*) AS n FROM companion WHERE status='Active'"),
        "customers": one("SELECT COUNT(*) AS n FROM customer"),
        "open_reports": one("SELECT COUNT(*) AS n FROM report WHERE status IN ('Open','Under Review')"),
        "open_sos": one("SELECT COUNT(*) AS n FROM report WHERE is_sos=TRUE AND status IN ('Open','Under Review')"),
        "bookings_today": one("SELECT COUNT(*) AS n FROM booking WHERE booking_date=%s", (today_local(),)),
    }
