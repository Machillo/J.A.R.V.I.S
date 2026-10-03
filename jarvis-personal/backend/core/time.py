from datetime import date, datetime
from zoneinfo import ZoneInfo

COSTA_RICA_TZ = ZoneInfo("America/Costa_Rica")


def costa_rica_today() -> date:
    """DINCR's canonical calendar date (America/Costa_Rica), independent of the server zone."""
    return datetime.now(COSTA_RICA_TZ).date()


def get_time():
    timezone = ZoneInfo("America/Costa_Rica")
    now = datetime.now(timezone)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": "America/Costa_Rica"
    }