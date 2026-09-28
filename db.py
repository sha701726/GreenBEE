"""
Database layer - saari MySQL queries yahan hain,
routes (app.py) sirf inhe call karenge.
"""

from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import Error
from config import Config

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


def get_connection():
    try:
        return mysql.connector.connect(**Config.DB_CONFIG)
    except Error as e:
        if e.errno == 1049:  # unknown database
            raise Error(
                f"Database '{Config.DB_CONFIG['database']}' exists nahi karta. "
                f"Pehle 'python init_db.py' chalao."
            )
        raise


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


def create_customer(name, phone, email, google_id, city, latitude, longitude):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO customer
               (full_name, phone, email, google_id, email_verified, city, latitude, longitude)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name, phone, email, google_id, True, city, latitude, longitude)
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
                emergency_name, emergency_relation, emergency_phone)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                data["full_name"], data["dob"], data["gender"], data["phone"],
                data.get("bio"), photo_bytes, photo_type, data.get("languages"),
                data.get("skills"), data.get("ngo_reference"), data["email"],
                data.get("google_id"), True, data["city"], data.get("latitude"),
                data.get("longitude"), data.get("service_type"), data["hourly_rate"],
                data.get("service_radius_km") or 15,
                data["id_proof_type"], data["id_proof_number"],
                data.get("emergency_name"), data.get("emergency_relation"),
                data.get("emergency_phone"),
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
                         AND b.booking_date = CURDATE()
                         AND NOW() >= TIMESTAMP(b.booking_date, b.start_time)
                         AND NOW() <  TIMESTAMP(b.booking_date, b.end_time)
                   ) THEN 'Busy' ELSE 'Available' END AS current_status,
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
        """
        cursor.execute(query, (latitude, longitude, latitude, radius_km))
        return cursor.fetchall()
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
                         AND b.booking_date = CURDATE()
                         AND NOW() >= TIMESTAMP(b.booking_date, b.start_time)
                         AND NOW() <  TIMESTAMP(b.booking_date, b.end_time)
                   ) THEN 'Busy' ELSE 'Available' END AS current_status
            FROM companion WHERE companion_id = %s
        """, (companion_id,))
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
            "SELECT hourly_rate, is_available, status FROM companion WHERE companion_id = %s FOR UPDATE",
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
        today = datetime.now().date()
        if new_date != today:
            conn.rollback()
            raise ValueError("date_not_today")

        duration_minutes = end_minutes - start_minutes
        if duration_minutes <= 0:
            conn.rollback()
            raise ValueError("invalid_time")
        hours = duration_minutes / 60

        # Start time already beet chuka ho (aaj ke andar) to booking allow nahi
        now = datetime.now()
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
        return {"booking_id": booking_id, "total_amount": total_amount}
    finally:
        if conn and conn.is_connected():
            conn.close()
