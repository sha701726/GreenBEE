"""
ID proof number ko DB mein encrypted store karne ke liye (free 'cryptography' library).
Key: ID_ENCRYPTION_KEY env (Fernet key). Na ho to SECRET_KEY se derive hoti hai.
Purane plain-text rows bhi padhe ja sakte hain ('enc:' prefix na ho to plain maana jaata hai).
Key generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from config import Config

PREFIX = "enc:"


def _fernet():
    key = os.getenv("ID_ENCRYPTION_KEY", "").strip()
    if not key:
        digest = hashlib.sha256(("id-proof|" + str(Config.SECRET_KEY)).encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def encrypt_id(plain):
    if plain is None or plain == "":
        return plain
    if str(plain).startswith(PREFIX):
        return plain
    return PREFIX + _fernet().encrypt(str(plain).encode()).decode()


def decrypt_id(value):
    if not value or not str(value).startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(str(value)[len(PREFIX):].encode()).decode()
    except InvalidToken:
        return "[decrypt failed - key badli hai?]"


def mask_id(value):
    plain = decrypt_id(value) or ""
    return ("X" * max(len(plain) - 4, 0) + plain[-4:]) if plain else ""
