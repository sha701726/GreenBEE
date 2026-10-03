"""Shared helpers (app.py aur blueprints dono use karte hain - circular import se bachne ke liye alag file)."""
import hmac
import logging
import os

from flask import jsonify, request, session

import db

log = logging.getLogger("greenbee")


def parse_coords(latitude, longitude):
    """(lat, lng) floats return karta hai, invalid/missing par None."""
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def db_error(e):
    """DB error ki detail client ko nahi bhejte (info leak) - log mein jaati hai."""
    log.error("Database error: %s", e, exc_info=True)
    return jsonify({"error": "Server me dikkat aayi — thodi der baad try karo"}), 500


def current_customer():
    """Session se logged-in Active customer (dict) ya None."""
    customer_id = session.get("customer_id")
    if not customer_id:
        return None
    customer = db.get_customer_by_id(customer_id)
    if not customer or customer["status"] != "Active":
        session.pop("customer_id", None)
        return None
    return customer


def current_companion():
    """Session se logged-in companion (id, full_name, status ...) ya None. Suspended/Blacklisted/Deactivated block."""
    companion_id = session.get("companion_id")
    if not companion_id:
        return None
    companion = db.get_companion_status(companion_id)
    if not companion or companion["status"] in ("Suspended", "Blacklisted", "Deactivated"):
        session.pop("companion_id", None)
        return None
    return companion


def is_admin_request():
    """Admin: ya to login-session (is_admin) ya X-Admin-Key header (ADMIN_API_KEY env). Env na ho to band."""
    if session.get("is_admin"):
        return True
    expected = os.getenv("ADMIN_API_KEY", "")
    given = request.headers.get("X-Admin-Key", "")
    return bool(expected) and hmac.compare_digest(expected, given)
