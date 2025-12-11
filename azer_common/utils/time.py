from datetime import datetime, timedelta, timezone, date


def utc_now():
    return datetime.now(timezone.utc)


def today():
    return date.today()


def add_days(days):
    return utc_now() + timedelta(days=days)
