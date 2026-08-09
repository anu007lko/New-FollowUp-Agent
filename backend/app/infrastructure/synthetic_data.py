"""
Synthetic test data provider for M3 dashboard.

INVARIANT: All data is clearly labeled [SYNTHETIC TEST DATA].
Graph access is blocked pending administrator approval.
This provider generates deterministic records for UI development and testing.

Identity uses ONLY conversationId and graph_immutable_id.
Job ID, EP reference, subject, and candidate name are display metadata ONLY.
"""

from datetime import datetime, timedelta
from backend.app.domain.models import (
    DomainStatus, InterviewState, SubmissionRecord, SubmissionRecordHeader,
    TimelineEntry, SubjectMetadata, DashboardSummary
)
from backend.app.domain.date_utils import TIMEZONE_UTC, TIMEZONE_NEW_YORK


def _ts(hours_ago: float) -> str:
    """UTC ISO timestamp N hours ago from a fixed reference point."""
    # Fixed reference: 2026-08-03T12:00:00Z for deterministic output
    ref = datetime(2026, 8, 3, 12, 0, 0, tzinfo=TIMEZONE_UTC)
    return (ref - timedelta(hours=hours_ago)).isoformat()


_synthetic_records_cache: dict[str, SubmissionRecord] = {}


def get_synthetic_records() -> list[SubmissionRecord]:
    """Generate or retrieve synthetic records covering all dashboard statuses."""
    global _synthetic_records_cache
    if not _synthetic_records_cache:
        records = _build_synthetic_records()
        for r in records:
            _synthetic_records_cache[r.id] = r
    return list(_synthetic_records_cache.values())


def reset_synthetic_records_cache():
    """Reset synthetic records cache."""
    global _synthetic_records_cache
    _synthetic_records_cache.clear()


def _build_synthetic_records() -> list[SubmissionRecord]:
    """Internal builder for synthetic records."""
    records = [
        # 1. Awaiting Feedback — manager confirmed interview completed 36h ago, 12h remaining on 48h timer
        SubmissionRecord(
            id="syn-rec-001",
            graph_immutable_id="AAMkSynth001",
            conversation_id="AAQkSynthConv001",
            job_id="418326",
            ep_reference="EP2026RA7415469",
            candidate_name="Govinda Mundra",
            skill="Technical Program Manager for AI PM",
            customer="AMEX",
            location="Phoenix, AZ",
            domain_status=DomainStatus.AWAITING_FEEDBACK,
            received_at=_ts(120),
            created_at=_ts(120),
            interview_state=InterviewState.COMPLETED,
            interview_updated_at=_ts(36),
            feedback_due_at=_ts(-12),  # 12h from now
            manager_notes="",
            system_notes=f"[{_ts(120)}] Imported from Submissions folder\n[{_ts(36)}] Manager confirmed interview completed — 48h feedback timer started",
            latest_update="Manager confirmed interview completed — awaiting client feedback (12h remaining)",
            latest_sender="Manager Action (Manual Confirmation)",
            latest_timestamp=_ts(36),
            timeline=[
                TimelineEntry(entry_id="te-001a", record_id="syn-rec-001", sender="tarun@clifyx.com", timestamp=_ts(120), body_preview="Submission: Govinda Mundra for TPM role at AMEX", classification="Submission", to_recipients=["recruiter@tcs.com"], cc_recipients=["team@tcs.com"], graph_immutable_id="AAMkMsg001a"),
                TimelineEntry(entry_id="te-001b", record_id="syn-rec-001", sender="recruiter@tcs.com", timestamp=_ts(96), body_preview="Thank you for the submission. We will review and get back.", classification="Acknowledgement", to_recipients=["tarun@clifyx.com"], cc_recipients=["team@tcs.com"], graph_immutable_id="AAMkMsg001b"),
                TimelineEntry(entry_id="te-001c", record_id="syn-rec-001", sender="recruiter@tcs.com", timestamp=_ts(72), body_preview="Interview scheduled for July 30, 2026 at 2:00 PM ET", classification="InterviewRequestScheduled", to_recipients=["tarun@clifyx.com"], cc_recipients=["team@tcs.com"], graph_immutable_id="AAMkMsg001c"),
                TimelineEntry(entry_id="te-001d", record_id="syn-rec-001", sender="Manager Action (Manual Confirmation)", timestamp=_ts(36), body_preview="Manager confirmed interview completed. 48-hour feedback window active.", classification="ManagerConfirmation", is_system_note=True),
            ],
        ),
        # 2. Feedback Due — 48h timer expired
        SubmissionRecord(
            id="syn-rec-002",
            graph_immutable_id="AAMkSynth002",
            conversation_id="AAQkSynthConv002",
            job_id="771209",
            ep_reference="EP2026RA9981240",
            candidate_name="Priya Patel",
            skill="React Frontend Architect",
            customer="Apple",
            location="Remote",
            domain_status=DomainStatus.FEEDBACK_DUE,
            received_at=_ts(168),
            created_at=_ts(168),
            interview_state=InterviewState.COMPLETED,
            interview_updated_at=_ts(72),
            feedback_due_at=_ts(24),  # Expired 24h ago
            manager_notes=f"[{_ts(48)}] Sent follow-up email to recruiter",
            system_notes=f"[{_ts(168)}] Imported from Submissions folder\n[{_ts(72)}] Interview marked completed — 48h feedback timer started\n[{_ts(24)}] 48h feedback timer EXPIRED — escalated to Feedback Due",
            latest_update="48h feedback window expired — follow-up required",
            latest_sender="hr.us@tcs.com",
            latest_timestamp=_ts(72),
            timeline=[
                TimelineEntry(entry_id="te-002a", record_id="syn-rec-002", sender="tarun@clifyx.com", timestamp=_ts(168), body_preview="Submission: Priya Patel for React Frontend Architect at Apple", classification="Submission", to_recipients=["hr.us@tcs.com"], cc_recipients=["lead.recruiter@tcs.com"], graph_immutable_id="AAMkMsg002a"),
                TimelineEntry(entry_id="te-002b", record_id="syn-rec-002", sender="hr.us@tcs.com", timestamp=_ts(144), body_preview="Acknowledged. Under review.", classification="Acknowledgement", to_recipients=["tarun@clifyx.com"], cc_recipients=["lead.recruiter@tcs.com"], graph_immutable_id="AAMkMsg002b"),
                TimelineEntry(entry_id="te-002c", record_id="syn-rec-002", sender="hr.us@tcs.com", timestamp=_ts(72), body_preview="Interview completed on July 28. Awaiting client feedback.", classification="InterviewCompleted", to_recipients=["tarun@clifyx.com"], cc_recipients=["lead.recruiter@tcs.com"], graph_immutable_id="AAMkMsg002c"),
            ],
        ),
        # 3. Manager Action Required — status updated to Manager Action Required
        SubmissionRecord(
            id="syn-rec-003",
            graph_immutable_id="AAMkSynth003",
            conversation_id="AAQkSynthConv003",
            job_id="991284",
            ep_reference="EP2026RA1122334",
            candidate_name="Alex Mercer",
            skill="Senior DevOps / Kubernetes",
            customer="Walmart",
            location="Sunnyvale, CA",
            domain_status=DomainStatus.MANAGER_ACTION_REQUIRED,
            received_at=_ts(96),
            created_at=_ts(96),
            interview_state=InterviewState.REQUESTED,
            interview_updated_at=_ts(48),
            feedback_due_at=None,
            manager_notes="",
            system_notes=f"[{_ts(96)}] Imported from Submissions folder\n[{_ts(48)}] Interview requested by client — awaiting manager scheduling confirmation",
            latest_update="Client requested interview — manager action required to confirm schedule",
            latest_sender="recruiter@tcs.com",
            latest_timestamp=_ts(48),
            timeline=[
                TimelineEntry(entry_id="te-003a", record_id="syn-rec-003", sender="tarun@clifyx.com", timestamp=_ts(96), body_preview="Submission: Alex Mercer for DevOps at Walmart", classification="Submission", to_recipients=["recruiter@tcs.com"], cc_recipients=[], graph_immutable_id="AAMkMsg003a"),
                TimelineEntry(entry_id="te-003b", record_id="syn-rec-003", sender="recruiter@tcs.com", timestamp=_ts(48), body_preview="Client would like to schedule an interview with Alex Mercer. Please provide availability.", classification="InterviewRequestScheduled", to_recipients=["tarun@clifyx.com"], cc_recipients=[], graph_immutable_id="AAMkMsg003b"),
            ],
        ),
        # 4. In Evaluation — client feedback received
        SubmissionRecord(
            id="syn-rec-004",
            graph_immutable_id="AAMkSynth004",
            conversation_id="AAQkSynthConv004",
            job_id="553901",
            ep_reference="EP2026RA5567788",
            candidate_name="Sarah Kim",
            skill="Data Engineer / PySpark",
            customer="JPMC",
            location="Plano, TX",
            domain_status=DomainStatus.IN_EVALUATION,
            received_at=_ts(48),
            created_at=_ts(48),
            system_notes=f"[{_ts(48)}] Imported from Submissions folder\n[{_ts(24)}] Interview scheduled for Aug 5, 2026",
            latest_update="Interview scheduled — Aug 5, 2026 10:00 AM ET",
            latest_sender="recruiter@tcs.com",
            latest_timestamp=_ts(24),
            timeline=[
                TimelineEntry(entry_id="te-004a", record_id="syn-rec-004", sender="tarun@clifyx.com", timestamp=_ts(48), body_preview="Submission: Sarah Kim for Data Scientist at JPMorgan", classification="Submission", to_recipients=["recruiter@tcs.com"], cc_recipients=["team@tcs.com"], graph_immutable_id="AAMkMsg004a"),
                TimelineEntry(entry_id="te-004b", record_id="syn-rec-004", sender="recruiter@tcs.com", timestamp=_ts(24), body_preview="Interview scheduled for August 5, 2026 at 10:00 AM ET.", classification="InterviewRequestScheduled", to_recipients=["tarun@clifyx.com"], cc_recipients=["team@tcs.com"], graph_immutable_id="AAMkMsg004b"),
            ],
        ),
        # 5. Needs Review
        SubmissionRecord(
            id="syn-rec-005",
            graph_immutable_id="AAMkSynth005",
            conversation_id="AAQkSynthConv005",
            job_id="882100",
            ep_reference="EP2026RA3344556",
            candidate_name="Raj Verma",
            skill="Cloud Security Architect",
            customer="Goldman Sachs",
            location="Dallas, TX",
            domain_status=DomainStatus.NEEDS_REVIEW,
            received_at=_ts(72),
            created_at=_ts(72),
            interview_state=InterviewState.NOT_CONFIRMED,
            interview_updated_at=_ts(12),
            manager_notes="",
            system_notes=f"[{_ts(72)}] Imported from Submissions folder\n[{_ts(12)}] Interview not confirmed by candidate — needs review",
            latest_update="Interview not confirmed — candidate unresponsive",
            latest_sender="recruiter@tcs.com",
            latest_timestamp=_ts(12),
            timeline=[
                TimelineEntry(entry_id="te-005a", record_id="syn-rec-005", sender="tarun@clifyx.com", timestamp=_ts(72), body_preview="Submission: Raj Verma for Cloud Security Architect at Goldman Sachs", classification="Submission", to_recipients=["recruiter@tcs.com"], cc_recipients=[], graph_immutable_id="AAMkMsg005a"),
                TimelineEntry(entry_id="te-005b", record_id="syn-rec-005", sender="recruiter@tcs.com", timestamp=_ts(48), body_preview="Under evaluation. Will schedule interview.", classification="InEvaluation", to_recipients=["tarun@clifyx.com"], cc_recipients=[], graph_immutable_id="AAMkMsg005b"),
                TimelineEntry(entry_id="te-005c", record_id="syn-rec-005", sender="recruiter@tcs.com", timestamp=_ts(12), body_preview="Interview invitation sent but candidate has not confirmed.", classification="NeedsReview", to_recipients=["tarun@clifyx.com"], cc_recipients=[], graph_immutable_id="AAMkMsg005c"),
            ],
        ),
        # 6. Closed
        SubmissionRecord(
            id="syn-rec-006",
            graph_immutable_id="AAMkSynth006",
            conversation_id="AAQkSynthConv006",
            job_id="660444",
            ep_reference="EP2026RA7788990",
            candidate_name="Maria Santos",
            skill="SAP FICO Consultant",
            customer="Deloitte",
            location="Chicago, IL",
            domain_status=DomainStatus.CLOSED,
            received_at=_ts(240),
            created_at=_ts(240),
            interview_state=InterviewState.COMPLETED,
            interview_updated_at=_ts(192),
            feedback_due_at=_ts(144),
            close_reason="Position closed",
            close_note=None,
            closed_at=_ts(120),
            manager_notes=f"[{_ts(130)}] Position filled by another vendor",
            system_notes=f"[{_ts(240)}] Imported from Submissions folder\n[{_ts(192)}] Interview completed\n[{_ts(144)}] Feedback received — position closed\n[{_ts(120)}] Record closed: Position closed",
            latest_update="Position filled — record closed",
            latest_sender="recruiter@tcs.com",
            latest_timestamp=_ts(144),
            timeline=[
                TimelineEntry(entry_id="te-006a", record_id="syn-rec-006", sender="tarun@clifyx.com", timestamp=_ts(240), body_preview="Submission: Maria Santos for SAP FICO Consultant at Deloitte", classification="Submission", to_recipients=["recruiter@tcs.com"], cc_recipients=[], graph_immutable_id="AAMkMsg006a"),
                TimelineEntry(entry_id="te-006c", record_id="syn-rec-006", sender="recruiter@tcs.com", timestamp=_ts(192), body_preview="Interview completed on July 24. Will share feedback.", classification="InterviewCompleted", to_recipients=["tarun@clifyx.com"], cc_recipients=[], graph_immutable_id="AAMkMsg006c"),
                TimelineEntry(entry_id="te-006d", record_id="syn-rec-006", sender="recruiter@tcs.com", timestamp=_ts(144), body_preview="Position has been filled by another vendor. Thank you for your submission.", classification="PositionClosed", to_recipients=["tarun@clifyx.com"], cc_recipients=[], graph_immutable_id="AAMkMsg006d"),
            ],
        ),
        # 7. Expired Record (Retention Expiry Review Test Record)
        SubmissionRecord(
            id="syn-rec-007",
            graph_immutable_id="AAMkSynth007",
            conversation_id="AAQkSynthConv007",
            job_id="330192",
            ep_reference="EP2026RA0099887",
            candidate_name="David Chen",
            skill="Solution Architect / Microservices",
            customer="Cisco",
            location="San Jose, CA",
            domain_status=DomainStatus.CLOSED,
            received_at="2026-04-01T09:00:00Z",
            created_at="2026-04-01T09:00:00Z",
            close_reason="Position closed",
            close_note="Hired internal candidate",
            closed_at="2026-04-12T14:00:00Z",
            manager_notes="[2026-04-12] Position filled by internal candidate",
            system_notes="[2026-04-01T09:00:00Z] Imported from Submissions folder\n[2026-04-10T10:00:00Z] Rejection received",
            latest_update="Position closed — 3-month retention window expired",
            latest_sender="recruiter@tcs.com",
            latest_timestamp="2026-04-10T10:00:00Z",
            attachment_count=2,
            attachment_hashes=["e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "f2ca1bb6c7e907d06dafe4687e579fce76b37e4e93b7605022da52e6ccc26fd2"],
            timeline=[
                TimelineEntry(entry_id="te-007a", record_id="syn-rec-007", sender="tarun@clifyx.com", timestamp="2026-04-01T09:00:00Z", body_preview="Submission: David Chen for Solution Architect at Cisco", classification="Submission", to_recipients=["recruiter@tcs.com"], cc_recipients=[], graph_immutable_id="AAMkMsg007a"),
                TimelineEntry(entry_id="te-007b", record_id="syn-rec-007", sender="recruiter@tcs.com", timestamp="2026-04-10T10:00:00Z", body_preview="Client selected internal candidate. Thank you for your submission.", classification="Rejection", to_recipients=["tarun@clifyx.com"], cc_recipients=[], graph_immutable_id="AAMkMsg007b"),
            ],
        ),
    ]
    return records
    return records


def get_synthetic_dashboard_summary() -> DashboardSummary:
    """Build dashboard summary from synthetic records."""
    records = get_synthetic_records()
    summary = DashboardSummary(auth_status="synthetic_test_data")
    headers = []
    for r in records:
        if r.domain_status == DomainStatus.AWAITING_FEEDBACK:
            summary.awaiting_feedback += 1
        elif r.domain_status == DomainStatus.PENDING_FOLLOW_UP:
            summary.pending_follow_up += 1
        elif r.domain_status == DomainStatus.FEEDBACK_DUE:
            summary.feedback_due += 1
        elif r.domain_status == DomainStatus.MANAGER_ACTION_REQUIRED:
            summary.manager_action_required += 1
        elif r.domain_status == DomainStatus.IN_EVALUATION:
            summary.in_evaluation += 1
        elif r.domain_status == DomainStatus.NEEDS_REVIEW:
            summary.needs_review += 1
        elif r.domain_status == DomainStatus.CLOSED:
            summary.closed += 1
        summary.total += 1
        headers.append(SubmissionRecordHeader(
            id=r.id,
            graph_immutable_id=r.graph_immutable_id,
            conversation_id=r.conversation_id,
            job_id=r.job_id,
            ep_reference=r.ep_reference,
            candidate_name=r.candidate_name,
            domain_status=r.domain_status,
            received_at=r.received_at,
            created_at=r.created_at,
        ))
    summary.records = headers
    return summary


def get_synthetic_record_by_id(record_id: str) -> SubmissionRecord | None:
    """Get a single synthetic record by ID."""
    for r in get_synthetic_records():
        if r.id == record_id:
            return r
    return None
