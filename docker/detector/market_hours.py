from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

NYSE_TZ = ZoneInfo("America/New_York")

# Horario regular NYSE
PRE_MARKET_START = dtime(hour=9, minute=15)
MARKET_OPEN = dtime(hour=9, minute=30)
MARKET_CLOSE = dtime(hour=16, minute=0)
POST_MARKET_END = dtime(hour=16, minute=15)


def is_market_open(now: datetime | None = None) -> bool:
    """
    Returns True if NYSE market is open.
    Assumes no holidays (handled later).
    """
    if now is None:
        now = datetime.now(tz=NYSE_TZ)
    else:
        now = now.astimezone(NYSE_TZ)

    # Lunes=0, Domingo=6
    if now.weekday() >= 5:
        return False

    current_time = now.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE

def is_detector_active(now: datetime | None = None) -> bool:
    """
    Returns True if detector should be running (warmup + market + grace).
    """
    if now is None:
        now = datetime.now(tz=NYSE_TZ)
    else:
        now = now.astimezone(NYSE_TZ)

    # Weekend
    if now.weekday() >= 5:
        return False

    current_time = now.time()
    return PRE_MARKET_START <= current_time < POST_MARKET_END

def seconds_until_detector_active(now: datetime | None = None) -> int:
    if now is None:
        now = datetime.now(tz=NYSE_TZ)
    else:
        now = now.astimezone(NYSE_TZ)

    if is_detector_active(now):
        return 0

    days_ahead = 0

    if now.weekday() >= 5:
        days_ahead = 7 - now.weekday()
    elif now.time() >= POST_MARKET_END:
        days_ahead = 1

    next_date = now.date() + timedelta(days=days_ahead)

    next_start = datetime.combine(
        next_date,
        PRE_MARKET_START,
        tzinfo=NYSE_TZ
    )

    return max(0, int((next_start - now).total_seconds()))


