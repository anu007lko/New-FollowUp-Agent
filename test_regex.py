import re

body_preview = "Manager confirmed interview schedule: 2026-08-15T14:00:00-04:00"
sched_match = re.search(r"interview schedule:\s*([0-9T:\-+.]+)", body_preview, re.IGNORECASE)
print("sched_match:", sched_match)
if sched_match:
    print("Group 1:", sched_match.group(1))

