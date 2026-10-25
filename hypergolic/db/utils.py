from datetime import datetime, timezone


def to_iso_utc(dt: datetime) -> str:
    """Serialize a datetime to ISO 8601 with explicit UTC offset.

    Naive datetimes from the DB (timestamp-without-tz columns) are assumed
    UTC and tagged accordingly.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
