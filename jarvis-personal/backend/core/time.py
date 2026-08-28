from datetime import datetime
from zoneinfo import ZoneInfo


def get_time():
    timezone = ZoneInfo("America/Costa_Rica")
    now = datetime.now(timezone)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": "America/Costa_Rica"
    }