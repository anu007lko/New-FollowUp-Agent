import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.app.domain.message_facts import analyze_conversation
from backend.app.domain.outcome_parser import evaluate_outcome_status
from backend.app.domain.consolidated_classifier import classify_record

msgs = [
    {
        "id": "m1",
        "from": {"emailAddress": {"address": "tarun@clifyx.com"}},
        "subject": "418542 - EP2026RA7308068 - Rani Ciriguri - SAP S/4HANA OTC / SD Consultant - Advantage Sales & Marketing LLC - Remote",
        "bodyPreview": "Hi Aditi, PFA profile of Ms. Rani Ciriguri",
        "sentDateTime": "2026-07-14T15:20:49Z"
    },
    {
        "id": "m2",
        "from": {"emailAddress": {"address": "kavi.rajendiran@tcs.com"}},
        "subject": "RE: 418542 - EP2026RA7308068 - Rani Ciriguri - SAP S/4HANA OTC / SD Consultant - Advantage Sales & Marketing LLC - Remote",
        "bodyPreview": "TCS Confidential\n\nHi Tarun,\n\nThis requirement is closed, please do not submit profiles.\n\nRegards,\nKavi Rajendiran",
        "sentDateTime": "2026-07-14T15:26:04Z"
    }
]

facts = analyze_conversation("m1", msgs)
evaluate_outcome_status(facts)
print(f"Facts outcome status: {facts.outcome_status}")
print(f"Facts no response status: {facts.no_response_status}")

res = classify_record("m1", msgs, datetime.now(timezone.utc))
print(f"Classification Category: {res.category}")
print(f"Classification Proposed Status: {res.proposed_status}")
print(f"Classification Reason Code: {res.reason_code}")
