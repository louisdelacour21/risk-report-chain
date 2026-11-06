"""TARGET2 business days (closed: 1 Jan, Good Friday, Easter Monday, 1 May, 25 and 26 Dec, plus weekends)."""
from datetime import date, timedelta

from dateutil.easter import easter


def holidays(year):
    e = easter(year)
    return {date(year, 1, 1), e - timedelta(2), e + timedelta(1), date(year, 5, 1), date(year, 12, 25), date(year, 12, 26)}


def is_business_day(d):
    return d.weekday() < 5 and d not in holidays(d.year)


def previous(d):
    """Last business day strictly before d (T-1)."""
    d -= timedelta(1)
    while not is_business_day(d):
        d -= timedelta(1)
    return d


def next_(d):
    d += timedelta(1)
    while not is_business_day(d):
        d += timedelta(1)
    return d


def business_days(end, n):
    """The n business days ending at `end` (included if it is one), oldest first."""
    out, d = [], end if is_business_day(end) else previous(end)
    while len(out) < n:
        out.append(d)
        d = previous(d)
    return out[::-1]


def asof_auto(today=None):
    """Reporting date for a run at 07:30 on `today`: the last business day before today."""
    return previous(today or date.today())
