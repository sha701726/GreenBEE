"""
Admin panel (/admin). Login: ADMIN_API_KEY (env) se. Env set na ho to admin band rehta hai.
Companion verify/approve, suspend, customers, reports + SOS, bookings overview.
"""
import hmac
import os

from flask import Blueprint, jsonify, render_template, request, session
from mysql.connector import Error

import crypto_util
import db
import notify
from common import db_error, is_admin_request
from ratelimit import limited

bp = Blueprint("admin", __name__)


def admin_only(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        if not is_admin_request():
            return jsonify({"error": "Admin login chahiye"}), 401
        return fn(*a, **kw)
    return wrapper


@bp.route("/admin")
def admin_page():
    return render_template("admin.html")


@bp.route("/api/admin/login", methods=["POST"])
@limited("admin-login", 5, 300)
def admin_login():
    expected = os.getenv("ADMIN_API_KEY", "")
    given = (request.get_json(silent=True) or {}).get("key", "")
    if not expected or not hmac.compare_digest(expected, str(given)):
        return jsonify({"error": "Galat admin key"}), 401
    session["is_admin"] = True  # non-permanent: browser band hote hi logout
    return jsonify({"ok": True})


@bp.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})


@bp.route("/api/admin/stats")
@admin_only
def stats():
    try:
        return jsonify(db.admin_stats())
    except Error as e:
        return db_error(e)


@bp.route("/api/admin/companions")
@admin_only
def companions():
    status = request.args.get("status") or None
    if status not in (None, "pending", "Active", "Inactive", "Suspended", "Blacklisted", "Deactivated"):
        return jsonify({"error": "Invalid status filter"}), 400
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        rows = db.admin_list_companions(status, limit, offset)
        for r in rows:  # admin ko verification ke liye asli ID number dikhta hai
            r["id_proof_number"] = crypto_util.decrypt_id(r["id_proof_number"])
        return jsonify(rows)
    except (ValueError, Error) as e:
        return db_error(e) if isinstance(e, Error) else (jsonify({"error": "Invalid limit/offset"}), 400)


@bp.route("/api/admin/companions/<int:companion_id>/<action>", methods=["POST"])
@admin_only
def companion_action(companion_id, action):
    try:
        cancelled = db.admin_set_companion_status(companion_id, action)
    except ValueError as e:
        return jsonify({"error": "Companion nahi mila" if str(e) == "not_found" else "Invalid action"}), 404 if str(e) == "not_found" else 400
    except Error as e:
        return db_error(e)
    msgs = {"approve": "Aapka profile verify ho gaya hai — ab 'Show my availability' on karke bookings le sakte ho.",
            "reject": "Aapka verification approve nahi hua. Details check karke dobara contact karo.",
            "suspend": "Aapka account suspend kar diya gaya hai.",
            "blacklist": "Aapka account band kar diya gaya hai.",
            "reactivate": "Aapka account dobara active kar diya gaya hai."}
    notify.notify("Companion", companion_id, msgs[action], "/dashboard")
    for _bid, customer_id in cancelled:
        notify.notify("Customer", customer_id, "Companion available nahi raha, aapki booking cancel ho gayi.", "/dashboard")
    return jsonify({"companion_id": companion_id, "action": action, "cancelled_bookings": len(cancelled)})


@bp.route("/api/admin/customers")
@admin_only
def customers():
    try:
        return jsonify(db.admin_list_customers())
    except Error as e:
        return db_error(e)


@bp.route("/api/admin/customers/<int:customer_id>/<action>", methods=["POST"])
@admin_only
def customer_action(customer_id, action):
    try:
        cancelled = db.admin_set_customer_status(customer_id, action)
    except ValueError as e:
        return (jsonify({"error": "Customer nahi mila"}), 404) if str(e) == "not_found" else (jsonify({"error": "Invalid action"}), 400)
    except Error as e:
        return db_error(e)
    for _bid, companion_id in cancelled:
        notify.notify("Companion", companion_id, "Customer ne booking cancel ki (account action).", "/dashboard")
    return jsonify({"customer_id": customer_id, "action": action, "cancelled_bookings": len(cancelled)})


@bp.route("/api/admin/reports")
@admin_only
def reports():
    status = request.args.get("status") or None
    if status not in (None, "Open", "Under Review", "Resolved", "Dismissed"):
        return jsonify({"error": "Invalid status filter"}), 400
    try:
        return jsonify(db.admin_list_reports(status))
    except Error as e:
        return db_error(e)


@bp.route("/api/admin/reports/<int:report_id>", methods=["POST"])
@admin_only
def update_report(report_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("Open", "Under Review", "Resolved", "Dismissed"):
        return jsonify({"error": "Invalid status"}), 400
    try:
        db.admin_update_report(report_id, status, (data.get("action_taken") or "").strip()[:1000] or None)
        return jsonify({"report_id": report_id, "status": status})
    except Error as e:
        return db_error(e)


@bp.route("/api/admin/bookings")
@admin_only
def bookings():
    try:
        db.expire_stale_bookings()
        return jsonify(db.admin_list_bookings())
    except Error as e:
        return db_error(e)
