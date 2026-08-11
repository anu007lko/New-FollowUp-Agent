from datetime import datetime, timedelta
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK
import re

future_dt = datetime(2026, 8, 15, 14, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
current_time_before = datetime(2026, 8, 15, 10, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
body_preview = f"Manager confirmed interview schedule: {future_dt.isoformat()}"

print("body_preview:", body_preview)
sched_match = re.search(r"interview schedule:\s*([0-9T:\-+.]+)", body_preview, re.IGNORECASE)
print("sched_match:", sched_match)

if sched_match:
    raw_str = sched_match.group(1).strip()
    print("raw_str:", raw_str)
    iv_dt = datetime.fromisoformat(raw_str)
    print("iv_dt:", iv_dt)
    print("current_time_before:", current_time_before)
    if iv_dt.tzinfo is None:
        iv_dt = iv_dt.replace(tzinfo=current_time_before.tzinfo)
    end_dt = iv_dt + timedelta(hours=1)
    print("end_dt:", end_dt)
    print("current_time_before >= end_dt:", current_time_before >= end_dt)

