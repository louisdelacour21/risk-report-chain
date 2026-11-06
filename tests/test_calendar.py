from datetime import date

from riskreport import calendar as cal


def test_easter_2027():
    assert not cal.is_business_day(date(2027, 3, 26))  # Good Friday
    assert not cal.is_business_day(date(2027, 3, 29))  # Easter Monday
    assert cal.previous(date(2027, 3, 29)) == date(2027, 3, 25)  # T-1 of Easter Monday, as in the spec


def test_monday_looks_back_to_friday():
    assert cal.previous(date(2026, 11, 2)) == date(2026, 10, 30)


def test_business_days_count_and_order():
    d = cal.business_days(date(2026, 10, 30), 10)
    assert len(d) == 10 and d == sorted(d) and all(cal.is_business_day(x) for x in d)


def test_christmas_fixed_holidays():
    assert not cal.is_business_day(date(2026, 12, 25)) and not cal.is_business_day(date(2027, 1, 1))
