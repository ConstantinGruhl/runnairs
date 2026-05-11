from datetime import datetime, timezone

import pytest

from app.services.schedule_service import ScheduleTimezoneError, next_run_at_utc


def test_next_run_at_utc_uses_schedule_timezone() -> None:
    base = datetime(2026, 5, 11, 0, 30, tzinfo=timezone.utc)

    next_run = next_run_at_utc(
        "0 9 * * *",
        timezone_name="Asia/Singapore",
        base=base,
    )

    assert next_run == datetime(2026, 5, 11, 1, 0, tzinfo=timezone.utc)


def test_next_run_at_utc_rejects_invalid_timezones() -> None:
    with pytest.raises(ScheduleTimezoneError):
        next_run_at_utc("0 9 * * *", timezone_name="Mars/Olympus")
