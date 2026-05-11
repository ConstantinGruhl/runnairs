from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


class ScheduleTimezoneError(ValueError):
    """Raised when a schedule references an unknown timezone."""


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleTimezoneError(f"invalid timezone: {timezone_name!r}") from exc


def next_run_at_utc(
    cron: str,
    *,
    timezone_name: str,
    base: datetime | None = None,
) -> datetime:
    utc_base = (base or datetime.now(timezone.utc)).astimezone(timezone.utc)
    zone = resolve_timezone(timezone_name)
    local_base = utc_base.astimezone(zone)
    next_local = croniter(cron, local_base).get_next(datetime)
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=zone)
    return next_local.astimezone(timezone.utc)
