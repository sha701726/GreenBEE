"""Shift availability (pure logic - MySQL ki zaroorat nahi)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DB_HOST", "127.0.0.1")

from db import day_status, shift_availability  # noqa: E402

H = 60


@pytest.fixture(autouse=True)
def clean_db():  # conftest ka DB-cleanup fixture yahan nahi chahiye - ye tests MySQL ke bina chalte hain
    yield


def test_free_day_both_shifts_available():
    s = shift_availability([], 5 * H)
    assert s == {"morning": "available", "evening": "available"} and day_status(s) == "available"


def test_morning_fully_booked_evening_free():
    s = shift_availability([(6 * H, 14 * H)], 5 * H)
    assert s == {"morning": "booked", "evening": "available"}
    assert day_status(s) == "available"


def test_both_shifts_booked_is_fully_booked():
    s = shift_availability([(6 * H, 14 * H), (15 * H, 22 * H)], 5 * H)   # 14-15 buffer, 15-22 booked
    assert s == {"morning": "booked", "evening": "booked"} and day_status(s) == "booked"


def test_buffer_after_booking_blocks_next_hour():
    # 6-13 booked + 1h buffer -> 13-14 blocked, morning me kuch nahi bacha
    assert shift_availability([(6 * H, 13 * H)], 5 * H)["morning"] == "booked"
    # 6-11 booked -> 12:00-14:00 free (2h)
    assert shift_availability([(6 * H, 11 * H)], 5 * H)["morning"] == "available"


def test_gap_between_bookings_must_fit_an_hour():
    # 6-8 (buffer till 9), 10-14: gap 9-10 = 60 min -> available
    assert shift_availability([(6 * H, 8 * H), (10 * H, 14 * H)], 5 * H)["morning"] == "available"
    # 6-8 (buffer till 9), 9:30-14: gap 30 min -> booked
    assert shift_availability([(6 * H, 8 * H), (9 * H + 30, 14 * H)], 5 * H)["morning"] == "booked"


def test_past_time_marks_shift_ended():
    s = shift_availability([], 13 * H + 30)          # 1:30 PM: morning me <1h bacha
    assert s["morning"] == "ended" and s["evening"] == "available"
    s = shift_availability([], 21 * H + 30)
    assert s == {"morning": "ended", "evening": "ended"} and day_status(s) == "ended"


def test_now_inside_shift_only_counts_remaining_time():
    # 10:00 baje, 10-12 booked(+buffer 13) -> baaki 13-14 = 60 min -> available
    assert shift_availability([(10 * H, 12 * H)], 9 * H + 59)["morning"] == "available"
    # 10:30 baje, 10-12 booked -> 13:00 se 14:00 = 60 -> available; 11:00-... ongoing booking blocks
    assert shift_availability([(10 * H, 13 * H)], 10 * H + 30)["morning"] == "booked"


def test_free_windows_from_bookings():
    from db import free_windows
    assert free_windows([], 5 * H) == [["06:00", "22:00"]]
    # 10-12 booked (+1h buffer -> 13:00): 06-10 aur 13-22 khaali
    assert free_windows([(10 * H, 12 * H)], 5 * H) == [["06:00", "10:00"], ["13:00", "22:00"]]
    # 30 min ka gap nahi dikhna chahiye
    assert free_windows([(6 * H, 8 * H), (9 * H + 30, 12 * H)], 5 * H) == [["13:00", "22:00"]]
    # din khatam
    assert free_windows([], 21 * H + 30) == []
