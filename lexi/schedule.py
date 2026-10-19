"""Local daily rollover, including daylight-saving gaps and repeated hours."""
from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo


def validate_time(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("Choose an update time in HH:MM format (00:00–23:59).")
    return tuple(map(int, value.split(":")))


def rollover_at(day, update_time, timezone_name):
    """Earliest occurrence; missing clock times move to the first valid minute."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    hour, minute = validate_time(update_time)
    zone = ZoneInfo(timezone_name)
    wall = datetime(day.year, day.month, day.day, hour, minute)
    candidates = [wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc) for fold in (0, 1)]
    exact = [instant for instant in candidates if instant.astimezone(zone).replace(tzinfo=None) == wall]
    if exact:
        return min(exact)
    forward = [instant for instant in candidates if instant.astimezone(zone).replace(tzinfo=None) > wall]
    if not forward:
        raise ValueError("The update time could not be resolved in this timezone.")
    result = min(forward)
    # A missing hour (e.g. 02:30) updates at 03:00, not at 03:30.
    for _ in range(1440):
        previous = result - timedelta(minutes=1)
        local = previous.astimezone(zone)
        if local.date() != day or local.replace(tzinfo=None) < wall:
            return result
        result = previous
    raise ValueError("The update time could not be resolved in this timezone.")


def daily_schedule(now, timezone_name, update_time="00:00"):
    if now.tzinfo is None:
        raise ValueError("The current time must include a timezone.")
    local_day = now.astimezone(ZoneInfo(timezone_name)).date()
    boundary = rollover_at(local_day, update_time, timezone_name)
    learning_day = local_day if now.astimezone(timezone.utc) >= boundary else local_day - timedelta(days=1)
    return {
        "date": learning_day.isoformat(),
        "calendarDate": local_day.isoformat(),
        "timezone": timezone_name,
        "updateTime": update_time,
        "nextUpdateAt": rollover_at(learning_day + timedelta(days=1), update_time, timezone_name).isoformat(),
    }
