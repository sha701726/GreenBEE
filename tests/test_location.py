"""Companion background location (5-min ping) + search accuracy."""
import db
from conftest import H, new_client, register_companion


def _active_companion(app_module, google):
    c = new_client(app_module.app)
    assert register_companion(c, google("loc@x.com")).status_code == 200
    db._exec("UPDATE companion SET status='Active', is_available=TRUE")
    return c


def test_location_ping_requires_companion_login(app_module):
    c = new_client(app_module.app)
    r = c.post("/api/companion/location", json={"latitude": 28.7, "longitude": 77.1}, headers=H)
    assert r.status_code == 401


def test_location_ping_validates_coords(app_module, google):
    c = _active_companion(app_module, google)
    for body in ({}, {"latitude": "x", "longitude": 1}, {"latitude": 95, "longitude": 10}):
        assert c.post("/api/companion/location", json=body, headers=H).status_code == 400


def test_ping_updates_db_and_search(app_module, google):
    c = _active_companion(app_module, google)
    cust = new_client(app_module.app)

    # Registration location (28.61, 77.20): Delhi ke paas search mein dikhta hai, Mumbai mein nahi
    assert len(cust.get("/api/companions/nearby?lat=28.61&lng=77.20").get_json()) == 1
    assert cust.get("/api/companions/nearby?lat=19.07&lng=72.87").get_json() == []

    # Companion Mumbai chala gaya - background ping
    r = c.post("/api/companion/location", json={"latitude": 19.07, "longitude": 72.87}, headers=H)
    assert r.status_code == 200 and r.get_json()["updated"] is True

    row = db._exec("SELECT latitude, longitude, location_updated_at, is_available FROM companion", fetch="one")
    assert float(row["latitude"]) == 19.07 and row["location_updated_at"] is not None
    assert row["is_available"] == 1                      # Show/Hide switch untouched
    assert len(cust.get("/api/companions/nearby?lat=19.07&lng=72.87").get_json()) == 1
    assert cust.get("/api/companions/nearby?lat=28.61&lng=77.20").get_json() == []


def test_hidden_companion_stays_hidden_after_ping(app_module, google):
    c = _active_companion(app_module, google)
    db._exec("UPDATE companion SET is_available=FALSE")
    c.post("/api/companion/location", json={"latitude": 28.61, "longitude": 77.20}, headers=H)
    assert new_client(app_module.app).get("/api/companions/nearby?lat=28.61&lng=77.20").get_json() == []


def test_static_assets_cached_and_pages_render(app_module):
    c = new_client(app_module.app)
    html = c.get("/").get_data(as_text=True)
    assert "cdn.tailwindcss.com" not in html and "css/tailwind.css?v=" in html
    assert 'data-companion="1"' not in html
    r = c.get("/static/css/tailwind.css?v=1")
    assert r.status_code == 200 and "immutable" in r.headers["Cache-Control"]
