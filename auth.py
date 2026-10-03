"""
Google Sign-In token verification.
"""

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from config import Config

# Chhoti clock-skew tolerance (seconds) - system clock 1-2 minute idhar-udhar hone par
# bhi verification fail na ho. Asli fix hamesha system clock sync karna hai (neeche dekho),
# ye sirf ek safety margin hai.
CLOCK_SKEW_TOLERANCE_SECONDS = 60


def verify_google_token(token):
    """
    Returns dict {email, google_id, name} on success, None on failure.
    Koi bhi verification error (invalid token, expired, network issue) -> None,
    caller ko clean 401 milta hai, 500 crash nahi.
    Real reason server console mein print hoti hai (client ko generic message hi jaata hai,
    security ke liye) - agar "Invalid or unverified Google account" baar baar aa raha hai
    to yahan ka console output check karo: mostly wrong GOOGLE_CLIENT_ID (.env), Google Cloud
    Console mein authorized origin missing, ya system clock ka drift ("Token used too early").
    """
    if not Config.GOOGLE_CLIENT_ID:
        print("❌ Google verify failed: GOOGLE_CLIENT_ID .env mein set nahi hai")
        return None

    try:
        info = id_token.verify_oauth2_token(
            token, google_requests.Request(), Config.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=CLOCK_SKEW_TOLERANCE_SECONDS
        )
    except Exception as e:
        print(f"❌ Google token verify failed: {e}")
        if "used too early" in str(e) or "clock" in str(e).lower():
            print("   ⏰ Ye system clock drift hai - apne computer/server ka time+date")
            print("      'sync automatically' / NTP ke through set karo aur retry karo.")
        return None

    if not info.get("email_verified"):
        print("❌ Google verify failed: email_verified is False on this Google account")
        return None

    return {
        "email": info["email"],
        "google_id": info["sub"],
        "name": info.get("name", "")
    }
