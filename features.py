"""
Booking management (accept/reject/cancel), contact reveal, payment-received, reviews, reports + SOS,
notifications, profile edit, account deactivate/delete, dashboard page.
"""
import re

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from mysql.connector import Error

import db
import notify
from common import current_companion, current_customer, db_error, parse_coords
from ratelimit import limited

bp = Blueprint("features", __name__)

ISSUE_TYPES = ("Harassment", "Unsafe behaviour", "No-show", "Payment issue", "Fake profile", "Other", "SOS")
PHONE_RE = re.compile(r"^[0-9+\-\s]{7,15}$")


def actor(role):
    """(user_dict, id) for 'customer'/'companion' ya (None, None)."""
    if role == "customer":
        u = current_customer()
        return (u, u["customer_id"]) if u else (None, None)
    if role == "companion":
        u = current_companion()
        return (u, u["companion_id"]) if u else (None, None)
    return None, None


def need_actor(role):
    user, uid = actor(role)
    if not user:
        return None, None, (jsonify({"error": "Please sign in first"}), 401)
    return user, uid, None


def _name(user):
    return user.get("full_name") or "Someone"


# ---------------- PAGE ----------------
@bp.route("/dashboard")
def dashboard_page():
    if not (session.get("customer_id") or session.get("companion_id")):
        return redirect(url_for("home"))
    return render_template("dashboard.html")


@bp.route("/api/dashboard/me")
def dashboard_me():
    try:
        roles = []
        if current_companion():
            roles.append("companion")
        if current_customer():
            roles.append("customer")
        if not roles:
            return jsonify({"error": "Please sign in first"}), 401
        return jsonify({"roles": roles})
    except Error as e:
        return db_error(e)


# ---------------- BOOKINGS LIST ----------------
@bp.route("/api/my/bookings")
def my_bookings():
    role = request.args.get("role")
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        db.expire_stale_bookings()
        rows = (db.list_bookings_for_customer(uid) if role == "customer"
                else db.list_bookings_for_companion(uid))
        return jsonify(rows)
    except Error as e:
        return db_error(e)


# ---------------- RATINGS ----------------
@bp.route("/api/companions/<int:companion_id>/reviews")
def companion_reviews(companion_id):
    """Public: companion ki average rating + recent reviews (search card ke 'Reviews' button ke liye)."""
    try:
        return jsonify(db.get_companion_reviews(companion_id))
    except Error as e:
        return db_error(e)


@bp.route("/api/my/rating")
def my_rating():
    """Logged-in companion ki apni rating summary (dashboard ke liye)."""
    user, uid, err = need_actor("companion")
    if err:
        return err
    try:
        return jsonify(db.get_companion_reviews(uid, limit=5))
    except Error as e:
        return db_error(e)


# ---------------- BOOKING ACTIONS ----------------
@bp.route("/api/bookings/<int:booking_id>/action", methods=["POST"])
@limited("booking-action", 30, 60)
def booking_action(booking_id):
    data = request.get_json(silent=True) or {}
    role, action = data.get("role"), data.get("action")
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        db.expire_stale_bookings()
        b = db.change_booking_status(booking_id, role, uid, action)
    except ValueError as e:
        msgs = {
            "not_found": ("Booking nahi mili", 404),
            "forbidden": ("Ye booking aapki nahi hai", 403),
            "invalid_state": ("Is booking par ab ye action possible nahi hai", 409),
            "expired": ("Request expire ho chuki hai", 409),
            "invalid_action": ("Invalid action", 400),
        }
        m, code = msgs.get(str(e), ("Action failed", 400))
        return jsonify({"error": m}), code
    except Error as e:
        return db_error(e)

    # Doosre party ko notification
    when = f"{b['booking_date']} {str(b['start_time'])[:5]}-{str(b['end_time'])[:5]}"
    try:
        if role == "companion":
            cust = db.get_customer_by_id(b["customer_id"])
            if action == "accept":
                msg = f"{_name(user)} ne aapki booking ({when}) accept kar li. Booking page par unka contact number dekho."
            elif action == "reject":
                msg = f"{_name(user)} ne aapki booking ({when}) decline kar di."
            else:
                msg = f"{_name(user)} ne confirmed booking ({when}) cancel kar di."
            notify.notify("Customer", b["customer_id"], msg, "/dashboard", cust and cust.get("email"))
        else:
            comp = db.get_companion_by_id(b["companion_id"])
            notify.notify("Companion", b["companion_id"],
                          f"{_name(user)} ne booking ({when}) cancel kar di.", "/dashboard", comp and comp.get("email"))
    except Error:
        pass
    return jsonify({"booking_id": booking_id, "status": b["status"]})


@bp.route("/api/bookings/<int:booking_id>/paid", methods=["POST"])
@limited("booking-paid", 30, 60)
def booking_paid(booking_id):
    user, uid, err = need_actor("companion")
    if err:
        return err
    try:
        if not db.mark_booking_paid(uid, booking_id):
            return jsonify({"error": "Payment mark nahi ho saka (booking confirmed/completed honi chahiye)"}), 409
        return jsonify({"booking_id": booking_id, "payment_status": "Paid"})
    except Error as e:
        return db_error(e)


@bp.route("/api/bookings/<int:booking_id>/review", methods=["POST"])
@limited("review", 20, 600)
def booking_review(booking_id):
    user, uid, err = need_actor("customer")
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        return jsonify({"error": "Rating 1 se 5 ke beech chahiye"}), 400
    if not 1 <= rating <= 5:
        return jsonify({"error": "Rating 1 se 5 ke beech chahiye"}), 400
    comment = (data.get("comment") or "").strip()[:500] or None
    try:
        db.expire_stale_bookings()
        companion_id = db.add_review(uid, booking_id, rating, comment)
    except ValueError as e:
        msgs = {"not_found": ("Booking nahi mili", 404),
                "not_completed": ("Review sirf completed booking par ho sakta hai", 409),
                "already_reviewed": ("Aap is booking ka review pehle de chuke ho", 409)}
        m, code = msgs.get(str(e), ("Review failed", 400))
        return jsonify({"error": m}), code
    except Error as e:
        return db_error(e)
    notify.notify("Companion", companion_id, f"{_name(user)} ne aapko {rating}★ rating di.", "/dashboard")
    return jsonify({"booking_id": booking_id, "rating": rating})


# ---------------- REPORT / SOS ----------------
@bp.route("/api/reports", methods=["POST"])
@limited("report", 8, 600)
def create_report():
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        booking_id = int(data.get("booking_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "booking_id chahiye"}), 400

    is_sos = bool(data.get("sos"))
    issue = "SOS" if is_sos else (data.get("issue_type") or "")
    if issue not in ISSUE_TYPES:
        return jsonify({"error": "Valid issue type chuno"}), 400
    description = (data.get("description") or "").strip()[:1000] or None
    coords = parse_coords(data.get("latitude"), data.get("longitude")) or (None, None)

    try:
        if is_sos:
            db.expire_stale_bookings()
            rows = (db.list_bookings_for_customer(uid) if role == "customer" else db.list_bookings_for_companion(uid))
            if not any(r["booking_id"] == booking_id and r["status"] == "Confirmed" for r in rows):
                return jsonify({"error": "SOS sirf active (confirmed) booking par bheja ja sakta hai"}), 409
        info = db.create_report(booking_id, role, uid, issue, description, is_sos, coords[0], coords[1])
    except ValueError as e:
        m, code = ({"not_found": ("Booking nahi mili", 404), "forbidden": ("Ye booking aapki nahi hai", 403)}
                   .get(str(e), ("Report failed", 400)))
        return jsonify({"error": m}), code
    except Error as e:
        return db_error(e)

    where = f" Location: https://maps.google.com/?q={coords[0]},{coords[1]}" if coords[0] is not None else ""
    notify.notify_admin(
        ("🚨 SOS" if is_sos else "New report") + f" — booking #{booking_id}",
        f"{issue} by {role} ({_name(user)}). Booking #{booking_id}, report #{info['report_id']}.{where}\n{description or ''}")
    return jsonify({"report_id": info["report_id"], "sos": is_sos, "emergency_number": "112"})


# ---------------- NOTIFICATIONS ----------------
@bp.route("/api/notifications")
def notifications():
    role = request.args.get("role")
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        utype = role.capitalize()
        return jsonify({"items": db.list_notifications(utype, uid),
                        "unread": db.count_unread_notifications(utype, uid)})
    except Error as e:
        return db_error(e)


@bp.route("/api/notifications/read", methods=["POST"])
def notifications_read():
    role = (request.get_json(silent=True) or {}).get("role")
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        db.mark_notifications_read(role.capitalize(), uid)
        return jsonify({"ok": True})
    except Error as e:
        return db_error(e)


# ---------------- PROFILE ----------------
def _owner_view_companion(c):
    """Companion ko apna profile dikhate waqt: ID proof masked, google_id hata do."""
    import crypto_util
    c = db._clean(c)
    c["id_proof_number"] = crypto_util.mask_id(c.get("id_proof_number"))
    c.pop("google_id", None)
    return c


@bp.route("/api/profile")
def get_profile():
    role = request.args.get("role")
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        if role == "companion":
            return jsonify(_owner_view_companion(db.get_companion_by_id(uid)))
        c = db._clean(db.get_customer_by_id(uid))
        c.pop("google_id", None)
        return jsonify(c)
    except Error as e:
        return db_error(e)


def _validate_profile(role, raw):
    """Returns (clean_fields, error)."""
    out = {}
    def text(key, maxlen):
        if key in raw:
            v = (raw.get(key) or "").strip()
            out[key] = v[:maxlen] or None

    if "phone" in raw:
        phone = (raw.get("phone") or "").strip()
        if not PHONE_RE.match(phone):
            return None, "Phone number valid nahi hai"
        out["phone"] = phone
    if role == "customer":
        if "full_name" in raw:
            name = (raw.get("full_name") or "").strip()
            if len(name) < 2:
                return None, "Naam kam se kam 2 characters ka ho"
            out["full_name"] = name[:100]
        return out, None

    text("bio", 1000); text("languages", 200); text("skills", 200); text("service_type", 100)
    text("emergency_name", 100); text("emergency_relation", 50)
    if "emergency_phone" in raw:
        ep = (raw.get("emergency_phone") or "").strip()
        if ep and not PHONE_RE.match(ep):
            return None, "Emergency phone valid nahi hai"
        out["emergency_phone"] = ep or None
    if "hourly_rate" in raw:
        try:
            rate = float(raw["hourly_rate"])
        except (TypeError, ValueError):
            return None, "Hourly rate number hona chahiye"
        if not 0 < rate <= 100000:
            return None, "Hourly rate valid range me nahi hai"
        out["hourly_rate"] = rate
    if "service_radius_km" in raw:
        try:
            radius = int(float(raw["service_radius_km"]))
        except (TypeError, ValueError):
            return None, "Service radius number hona chahiye"
        if not 1 <= radius <= 200:
            return None, "Service radius 1 aur 200 km ke beech hona chahiye"
        out["service_radius_km"] = radius
    return out, None


@bp.route("/api/profile/update", methods=["POST"])
@limited("profile", 20, 600)
def update_profile():
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    user, uid, err = need_actor(role)
    if err:
        return err
    fields, verr = _validate_profile(role, data.get("fields") or {})
    if verr:
        return jsonify({"error": verr}), 400
    if not fields:
        return jsonify({"error": "Kuch badla nahi gaya"}), 400
    try:
        (db.update_companion_profile if role == "companion" else db.update_customer_profile)(uid, fields)
        return jsonify({"updated": True})
    except Error as e:
        if e.errno == 1062:
            return jsonify({"error": "Ye phone number pehle se use ho raha hai"}), 409
        return db_error(e)


# ---------------- ACCOUNT: DEACTIVATE / DELETE ----------------
def _close_account(role, delete):
    user, uid, err = need_actor(role)
    if err:
        return err
    try:
        db.expire_stale_bookings()
        if db.has_active_bookings(role, uid):
            return jsonify({"error": "Pehle apni pending/confirmed bookings cancel ya complete karo"}), 409
        if delete:
            db.anonymize_account(role, uid)
        else:
            db.deactivate_account(role, uid)
    except Error as e:
        return db_error(e)
    session.pop("customer_id" if role == "customer" else "companion_id", None)
    return jsonify({"done": True, "deleted": delete})


@bp.route("/api/account/deactivate", methods=["POST"])
@limited("account", 5, 600)
def deactivate_account():
    return _close_account((request.get_json(silent=True) or {}).get("role"), delete=False)


@bp.route("/api/account/delete", methods=["POST"])
@limited("account", 5, 600)
def delete_account():
    data = request.get_json(silent=True) or {}
    if data.get("confirm") != "DELETE":
        return jsonify({"error": "Confirm karne ke liye DELETE likho"}), 400
    return _close_account(data.get("role"), delete=True)
