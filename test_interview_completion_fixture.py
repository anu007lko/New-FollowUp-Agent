from datetime import datetime, timedelta
from backend.app.domain.date_utils import TIMEZONE_NEW_YORK
from backend.app.domain.consolidated_classifier import classify_record

# 1. Scheduled interview in the future (Aug 15, 2026 at 2 PM EDT)
future_dt = datetime(2026, 8, 15, 14, 0, 0, tzinfo=TIMEZONE_NEW_YORK)
current_time_before = datetime(2026, 8, 15, 10, 0, 0, tzinfo=TIMEZONE_NEW_YORK)

timeline_future = [{
    "entry_id": "aud_01",
    "event_type": "INTERVIEW_SCHEDULE_CONFIRMED",
    "sender": "tarun@clifyx.com",
    "timestamp": current_time_before.isoformat(),
    "body_preview": f"Manager confirmed interview schedule: {future_dt.isoformat()}"
}]

res_future = classify_record("graph-future-iv", [], current_time_before, timeline=timeline_future)
print("=== 1. FUTURE INTERVIEW (BEFORE END TIME) ===")
print(f"Proposed Status: {res_future.proposed_status}")
print(f"Category: {res_future.category}")
assert res_future.proposed_status == "Interview Scheduled"

# 2. Elapsed interview (Same day, 3:30 PM EDT - 30 mins after 1h interview ends)
current_time_same_day_after = datetime(2026, 8, 15, 15, 30, 0, tzinfo=TIMEZONE_NEW_YORK)
res_same_day = classify_record("graph-future-iv", [], current_time_same_day_after, timeline=timeline_future)
print("\n=== 2. ELAPSED INTERVIEW (SAME DAY, AFTER END TIME) ===")
print(f"Proposed Status: {res_same_day.proposed_status}")
print(f"Category: {res_same_day.category}")
assert res_same_day.proposed_status == "AwaitingFeedback"
assert res_same_day.category == "Interview Completed"

# 3. Elapsed interview (Next business morning, Aug 16 at 9:30 AM EDT - past 9 AM EDT)
current_time_next_morning = datetime(2026, 8, 16, 9, 30, 0, tzinfo=TIMEZONE_NEW_YORK)
res_next_morning = classify_record("graph-future-iv", [], current_time_next_morning, timeline=timeline_future)
print("\n=== 3. ELAPSED INTERVIEW (NEXT BUSINESS MORNING AFTER 9 AM EDT) ===")
print(f"Proposed Status: {res_next_morning.proposed_status}")
print(f"Category: {res_next_morning.category}")
assert res_next_morning.proposed_status == "FeedbackDue"
assert res_next_morning.category == "Interview Completed"

print("\n✓ ALL ELAPSED INTERVIEW TRANSITION TESTS PASSED SUCCESSFULLY!")

