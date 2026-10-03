"""
rentafriend_db - FLASK APP ENTRY POINT
Run:
    pip install -r requirements.txt
    cp .env.example .env      (fill in your real values)
    python app.py             (database + tables auto-create ho jaate hain)
"""

import logging
import os
from datetime import datetime

from flask import Flask, request, jsonify, render_template, Response, session, redirect, url_for
from mysql.connector import Error
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
import db
import auth
import crypto_util
import notify
import ratelimit
from common import current_customer, current_companion, parse_coords, is_admin_request, db_error
from ratelimit import limited
import features
import admin as admin_panel
import init_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Database / tables jo nahi hain wo yahin ban jaate hain (pehle check, phir create) - alag setup step nahi chahiye.
init_db.main()

app = Flask(__name__)
app.config.from_object(Config)
if os.getenv("TRUST_PROXY", "").strip().lower() == "true":  # Render/nginx ke peeche sahi client IP + https
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.register_blueprint(features.bp)
app.register_blueprint(admin_panel.bp)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB - photo uploads ki safety limit

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}

if Config.SECRET_KEY == "dev-key" and Config.SESSION_COOKIE_SECURE:
    raise RuntimeError("Production me FLASK_SECRET_KEY set karna zaroori hai (dev-key se sessions forge ho sakte hain).")

if Config.SECRET_KEY == "dev-key":
    print("⚠️  FLASK_SECRET_KEY set nahi hai - dev-key use ho raha hai. "
          "Production mein .env / Render mein strong secret key zaroor set karo (sessions ke liye).")


@app.after_request
def add_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")  # personal data cache na ho
    return resp


@app.before_request
def api_guards():
    """CSRF: state-changing /api request par custom header zaroori (cross-site form/fetch ye set nahi kar sakta).
    Plus har IP par /api ke liye overall rate limit."""
    if not request.path.startswith("/api/"):
        return None
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get("X-Requested-With") != "GreenBEE":
        return jsonify({"error": "Invalid request"}), 403
    if not ratelimit.hit("api-global", 600, 300):
        return jsonify({"error": "Bahut zyada requests — thodi der baad try karo"}), 429
    return None


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("error.html", code=404, message="Ye page nahi mila."), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def server_error(e):
    logging.getLogger("greenbee").exception("Unhandled error")
    if request.path.startswith("/api/"):
        return jsonify({"error": "Server me dikkat aayi — thodi der baad try karo"}), 500
    return render_template("error.html", code=500, message="Kuch galat ho gaya. Thodi der baad try karo."), 500


@app.route("/healthz")
def healthz():
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception:
        logging.getLogger("greenbee").exception("Health check failed")
        return jsonify({"status": "db_down"}), 503


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", support_email=os.getenv("SUPPORT_EMAIL", ""))


@app.route("/terms")
def terms():
    return render_template("terms.html", support_email=os.getenv("SUPPORT_EMAIL", ""))


# ---------------- PAGE ----------------
@app.route("/")
def home():
    return render_template("index.html", google_client_id=Config.GOOGLE_CLIENT_ID)


@app.route("/join")
def join():
    return render_template("join.html", google_client_id=Config.GOOGLE_CLIENT_ID)


@app.route("/companion/status/<int:companion_id>")
def companion_status_page(companion_id):
    # Sirf logged-in companion apna hi status page dekh sakta hai
    logged_in_id = session.get("companion_id")
    if not logged_in_id:
        return redirect(url_for("home"))
    if logged_in_id != companion_id:
        return redirect(url_for("companion_status_page", companion_id=logged_in_id))
    return render_template("companion_status.html", companion_id=companion_id)


# ---------------- API: COMPANION REGISTRATION ----------------
@app.route("/api/companions", methods=["POST"])
@limited("register-companion", 6, 600)
def register_companion():
    # multipart/form-data - text fields request.form mein, photo request.files mein
    data = request.form.to_dict()

    token = data.get("credential")
    if not token:
        return jsonify({"error": "Google se email verify karna zaroori hai"}), 400

    google_data = auth.verify_google_token(token)
    if not google_data:
        return jsonify({"error": "Invalid or unverified Google account"}), 401

    required = ["full_name", "dob", "gender", "phone", "city",
                "latitude", "longitude", "hourly_rate", "id_proof_type", "id_proof_number"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    # 18+ aur Terms/Privacy consent zaroori
    if str(data.get("consent", "")).lower() not in ("true", "on", "1", "yes"):
        return jsonify({"error": "Terms aur Privacy Policy accept karna zaroori hai (aur aapki umar 18+ honi chahiye)"}), 400
    try:
        dob = datetime.strptime(data["dob"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Date of birth sahi format (YYYY-MM-DD) me do"}), 400
    today = db.today_local()
    if (today.year - dob.year) - ((today.month, today.day) < (dob.month, dob.day)) < 18:
        return jsonify({"error": "Companion banne ke liye umar kam se kam 18 saal honi chahiye"}), 400
    data["consent_at"] = db.now_local()

    # service_radius_km optional - companion apna coverage area set karta hai (default 15km)
    if data.get("service_radius_km"):
        try:
            radius_val = int(float(data["service_radius_km"]))
        except ValueError:
            return jsonify({"error": "service_radius_km must be a number"}), 400
        if not (1 <= radius_val <= 200):
            return jsonify({"error": "Service radius 1 aur 200 km ke beech hona chahiye"}), 400
        data["service_radius_km"] = radius_val
    else:
        data["service_radius_km"] = 15

    data["email"] = google_data["email"]
    data["google_id"] = google_data["google_id"]

    # photo optional - agar diya hai to validate karo
    photo_bytes, photo_type = None, None
    photo_file = request.files.get("photo")
    if photo_file and photo_file.filename:
        if photo_file.mimetype not in ALLOWED_PHOTO_TYPES:
            return jsonify({"error": "Photo JPEG, PNG ya WebP format mein honi chahiye"}), 400
        photo_bytes = photo_file.read()
        if not photo_bytes:
            return jsonify({"error": "Photo file khali hai"}), 400
        photo_type = photo_file.mimetype

    try:
        existing = db.find_companion_by_email(data["email"])
        if existing:
            return jsonify({"error": "Is email se pehle se ek companion registered hai"}), 409

        companion_id = db.create_companion(data, photo_bytes=photo_bytes, photo_type=photo_type)

        # Register karte hi companion logged-in ho jaata hai (Google se email already verify hai)
        session.permanent = True
        session["companion_id"] = companion_id
        return jsonify({"companion_id": companion_id, "message": "Registered — verification pending"})

    except Error as e:
        if e.errno == 1062:  # duplicate unique key (phone/email)
            return jsonify({"error": "Phone ya email pehle se use ho raha hai"}), 409
        return db_error(e)


@app.route("/api/companions/<int:companion_id>/photo", methods=["GET"])
def get_companion_photo(companion_id):
    try:
        photo_bytes, photo_type = db.get_companion_photo(companion_id)
        if not photo_bytes:
            return jsonify({"error": "No photo for this companion"}), 404
        return Response(photo_bytes, mimetype=photo_type or "image/jpeg")
    except Error as e:
        return db_error(e)


# ---------------- API: COMPANION AVAILABILITY (Show/Hide) ----------------
@app.route("/api/companions/<int:companion_id>/availability", methods=["POST"])
def set_companion_availability(companion_id):
    if session.get("companion_id") != companion_id or not current_companion():
        return jsonify({"error": "Please sign in as this companion"}), 401

    data = request.get_json(force=True)
    show = data.get("is_available")
    if show is None:
        return jsonify({"error": "is_available (true/false) bhejna zaroori hai"}), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    # Show karte waqt current location zaroori hai, taaki customers ko sahi jagah dikhe
    if show and (latitude is None or longitude is None):
        return jsonify({"error": "Availability ON karne ke liye current location (lat/lng) chahiye"}), 400

    try:
        updated = db.set_companion_availability(companion_id, bool(show), latitude, longitude)
        if not updated:
            return jsonify({"error": "Companion not found"}), 404
        return jsonify({"companion_id": companion_id, "is_available": bool(show)})
    except Error as e:
        return db_error(e)


@app.route("/api/companions/<int:companion_id>/status", methods=["GET"])
def get_companion_status(companion_id):
    if session.get("companion_id") != companion_id or not current_companion():
        return jsonify({"error": "Please sign in as this companion"}), 401

    try:
        result = db.get_companion_status(companion_id)
        if not result:
            return jsonify({"error": "Companion not found"}), 404
        return jsonify(result)
    except Error as e:
        return db_error(e)


@app.route("/api/companions/<int:companion_id>", methods=["GET"])
def get_companion(companion_id):
    # Phone, ID proof, exact location, emergency contact hai - sirf companion khud ya admin dekh sakta hai
    if session.get("companion_id") != companion_id and not is_admin_request():
        return jsonify({"error": "Not allowed"}), 403
    try:
        companion = db.get_companion_by_id(companion_id)
        if not companion:
            return jsonify({"error": "Companion not found"}), 404
        return jsonify(features._owner_view_companion(companion))
    except Error as e:
        return db_error(e)


@app.route("/api/companions", methods=["GET"])
def list_companions():
    if not is_admin_request():
        return jsonify({"error": "Not allowed"}), 403
    city = request.args.get("city")
    status = request.args.get("status")
    try:
        results = db.list_companions(city=city, status=status)
        for r in results:
            r["id_proof_number"] = crypto_util.decrypt_id(r.get("id_proof_number"))
            r.pop("google_id", None)
        return jsonify(results)
    except Error as e:
        return db_error(e)


# ---------------- API: GOOGLE AUTH ----------------
@app.route("/api/auth/google", methods=["POST"])
@limited("google-auth", 20, 300)
def google_auth():
    """
    Google Sign-In: pehle role detect karta hai (email se), phir:
      - Companion  -> companion ki location update + companion session   (role="companion")
      - Customer   -> customer ki location update + customer session     (role="customer")
      - New user   -> kuch save nahi hota, frontend role poochta hai      (role="new_user")
                      Customer choose kare -> yahi endpoint phone ke saath dobara hit hota hai
                      (purana signup flow, unchanged). Companion choose kare -> /join.
    """
    data = request.get_json(force=True)
    token = data.get("credential")
    phone = data.get("phone", "") or ""
    city = data.get("city", "")

    if not token:
        return jsonify({"error": "Google token missing"}), 400

    google_data = auth.verify_google_token(token)
    if not google_data:
        return jsonify({"error": "Invalid or unverified Google account"}), 401

    coords = parse_coords(data.get("latitude"), data.get("longitude"))
    email = google_data["email"]
    no_location = (jsonify({"error": "Location zaroori hai — please location access allow karo"}), 400)

    try:
        companion = db.find_companion_by_email(email)
        customer = (db.find_customer_by_google_id(google_data["google_id"])
                    or db.find_customer_by_email(email))
        customer_active = bool(customer) and customer["status"] == "Active"

        # ---- 1) Existing Companion: sirf location update, register/login dobara nahi ----
        if companion:
            if companion["status"] in ("Suspended", "Blacklisted"):
                return jsonify({"error": "Ye account active nahi hai"}), 403
            if not coords:
                return no_location
            db.update_companion_location(companion["companion_id"], coords[0], coords[1])
            if companion["status"] == "Deactivated":  # user ne account band kiya tha - sign-in par wapas
                db.reactivate_account("companion", companion["companion_id"])
            session.permanent = True
            session["companion_id"] = companion["companion_id"]
            # Same email customer bhi hai to uski location bhi sahi record mein update
            if customer_active:
                db.update_customer_location(customer["customer_id"], coords[0], coords[1])
                session["customer_id"] = customer["customer_id"]
            return jsonify({"role": "companion", "companion_id": companion["companion_id"],
                            "name": companion["full_name"]})

        # ---- 2) Existing Customer: location update + purana sign-in ----
        if customer:
            if customer["status"] == "Deactivated":
                db.reactivate_account("customer", customer["customer_id"])
                customer_active = True
            if not customer_active:
                return jsonify({"error": "Ye account active nahi hai"}), 403
            if not coords:
                return no_location
            db.update_customer_location(customer["customer_id"], coords[0], coords[1])
            session.permanent = True
            session["customer_id"] = customer["customer_id"]
            return jsonify({"role": "customer", "customer_id": customer["customer_id"],
                            "name": customer["full_name"]})

        # ---- 3) New user: role select karwao (phone abhi nahi aaya = pehla check-call) ----
        if not phone.strip():
            return jsonify({"role": "new_user", "email": email, "name": google_data["name"]})

        # ---- 4) "Continue as Customer": purana customer signup ----
        if not coords:
            return no_location
        if not data.get("consent"):
            return jsonify({"error": "Terms aur Privacy Policy accept karna zaroori hai (18+ ke liye)"}), 400
        customer_id = db.create_customer(
            google_data["name"], phone, email, google_data["google_id"],
            city, coords[0], coords[1], consent_at=db.now_local()
        )
        session.permanent = True
        session["customer_id"] = customer_id
        return jsonify({"role": "customer", "customer_id": customer_id, "name": google_data["name"]})

    except Error as e:
        return db_error(e)


# ---------------- API: SESSION (me / logout / customer location) ----------------
@app.route("/api/me", methods=["GET"])
def me():
    """Page load par frontend yahan se puchta hai - customer ka session valid hai ya nahi."""
    try:
        customer = current_customer()
    except Error as e:
        return db_error(e)
    if not customer:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "customer_id": customer["customer_id"], "name": customer["full_name"]})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role == "customer":
        session.pop("customer_id", None)
    elif role == "companion":
        session.pop("companion_id", None)
    else:
        session.clear()
    return jsonify({"logged_out": True})


@app.route("/api/customer/location", methods=["POST"])
@limited("customer-location", 60, 300)
def update_my_location():
    """Customer ki live location (frontend har 5 minute mein bhejta hai) DB mein save karta hai."""
    data = request.get_json(force=True)
    coords = parse_coords(data.get("latitude"), data.get("longitude"))
    if not coords:
        return jsonify({"error": "Valid latitude/longitude chahiye"}), 400

    try:
        customer = current_customer()
        if not customer:
            return jsonify({"error": "Please sign in first"}), 401
        db.update_customer_location(customer["customer_id"], coords[0], coords[1])
        return jsonify({"updated": True})
    except Error as e:
        return db_error(e)


# ---------------- API: NEARBY COMPANIONS ----------------
@app.route("/api/companions/nearby", methods=["GET"])
def nearby_companions():
    try:
        latitude = float(request.args.get("lat"))
        longitude = float(request.args.get("lng"))
        radius = float(request.args.get("radius", 4))  # default backend search radius = 4km
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lng are required numbers"}), 400

    if not (1 <= radius <= 500):
        return jsonify({"error": "Search radius 1 aur 500 km ke beech hona chahiye"}), 400

    try:
        db.expire_stale_bookings()
        results = db.find_nearby_companions(latitude, longitude, radius)
        return jsonify(results)
    except Error as e:
        return db_error(e)


# ---------------- API: CREATE BOOKING ----------------
@app.route("/api/bookings", methods=["POST"])
@limited("create-booking", 15, 300)
def create_booking():
    data = request.get_json(force=True)
    # customer_id ab client se nahi liya jaata - session se aata hai (koi doosre ke naam se book na kar sake)
    companion_id = data.get("companion_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    if not all([companion_id, start_time, end_time]):
        return jsonify({"error": "Missing fields"}), 400

    # Future booking option poori tarah hata di gayi hai - booking_date client se
    # accept hi nahi hoti, server hamesha aaj ki date use karta hai.
    booking_date = db.today_local().isoformat()

    try:
        customer = current_customer()
        if not customer:
            return jsonify({"error": "Please sign in first"}), 401

        result = db.create_booking_atomic(
            companion_id, customer["customer_id"], booking_date, start_time, end_time
        )
        try:  # companion ko naye request ki notification (fail ho to booking par asar nahi)
            comp = db.get_companion_by_id(int(companion_id))
            notify.notify("Companion", int(companion_id),
                          f"Nayi booking request: {customer['full_name']} ({str(start_time)[:5]}-{str(end_time)[:5]}, "
                          f"₹{result['total_amount']}). Dashboard me accept ya decline karo.",
                          "/dashboard", comp and comp.get("email"))
        except Exception:
            logging.getLogger("greenbee").exception("Booking notification failed")
        return jsonify(result)

    except ValueError as e:
        error_map = {
            "not_found": ("Companion not found", 404),
            "not_available": ("Companion abhi available nahi hai", 409),
            "invalid_time": ("End time, start time ke baad hona chahiye", 400),
            "date_not_today": ("Bookings sirf aaj ke liye allowed hain", 400),
            "time_in_past": ("Ye start time already beet chuka hai", 400),
            "time_conflict": ("Companion ki is waqt (1hr gap ke saath) pehle se booking hai", 409),
        }
        message, status_code = error_map.get(str(e), ("Booking failed", 400))
        return jsonify({"error": message}), status_code

    except Error as e:
        return db_error(e)


@app.errorhandler(413)
def file_too_large(e):
    return jsonify({"error": "Photo 5 MB se badi hai — chhoti file try karo"}), 413


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").strip().lower() == "true")
