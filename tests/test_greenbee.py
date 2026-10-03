
import db
from conftest import H, admin_client, insert_booking, new_client, register_companion, signup_customer


# ---------- security / CSRF ----------
def test_csrf_header_required(client):
    assert client.post("/api/auth/google", json={"credential": "x"}).status_code == 403


def test_private_companion_data_not_public(client, google):
    c = new_client(client.application)
    cid = register_companion(c, google("a@x.com")).get_json()["companion_id"]
    anon = new_client(client.application)
    assert anon.get(f"/api/companions/{cid}").status_code == 403
    assert anon.get("/api/companions").status_code == 403
    assert admin_client(client.application).get("/api/companions").status_code == 200


def test_security_headers_and_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.headers["X-Frame-Options"] == "DENY"
    assert client.get("/nope").status_code == 404
    assert client.get("/privacy").status_code == 200 and client.get("/terms").status_code == 200


def test_rate_limit_blocks(app_module, monkeypatch):
    import ratelimit
    monkeypatch.delenv("RATE_LIMIT_DISABLED")
    ratelimit.reset()
    with app_module.app.test_request_context("/"):
        assert all(ratelimit.hit("t", 3, 60) for _ in range(3)) and not ratelimit.hit("t", 3, 60)
    ratelimit.reset()


# ---------- registration / consent / encryption ----------
def test_companion_registration_rules(client, google):
    c = new_client(client.application)
    assert register_companion(c, google("a@x.com"), consent=False).status_code == 400
    assert register_companion(c, google("a@x.com"), dob="2015-01-01").status_code == 400
    r = register_companion(c, google("a@x.com"))
    assert r.status_code == 200
    cid = r.get_json()["companion_id"]
    raw = db._exec("SELECT id_proof_number, consent_at, status FROM companion WHERE companion_id=%s", (cid,), fetch="one")
    assert raw["id_proof_number"].startswith("enc:") and "1234" not in raw["id_proof_number"]
    assert raw["consent_at"] is not None and raw["status"] == "Inactive"
    own = c.get(f"/api/companions/{cid}").get_json()          # owner view: masked
    assert own["id_proof_number"] == "XXXXXXXX1234" and "google_id" not in own
    adm = admin_client(client.application).get("/api/admin/companions").get_json()
    assert adm[0]["id_proof_number"] == "123412341234"         # admin ko asli number


def test_google_flow_roles_and_consent(client, google):
    c = new_client(client.application)
    tok = google("new@x.com")
    assert c.post("/api/auth/google", json={"credential": tok}, headers=H).get_json()["role"] == "new_user"
    assert signup_customer(c, tok, consent=False).status_code == 400
    assert signup_customer(c, tok).get_json()["role"] == "customer"
    c2 = new_client(client.application)   # existing customer -> location update
    r = c2.post("/api/auth/google", json={"credential": tok, "latitude": 19.0, "longitude": 72.8}, headers=H)
    assert r.get_json()["role"] == "customer"
    row = db._exec("SELECT latitude, consent_at FROM customer", fetch="one")
    assert float(row["latitude"]) == 19.0 and row["consent_at"] is not None


# ---------- admin ----------
def test_admin_login_and_verification(client, google):
    assert new_client(client.application).post("/api/admin/login", json={"key": "bad"}, headers=H).status_code == 401
    assert new_client(client.application).get("/api/admin/stats").status_code == 401
    c = new_client(client.application)
    cid = register_companion(c, google("a@x.com")).get_json()["companion_id"]
    adm = admin_client(client.application)
    assert adm.get("/api/admin/stats").get_json()["pending_companions"] == 1
    assert adm.post(f"/api/admin/companions/{cid}/approve", headers=H).status_code == 200
    row = db._exec("SELECT status, background_check FROM companion", fetch="one")
    assert (row["status"], row["background_check"]) == ("Active", "Passed")
    assert c.get("/api/notifications?role=companion").get_json()["unread"] == 1
    assert adm.post(f"/api/admin/companions/{cid}/bogus", headers=H).status_code == 400


# ---------- booking flow ----------
def setup_pair(app_module, google):
    comp, cust = new_client(app_module), new_client(app_module)
    cid = register_companion(comp, google("comp@x.com")).get_json()["companion_id"]
    admin_client(app_module).post(f"/api/admin/companions/{cid}/approve", headers=H)
    db._exec("UPDATE companion SET is_available=TRUE WHERE companion_id=%s", (cid,))
    cuid = signup_customer(cust, google("cust@x.com")).get_json()["customer_id"]
    return comp, cust, cid, cuid


def test_booking_accept_contact_complete_review(client, google, clock):
    A = client.application
    comp, cust, cid, cuid = setup_pair(A, google)
    r = cust.post("/api/bookings", json={"companion_id": cid, "start_time": "12:30", "end_time": "13:30"}, headers=H)
    assert r.status_code == 200, r.get_json()
    bid = r.get_json()["booking_id"]
    assert r.get_json()["companion_phone"] == "9000000001"                       # booking hote hi customer ko number
    assert cust.get("/api/my/bookings?role=customer").get_json()[0]["other_phone"] == "9000000001"

    cb = comp.get("/api/my/bookings?role=companion").get_json()
    assert cb[0]["status"] == "Pending" and cb[0]["other_phone"] is None        # customer ka number accept tak hidden
    assert comp.get("/api/notifications?role=companion").get_json()["unread"] >= 1

    stranger = new_client(A); signup_customer(stranger, google("s@x.com"), phone="9222222222")
    assert stranger.post(f"/api/bookings/{bid}/action", json={"role": "customer", "action": "cancel"}, headers=H).status_code == 403
    assert cust.post(f"/api/bookings/{bid}/action", json={"role": "customer", "action": "accept"}, headers=H).status_code == 409

    assert comp.post(f"/api/bookings/{bid}/action", json={"role": "companion", "action": "accept"}, headers=H).status_code == 200
    mine = cust.get("/api/my/bookings?role=customer").get_json()[0]
    assert mine["status"] == "Confirmed" and mine["other_phone"] == "9000000001"
    assert comp.get("/api/my/bookings?role=companion").get_json()[0]["other_phone"] == "9111111111"

    # review abhi nahi (Completed nahi)
    assert cust.post(f"/api/bookings/{bid}/review", json={"rating": 5}, headers=H).status_code == 409
    assert comp.post(f"/api/bookings/{bid}/paid", headers=H).status_code == 200

    clock["now"] = clock["now"].replace(hour=14)       # end time guzar gaya -> auto Completed
    assert cust.get("/api/my/bookings?role=customer").get_json()[0]["status"] == "Completed"
    row = db._exec("SELECT payout_amount, completed_at FROM booking", fetch="one")
    assert float(row["payout_amount"]) == 160.0 and row["completed_at"] is not None   # 20% commission

    assert cust.post(f"/api/bookings/{bid}/review", json={"rating": 9}, headers=H).status_code == 400
    assert cust.post(f"/api/bookings/{bid}/review", json={"rating": 4, "comment": "nice"}, headers=H).status_code == 200
    assert cust.post(f"/api/bookings/{bid}/review", json={"rating": 5}, headers=H).status_code == 409
    near = cust.get("/api/companions/nearby?lat=28.61&lng=77.20").get_json()
    assert float(near[0]["avg_rating"]) == 4.0 and near[0]["review_count"] == 1


def test_reject_cancel_and_expiry(client, google, clock):
    A = client.application
    comp, cust, cid, cuid = setup_pair(A, google)
    b1 = insert_booking(cid, cuid, "12:30", "13:30")
    assert comp.post(f"/api/bookings/{b1}/action", json={"role": "companion", "action": "reject"}, headers=H).status_code == 200
    assert db._exec("SELECT status, cancelled_by FROM booking WHERE booking_id=%s", (b1,), fetch="one") == {"status": "Cancelled", "cancelled_by": "Companion"}

    b2 = insert_booking(cid, cuid, "15:00", "16:00", status="Confirmed")
    assert cust.post(f"/api/bookings/{b2}/action", json={"role": "customer", "action": "cancel"}, headers=H).status_code == 200

    b3 = insert_booking(cid, cuid, "12:10", "13:00")                    # Pending, start nikal gaya
    clock["now"] = clock["now"].replace(hour=12, minute=40)
    assert comp.post(f"/api/bookings/{b3}/action", json={"role": "companion", "action": "accept"}, headers=H).status_code == 409
    assert db._exec("SELECT cancelled_by FROM booking WHERE booking_id=%s", (b3,), fetch="one")["cancelled_by"] == "System"


# ---------- report / SOS ----------
def test_report_and_sos(client, google, clock):
    A = client.application
    comp, cust, cid, cuid = setup_pair(A, google)
    pending = insert_booking(cid, cuid, "12:30", "13:30")
    confirmed = insert_booking(cid, cuid, "15:00", "16:00", status="Confirmed")
    sos = {"role": "customer", "sos": True, "latitude": 28.6, "longitude": 77.2}
    assert cust.post("/api/reports", json=dict(sos, booking_id=pending), headers=H).status_code == 409
    r = cust.post("/api/reports", json=dict(sos, booking_id=confirmed), headers=H)
    assert r.status_code == 200 and r.get_json()["emergency_number"] == "112"
    assert comp.post("/api/reports", json={"role": "companion", "booking_id": confirmed, "issue_type": "Harassment", "description": "x"}, headers=H).status_code == 200
    assert cust.post("/api/reports", json={"role": "customer", "booking_id": confirmed, "issue_type": "Nope"}, headers=H).status_code == 400
    adm = admin_client(A)
    reports = adm.get("/api/admin/reports").get_json()
    assert reports[0]["is_sos"] == 1 and len(reports) == 2                  # SOS sabse upar
    assert adm.get("/api/admin/stats").get_json()["open_sos"] == 1
    assert adm.post(f"/api/admin/reports/{reports[0]['report_id']}", json={"status": "Resolved", "action_taken": "called"}, headers=H).status_code == 200


# ---------- admin suspend / account close ----------
def test_suspend_cancels_bookings_and_blocks_login(client, google, clock):
    A = client.application
    comp, cust, cid, cuid = setup_pair(A, google)
    b = insert_booking(cid, cuid, "15:00", "16:00", status="Confirmed")
    r = admin_client(A).post(f"/api/admin/companions/{cid}/suspend", headers=H).get_json()
    assert r["cancelled_bookings"] == 1
    assert db._exec("SELECT cancelled_by FROM booking WHERE booking_id=%s", (b,), fetch="one")["cancelled_by"] == "Admin"
    assert comp.get(f"/api/companions/{cid}/status").status_code in (401, 403)       # session block
    again = new_client(A).post("/api/auth/google", json={"credential": google("comp@x.com"), "latitude": 1, "longitude": 1}, headers=H)
    assert again.status_code == 403


def test_deactivate_and_delete(client, google, clock):
    A = client.application
    comp, cust, cid, cuid = setup_pair(A, google)
    b = insert_booking(cid, cuid, "15:00", "16:00", status="Confirmed")
    assert cust.post("/api/account/delete", json={"role": "customer", "confirm": "DELETE"}, headers=H).status_code == 409
    assert cust.post("/api/account/delete", json={"role": "customer", "confirm": "no"}, headers=H).status_code == 400
    cust.post(f"/api/bookings/{b}/action", json={"role": "customer", "action": "cancel"}, headers=H)
    assert cust.post("/api/account/delete", json={"role": "customer", "confirm": "DELETE"}, headers=H).status_code == 200
    row = db._exec("SELECT full_name, email, google_id, phone FROM customer", fetch="one")
    assert row["full_name"] == "Deleted user" and row["email"].endswith("@deleted.invalid") and row["google_id"] is None
    assert cust.get("/api/my/bookings?role=customer").status_code == 401

    assert comp.post("/api/account/deactivate", json={"role": "companion"}, headers=H).status_code == 200
    assert db._exec("SELECT status FROM companion", fetch="one")["status"] == "Deactivated"
    back = new_client(A).post("/api/auth/google", json={"credential": google("comp@x.com"), "latitude": 1, "longitude": 1}, headers=H)
    assert back.status_code == 200
    assert db._exec("SELECT status FROM companion", fetch="one")["status"] == "Active"   # verified tha -> wapas Active


def test_profile_update_validation(client, google, clock):
    A = client.application
    comp, cust, cid, cuid = setup_pair(A, google)
    assert comp.post("/api/profile/update", json={"role": "companion", "fields": {"hourly_rate": "abc"}}, headers=H).status_code == 400
    assert comp.post("/api/profile/update", json={"role": "companion", "fields": {"hourly_rate": "350", "bio": "hi", "id_proof_number": "hack"}}, headers=H).status_code == 200
    row = db._exec("SELECT hourly_rate, bio, id_proof_number FROM companion", fetch="one")
    assert float(row["hourly_rate"]) == 350 and row["bio"] == "hi" and row["id_proof_number"].startswith("enc:")  # ID edit nahi hota
    assert cust.post("/api/profile/update", json={"role": "customer", "fields": {"phone": "9111111111"}}, headers=H).status_code == 200
    other = new_client(A); signup_customer(other, google("o@x.com"), phone="9333333333")
    assert cust.post("/api/profile/update", json={"role": "customer", "fields": {"phone": "9333333333"}}, headers=H).status_code == 409   # duplicate phone
