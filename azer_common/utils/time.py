from datetime import datetime, timezone


def current_utc_time():
    return datetime.now(timezone.utc)
