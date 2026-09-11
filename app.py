"""
rentafriend_db - FLASK APP ENTRY POINT
Run:
    pip install -r requirements.txt
    cp .env.example .env      (fill in your real values)
    python app.py
"""

from datetime import date

from flask import Flask, request, jsonify, render_template, Response
from mysql.connector import Error

from config import Config
import db
import auth

app = Flask(__name__)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB - photo uploads ki safety limit

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ---------------- PAGE ----------------
@app.route("/")
def home():
    return render_template("index.html", google_client_id=Config.GOOGLE_CLIENT_ID)


@app.route("/join")
def join():
    return render_template("join.html", google_client_id=Config.GOOGLE_CLIENT_ID)


@app.route("/companion/status/<int:companion_id>")
def companion_status_page(companion_id):
    return render_template("companion_status.html", companion_id=companion_id)


# ---------------- API: COMPANION REGISTRATION ----------------
@app.route("/api/companions", methods=["POST"])
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
        return jsonify({"companion_id": companion_id, "message": "Registered — verification pending"})

    except Error as e:
        if e.errno == 1062:  # duplicate unique key (phone/email)
            return jsonify({"error": "Phone ya email pehle se use ho raha hai"}), 409
        return jsonify({"error": str(e)}), 500


@app.route("/api/companions/<int:companion_id>/photo", methods=["GET"])
def get_companion_photo(companion_id):
    try:
        photo_bytes, photo_type = db.get_companion_photo(companion_id)
        if not photo_bytes:
            return jsonify({"error": "No photo for this companion"}), 404
        return Response(photo_bytes, mimetype=photo_type or "image/jpeg")
    except Error as e:
        return jsonify({"error": str(e)}), 500


# ---------------- API: COMPANION AVAILABILITY (Show/Hide) ----------------
@app.route("/api/companions/<int:companion_id>/availability", methods=["POST"])
def set_companion_availability(companion_id):
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/companions/<int:companion_id>/status", methods=["GET"])
def get_companion_status(companion_id):
    try:
        result = db.get_companion_status(companion_id)
        if not result:
            return jsonify({"error": "Companion not found"}), 404
        return jsonify(result)
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/companions/<int:companion_id>", methods=["GET"])
def get_companion(companion_id):
    try:
        companion = db.get_companion_by_id(companion_id)
        if not companion:
            return jsonify({"error": "Companion not found"}), 404
        return jsonify(companion)
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/companions", methods=["GET"])
def list_companions():
    city = request.args.get("city")
    status = request.args.get("status")
    try:
        results = db.list_companions(city=city, status=status)
        return jsonify(results)
    except Error as e:
        return jsonify({"error": str(e)}), 500


# ---------------- API: GOOGLE AUTH ----------------
@app.route("/api/auth/google", methods=["POST"])
def google_auth():
    data = request.get_json(force=True)
    token = data.get("credential")
    phone = data.get("phone", "")
    city = data.get("city", "")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not token:
        return jsonify({"error": "Google token missing"}), 400

    google_data = auth.verify_google_token(token)
    if not google_data:
        return jsonify({"error": "Invalid or unverified Google account"}), 401

    try:
        existing = db.find_customer_by_google_id(google_data["google_id"])
        if existing:
            return jsonify({"customer_id": existing["customer_id"], "name": existing["full_name"]})

        customer_id = db.create_customer(
            google_data["name"], phone, google_data["email"], google_data["google_id"],
            city, latitude, longitude
        )
        return jsonify({"customer_id": customer_id, "name": google_data["name"]})

    except Error as e:
        return jsonify({"error": str(e)}), 500


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
        results = db.find_nearby_companions(latitude, longitude, radius)
        return jsonify(results)
    except Error as e:
        return jsonify({"error": str(e)}), 500


# ---------------- API: CREATE BOOKING ----------------
@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(force=True)
    customer_id = data.get("customer_id")
    companion_id = data.get("companion_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    if not all([customer_id, companion_id, start_time, end_time]):
        return jsonify({"error": "Missing fields"}), 400

    # Future booking option poori tarah hata di gayi hai - booking_date client se
    # accept hi nahi hoti, server hamesha aaj ki date use karta hai.
    booking_date = date.today().isoformat()

    try:
        result = db.create_booking_atomic(
            companion_id, customer_id, booking_date, start_time, end_time
        )
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
        return jsonify({"error": str(e)}), 500


def check_database_ready():
    """App start hone se pehle check karo database bana hua hai ya nahi."""
    try:
        conn = db.get_connection()
        conn.close()
    except Error as e:
        print(f"\n❌ {e}\n")
        raise SystemExit(1)


@app.errorhandler(413)
def file_too_large(e):
    return jsonify({"error": "Photo 5 MB se badi hai — chhoti file try karo"}), 413


if __name__ == "__main__":
    check_database_ready()
    app.run(debug=True)
