"""
dam/daemon/scheduler.py

Cron expression parser and next-run calculator for DAM's daemon mode.

Supports standard 5-field cron syntax:
  minute  hour  day-of-month  month  day-of-week
  0-59    0-23  1-31          1-12   0-7 (0 and 7 = Sunday)

Supported field syntax:
  *           any value
  */n         every n units (step)
  a-b         range
  a,b,c       list
  a-b/n       range with step

Examples:
  "0 2 1 * *"     — 2:00 AM on 1st of every month
  "0 3 * * 0"     — 3:00 AM every Sunday
  "30 4 * * 1-5"  — 4:30 AM weekdays
  "*/15 * * * *"  — every 15 minutes

Does NOT use the `schedule` library for next-run calculation —
pure stdlib datetime arithmetic so it works on QNAP's minimal Python.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


# ------------------------------------------------------------
# Cron field parser
# ------------------------------------------------------------

def _expand_field(value: str, min_val: int, max_val: int) -> set[int]:
    """
    Expand a single cron field into a set of matching integers.

    Args:
        value:    field string e.g. "*/5", "1-5", "0,15,30,45", "*"
        min_val:  minimum allowed value for this field
        max_val:  maximum allowed value for this field

    Returns:
        Set of matching integer values.
    """
    result: set[int] = set()

    for part in value.split(","):
        part = part.strip()

        if part == "*":
            result.update(range(min_val, max_val + 1))

        elif "/" in part:
            # Step: */5 or 0-59/5 or 1-5/2
            range_part, step_str = part.split("/", 1)
            step = int(step_str)
            if range_part == "*":
                start, end = min_val, max_val
            elif "-" in range_part:
                start, end = map(int, range_part.split("-", 1))
            else:
                start, end = int(range_part), max_val
            result.update(range(start, end + 1, step))

        elif "-" in part:
            # Range: 1-5
            start, end = map(int, part.split("-", 1))
            result.update(range(start, end + 1))

        else:
            # Literal: 5
            result.add(int(part))

    # Clamp to valid range
    return {v for v in result if min_val <= v <= max_val}


def _normalize_dow(values: set[int]) -> set[int]:
    """Normalize day-of-week: treat 7 as 0 (both = Sunday)."""
    if 7 in values:
        values = (values - {7}) | {0}
    return values


@dataclass
class CronExpression:
    """
    Parsed and validated cron expression.
    """
    raw: str
    minutes:      set[int]   # 0-59
    hours:        set[int]   # 0-23
    days_of_month: set[int]  # 1-31
    months:       set[int]   # 1-12
    days_of_week: set[int]   # 0-6 (0=Sunday)

    @classmethod
    def parse(cls, expression: str) -> "CronExpression":
        """
        Parse a 5-field cron expression string.
        Raises ValueError on invalid input.
        """
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression '{expression}': "
                f"expected 5 fields, got {len(parts)}"
            )

        minute_str, hour_str, dom_str, month_str, dow_str = parts

        try:
            return cls(
                raw=expression,
                minutes=      _expand_field(minute_str, 0, 59),
                hours=        _expand_field(hour_str,   0, 23),
                days_of_month=_expand_field(dom_str,    1, 31),
                months=       _expand_field(month_str,  1, 12),
                days_of_week= _normalize_dow(_expand_field(dow_str, 0, 7)),
            )
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid cron expression '{expression}': {e}")

    def matches(self, dt: datetime) -> bool:
        """Return True if this cron expression fires at the given datetime."""
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.month in self.months
            and dt.day in self.days_of_month
            and dt.weekday() in {
                # Python weekday(): Monday=0, Sunday=6
                # Cron: Sunday=0, Monday=1 ... Saturday=6
                (d + 1) % 7 for d in range(7)
                if (d + 1) % 7 in self.days_of_week
            } | (self.days_of_week if 0 in self.days_of_week else set())
        )

    def next_run(self, after: Optional[datetime] = None) -> datetime:
        """
        Calculate the next datetime this expression will fire.

        Args:
            after: Start searching after this datetime (default: now).
        Returns:
            Next matching datetime (truncated to minute precision).
        """
        # Start one minute after 'after' to avoid returning 'after' itself
        dt = (after or datetime.now()).replace(second=0, microsecond=0)
        dt += timedelta(minutes=1)

        # Search up to 4 years ahead to handle rare expressions
        limit = dt + timedelta(days=366 * 4)

        while dt < limit:
            # Fast-skip: if month doesn't match, jump to next matching month
            if dt.month not in self.months:
                # Advance to 1st of next month
                if dt.month == 12:
                    dt = dt.replace(year=dt.year + 1, month=1, day=1,
                                    hour=0, minute=0)
                else:
                    dt = dt.replace(month=dt.month + 1, day=1,
                                    hour=0, minute=0)
                continue

            # Fast-skip: if day doesn't match, jump to next day
            cron_dow = (dt.weekday() + 1) % 7   # convert Python→cron DOW
            day_matches = (
                dt.day in self.days_of_month
                and cron_dow in self.days_of_week
            )
            if not day_matches:
                dt = (dt + timedelta(days=1)).replace(hour=0, minute=0)
                continue

            # Fast-skip: if hour doesn't match, jump to next matching hour
            if dt.hour not in self.hours:
                next_hour = min((h for h in self.hours if h > dt.hour),
                                default=None)
                if next_hour is None:
                    dt = (dt + timedelta(days=1)).replace(hour=0, minute=0)
                else:
                    dt = dt.replace(hour=next_hour, minute=0)
                continue

            # Fast-skip: find next matching minute in this hour
            if dt.minute not in self.minutes:
                next_min = min((m for m in self.minutes if m > dt.minute),
                               default=None)
                if next_min is None:
                    dt += timedelta(hours=1)
                    dt = dt.replace(minute=0)
                else:
                    dt = dt.replace(minute=next_min)
                continue

            # All fields match
            return dt

        raise RuntimeError(
            f"Could not find next run for cron expression '{self.raw}' "
            f"within 4 years of {after}"
        )

    def describe(self) -> str:
        """Return a human-readable description of the schedule."""
        raw = self.raw.strip()

        descriptions = {
            "0 * * * *":     "every hour at :00",
            "*/5 * * * *":   "every 5 minutes",
            "*/15 * * * *":  "every 15 minutes",
            "*/30 * * * *":  "every 30 minutes",
            "0 0 * * *":     "daily at midnight",
            "0 12 * * *":    "daily at noon",
            "0 2 1 * *":     "monthly on the 1st at 2:00 AM",
            "0 3 * * 0":     "weekly on Sunday at 3:00 AM",
            "0 3 * * 1":     "weekly on Monday at 3:00 AM",
        }
        return descriptions.get(raw, f"cron: {raw}")


# ------------------------------------------------------------
# Convenience functions
# ------------------------------------------------------------

def parse_cron(expression: str) -> CronExpression:
    """Parse a cron expression. Raises ValueError on invalid input."""
    return CronExpression.parse(expression)


def next_run_from_now(expression: str) -> datetime:
    """Return the next scheduled run time for a cron expression."""
    return parse_cron(expression).next_run()


def validate_cron(expression: str) -> tuple[bool, str]:
    """
    Validate a cron expression.
    Returns (is_valid, error_message).
    """
    try:
        expr = parse_cron(expression)
        return True, expr.describe()
    except ValueError as e:
        return False, str(e)
