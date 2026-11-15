"""Working-day calendar: Sunday to Thursday are working days (Saudi week); Friday and Saturday are the weekend.
Public holidays come from the `holidays` table, which administrators maintain. Islamic holiday dates depend on
moon sighting, so seeded dates are estimates until an administrator marks them confirmed."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holiday

WEEKEND = {4, 5}  # Python weekday(): Monday=0 ... Friday=4, Saturday=5
KSA = timezone(timedelta(hours=3), "AST")  # Saudi Arabia: UTC+3 all year (no daylight saving)


def today() -> date:
    """The business date in Saudi Arabia, whatever time zone the server runs in."""
    return datetime.now(KSA).date()


def business_date(dt: datetime) -> date:
    """The Saudi calendar date of a stored (UTC) timestamp."""
    return dt.astimezone(KSA).date()


class WorkCalendar:
    def __init__(self, holidays: set[date] | None = None):
        self.holidays = holidays or set()

    @classmethod
    def load(cls, db: Session) -> "WorkCalendar":
        return cls(set(db.scalars(select(Holiday.day)).all()))

    def is_working_day(self, d: date) -> bool:
        return d.weekday() not in WEEKEND and d not in self.holidays

    def next_working_day(self, d: date) -> date:
        while not self.is_working_day(d):
            d += timedelta(days=1)
        return d

    def add_working_days(self, start: date, n: int) -> date:
        """The date that is n working days after `start` (start itself not counted)."""
        d, left = start, n
        while left > 0:
            d += timedelta(days=1)
            if self.is_working_day(d):
                left -= 1
        return d

    def nth_working_day(self, start: date, n: int) -> date:
        """The n-th working day counting `start` as day 1 if it is a working day."""
        d = self.next_working_day(start)
        return self.add_working_days(d, n - 1) if n > 1 else d

    def working_days_between(self, start: date, end: date) -> int:
        """Working days from start to end, both included."""
        if end < start:
            return 0
        n, d = 0, start
        while d <= end:
            n += self.is_working_day(d)
            d += timedelta(days=1)
        return n

    def split_periods(self, start: date, total_days: int, period_len: int) -> list[tuple[date, date, int]]:
        """Splits a contract into billing periods of `period_len` working days; the last one holds the rest.
        Example: 90 days, 20-day periods -> 20, 20, 20, 20, 10."""
        periods, day, left = [], self.next_working_day(start), total_days
        while left > 0:
            size = min(period_len, left)
            end = self.nth_working_day(day, size)
            periods.append((day, end, size))
            left -= size
            day = self.add_working_days(end, 1)
        return periods
