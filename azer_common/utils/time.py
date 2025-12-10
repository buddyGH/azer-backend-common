from datetime import datetime, timezone, date


def utc_now():
    return datetime.now(timezone.utc)


def today():
    return date.today()
