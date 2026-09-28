import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-key")

    # ---- Login session (customer + companion) ----
    # Session cookie signed hoti hai SECRET_KEY se - production mein FLASK_SECRET_KEY zaroor set karo
    # (aur saare gunicorn workers par same rakho), warna koi bhi session forge kar sakta hai.
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)   # 30 din tak login bana rahega
    SESSION_COOKIE_HTTPONLY = True                    # JS se cookie read nahi hoti
    SESSION_COOKIE_SAMESITE = "Lax"                   # cross-site POST par cookie nahi jaati (CSRF safety)
    # Render (https) par SESSION_COOKIE_SECURE=true set karo; local http par false rehne do
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

    # Do .env styles support karte hain:
    #  1) Simple (Render / production par ye use ho raha hai):
    #     DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL_CA
    #  2) Profile-based (local dev ke liye, jab local aur Aiven dono switch karna ho):
    #     DB_PROFILE=local|aiven + LOCAL_DB_* / AIVEN_DB_*
    # Agar DB_HOST seedha set hai to wahi priority mein use hoga (style 1) - Render isi ko
    # follow karta hai, isliye ye galti se style-2 ke localhost fallback mein nahi phasna chahiye.
    DB_PROFILE = os.getenv("DB_PROFILE", "").strip().lower()

    if os.getenv("DB_HOST"):
        _host = os.getenv("DB_HOST")
        _port = int(os.getenv("DB_PORT", "3306"))
        _user = os.getenv("DB_USER", "root")
        _password = os.getenv("DB_PASSWORD", "")
        _name = os.getenv("DB_NAME", "rentafriend_db")
        _ssl_ca = os.getenv("DB_SSL_CA", "").strip()

    elif DB_PROFILE == "aiven":
        _host = os.getenv("AIVEN_DB_HOST")
        _port = int(os.getenv("AIVEN_DB_PORT", "3306"))
        _user = os.getenv("AIVEN_DB_USER")
        _password = os.getenv("AIVEN_DB_PASSWORD")
        _name = os.getenv("AIVEN_DB_NAME", "defaultdb")
        _ssl_ca = os.getenv("AIVEN_DB_SSL_CA", "").strip()

        if not all([_host, _user, _password]):
            raise RuntimeError(
                "DB_PROFILE=aiven hai lekin AIVEN_DB_HOST / AIVEN_DB_USER / AIVEN_DB_PASSWORD "
                ".env mein set nahi hain. Aiven console ke 'Connection information' se copy karo."
            )
        if not _ssl_ca:
            raise RuntimeError(
                "DB_PROFILE=aiven ke saath AIVEN_DB_SSL_CA (CA cert ka path) set karna zaroori hai - "
                "Aiven plaintext connection allow nahi karta."
            )
    else:
        _host = os.getenv("LOCAL_DB_HOST", "localhost")
        _port = int(os.getenv("LOCAL_DB_PORT", "3306"))
        _user = os.getenv("LOCAL_DB_USER", "root")
        _password = os.getenv("LOCAL_DB_PASSWORD", "")
        _name = os.getenv("LOCAL_DB_NAME", "rentafriend_db")
        _ssl_ca = os.getenv("LOCAL_DB_SSL_CA", "").strip()

    DB_CONFIG = {
        "host": _host,
        "port": _port,
        "user": _user,
        "password": _password,
        "database": _name,
        "connection_timeout": 10,  # Aiven jaisi cloud DB ke liye slow/hung connection turant fail ho
    }

    # Aiven jaise managed MySQL ke liye SSL CA cert zaroori hai; Render par DB_SSL_CA=certs/ca.pem
    # set hai isliye ye automatically activate ho jayega.
    if _ssl_ca:
        if not os.path.isfile(_ssl_ca):
            raise FileNotFoundError(
                f"SSL CA file '{_ssl_ca}' par nahi mili. .env mein path check karo - "
                f"project root (jahan app.py hai) se relative hona chahiye (e.g. certs/ca.pem)."
            )
        DB_CONFIG["ssl_ca"] = _ssl_ca
        DB_CONFIG["ssl_verify_cert"] = True

    # DB_NAME alag se bhi chahiye kahin-kahin (init_db.py mein)
    DB_NAME = _name
