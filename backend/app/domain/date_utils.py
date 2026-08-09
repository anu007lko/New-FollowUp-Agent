"""
Time zone and date boundary utility.

INVARIANT:
Target horizon July 10, 2026 refers to midnight (00:00:00) in America/New_York.
In summer (EDT), America/New_York is UTC-4.
In winter (EST), America/New_York is UTC-5.
Converts local New York midnight timestamps correctly to UTC ISO-8601 string for Graph API OData queries.
"""

import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TIMEZONE_NEW_YORK = ZoneInfo("America/New_York")
TIMEZONE_UTC = ZoneInfo("UTC")


def get_new_york_midnight_utc_iso(date_str: str = "2026-07-10") -> str:
    """
    Convert a date string (YYYY-MM-DD) representing midnight in America/New_York
    to a UTC ISO-8601 string suitable for Microsoft Graph OData filter queries.

    Example: "2026-07-10" -> "2026-07-10T04:00:00Z" (EDT is UTC-4)
    Example: "2026-01-10" -> "2026-01-10T05:00:00Z" (EST is UTC-5)
    """
    dt_local = datetime.strptime(f"{date_str} 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=TIMEZONE_NEW_YORK)
    dt_utc = dt_local.astimezone(TIMEZONE_UTC)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_current_new_york_datetime() -> datetime:
    """Get current datetime in America/New_York time zone."""
    return datetime.now(TIMEZONE_NEW_YORK)


def add_calendar_months(dt: datetime, months: int) -> datetime:
    """
    Add specified number of calendar months to a datetime object.
    Handles month-end clamping (e.g. Jan 31 + 3 months -> Apr 30)
    and leap years (e.g. Nov 29, 2023 + 3 months -> Feb 29, 2024).
    Preserves original timezone, hour, minute, second, and microsecond.
    """
    target_month_index = (dt.month - 1) + months
    target_year = dt.year + (target_month_index // 12)
    target_month = (target_month_index % 12) + 1
    
    max_days = calendar.monthrange(target_year, target_month)[1]
    target_day = min(dt.day, max_days)
    
    return dt.replace(year=target_year, month=target_month, day=target_day)


def calculate_retention_expiry(latest_message_dt: datetime) -> datetime:
    """
    Calculate retention expiry as exactly three calendar months after the latest real Outlook message.
    """
    return add_calendar_months(latest_message_dt, 3)

