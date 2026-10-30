"""
Simple in-memory rate limiter (free, koi extra service nahi). Per-IP sliding window.
Note: har gunicorn worker ka apna counter hota hai - basic abuse/brute-force rokne ke liye kaafi hai.
"""
import os
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import jsonify, request

_lock = threading.Lock()
_hits = defaultdict(deque)


def client_ip():
    # TRUST_PROXY=true tabhi set karo jab app Render/nginx jaise proxy ke peeche ho
    if os.getenv("TRUST_PROXY", "").strip().lower() == "true":
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def hit(bucket, limit, window):
    """True agar allowed, False agar limit cross ho gayi."""
    if os.getenv("RATE_LIMIT_DISABLED", "").lower() == "true":
        return True
    key = (bucket, client_ip())
    now = time.time()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > 20000:  # memory guard
            for k in [k for k, v in _hits.items() if not v][:5000]:
                _hits.pop(k, None)
    return True


def limited(bucket, limit, window):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not hit(bucket, limit, window):
                return jsonify({"error": "Bahut zyada requests — thodi der baad try karo"}), 429
            return fn(*a, **kw)
        return wrapper
    return deco


def reset():
    with _lock:
        _hits.clear()
