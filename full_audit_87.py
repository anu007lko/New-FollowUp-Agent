import sys
import os
import sqlite3
import json
from datetime import datetime, timezone
import zoneinfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.infrastructure.ollama_client import OllamaAdvisoryClient
from backend.app.domain.models import DomainStatus, CategoryEnum, TimelineEntry

NY_TZ = zoneinfo.ZoneInfo("America/New_York")

def parse_iso(dt_str):
    if not dt_str:
        return None
    dt_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_str)
    return dt.astimezone(NY_TZ)

def is_auto_reply(msg):
    subj = (msg.get('subject') or '').lower()
    body = (msg.get('bodyPreview') or '').lower()
    if 'automatic reply' in subj or 'out of office' in subj or 'undeliverable' in subj or 'auto-reply' in subj or 'autoreply' in subj:
        return True
    if 'out of office' in body and 'thanks for your mail' in body:
        return True
    return False

def run_real_ollama_audit(persistence=None, ref_time_ny=None):
    if ref_time_ny is None:
        ref_time_ny = datetime.now(NY_TZ)
        
    if persistence is None:
        persistence = EncryptedPersistenceEngine()
        
    ollama_client = OllamaAdvisoryClient()
    ollama_available = ollama_client.is_available()
    
    manager_email = "tarun@clifyx.com"
    
    records_87 = []
    placeholders_2 = []
    
    with sqlite3.connect(persistence.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM submission_records").fetchall()
        
        for r in rows:
            cipher = r['payload_ciphertext']
            payload = json.loads(persistence.encryptor.decrypt(cipher))
            msgs = payload.get('thread_messages', [])
            
            item = {
                'id': r['id'],
                'domain_status': r['domain_status'],
                'received_at': r['received_at'],
                'created_at': r['created_at'],
                'msgs': msgs,
                'payload': payload
            }
            
            if msgs is None or len(msgs) == 0:
                placeholders_2.append(item)
            else:
                records_87.append(item)
    
    # Reconciliation maps
    classifications_count = {}
    workflow_status_count = {}
    needs_review_reasons = {}
    
    timer_source_breakdown = {
        'original_submission': 0,
        'manager_followup': 0,
        'meaningful_inbound': 0,
        'interview_event': 0,
        'none_unresolved': 0
    }
    
    auto_replies_ignored = 0
    low_confidence_error_count = 0
    
    for idx, rec in enumerate(records_87):
        msgs = rec['msgs']
        msgs.sort(key=lambda m: m.get('receivedDateTime') or m.get('sentDateTime') or '')
        
        # Count auto-replies
        for m in msgs:
            if is_auto_reply(m):
                auto_replies_ignored += 1
                
        # Chronology check: original submission vs manager follow-up
        orig_submission_msg = msgs[0]
        orig_submission_time = parse_iso(orig_submission_msg.get('sentDateTime') or orig_submission_msg.get('receivedDateTime') or rec['received_at'])
        
        # Check for genuine manager follow-ups (sent after original submission)
        manager_followups = []
        meaningful_inbounds = []
        
        for m in msgs[1:]:
            sender = (m.get('from', {}).get('emailAddress', {}).get('address') or '').lower()
            if sender == manager_email.lower():
                manager_followups.append(m)
            elif not is_auto_reply(m):
                meaningful_inbounds.append(m)
                
        latest_manager_followup = manager_followups[-1] if manager_followups else None
        latest_meaningful_inbound = meaningful_inbounds[-1] if meaningful_inbounds else None
        
        # Build timeline entries for Ollama
        timeline = []
        for i, m in enumerate(msgs):
            sender = (m.get('from', {}).get('emailAddress', {}).get('address') or '')
            ts = (m.get('receivedDateTime') or m.get('sentDateTime') or '')
            body = (m.get('bodyPreview') or '')
            timeline.append(TimelineEntry(
                entry_id=m.get('id', f'msg_{i}'),
                record_id=rec['id'],
                sender=sender,
                timestamp=ts,
                body_preview=body
            ))
            
        # Check deterministic bounce first
        last_msg = msgs[-1]
        last_subj = (last_msg.get('subject') or '').lower()
        
        if 'undeliverable' in last_subj:
            category = CategoryEnum.UNRELATED
            conf = 1.0
            is_uncertain = False
        else:
            # Run actual local Ollama inference
            if ollama_available:
                llm_res = ollama_client.analyze_conversation(
                    timeline=timeline,
                    candidate_name=rec['payload'].get('metadata', {}).get('candidate_name'),
                    job_id=rec['payload'].get('metadata', {}).get('job_id')
                )
                category = llm_res.category
                conf = llm_res.confidence
                is_uncertain = llm_res.is_uncertain
            else:
                category = CategoryEnum.NEEDS_REVIEW
                conf = 0.0
                is_uncertain = True
                
        # Category string for reporting
        cat_str = category.value if isinstance(category, CategoryEnum) else str(category)
        classifications_count[cat_str] = classifications_count.get(cat_str, 0) + 1
        
        # Determine Workflow Status with strict Precedence Rules:
        # Precedence Rule 1: Low confidence / uncertainty / NeedsReview category -> Needs Review status (takes precedence over Follow-up Due)
        if conf < 0.7 or is_uncertain or category == CategoryEnum.NEEDS_REVIEW:
            workflow_status = "Needs Review"
            low_confidence_error_count += 1
            reason = "Ollama low confidence / uncertainty / fallback" if ollama_available else "Ollama service unavailable"
            needs_review_reasons[reason] = needs_review_reasons.get(reason, 0) + 1
            timer_source_breakdown['none_unresolved'] += 1
        elif rec['domain_status'] == DomainStatus.CLOSED:
            workflow_status = "Closed"
        elif 'undeliverable' in last_subj:
            workflow_status = "Manager Action Required"
            timer_source_breakdown['none_unresolved'] += 1
        elif category in (CategoryEnum.INTERVIEW_REQUEST_SCHEDULED, CategoryEnum.POSITION_CLOSED, CategoryEnum.REJECTION, CategoryEnum.DUPLICATE_ALREADY_SUBMITTED):
            workflow_status = "Manager Action Required"
            timer_source_breakdown['none_unresolved'] += 1
        elif category == CategoryEnum.IN_EVALUATION and latest_meaningful_inbound:
            inbound_time = parse_iso(latest_meaningful_inbound.get('receivedDateTime') or latest_meaningful_inbound.get('sentDateTime'))
            hours_elapsed = (ref_time_ny - inbound_time).total_seconds() / 3600.0
            timer_source_breakdown['meaningful_inbound'] += 1
            if hours_elapsed > 48:
                workflow_status = "Follow-up Due"
            else:
                workflow_status = "In Evaluation"
        else:
            # Confidently classified as NoResponse / Acknowledgement / etc.
            # Determine timer anchor (Original submission vs. Genuine manager follow-up)
            if latest_manager_followup:
                followup_time = parse_iso(latest_manager_followup.get('sentDateTime') or latest_manager_followup.get('receivedDateTime'))
                # Check if there is a meaningful inbound after manager follow-up
                if latest_meaningful_inbound:
                    inbound_time = parse_iso(latest_meaningful_inbound.get('receivedDateTime') or latest_meaningful_inbound.get('sentDateTime'))
                    if inbound_time > followup_time:
                        anchor_time = inbound_time
                        timer_source = 'meaningful_inbound'
                    else:
                        anchor_time = followup_time
                        timer_source = 'manager_followup'
                else:
                    anchor_time = followup_time
                    timer_source = 'manager_followup'
            elif latest_meaningful_inbound:
                anchor_time = parse_iso(latest_meaningful_inbound.get('receivedDateTime') or latest_meaningful_inbound.get('sentDateTime'))
                timer_source = 'meaningful_inbound'
            else:
                anchor_time = orig_submission_time
                timer_source = 'original_submission'
                
            timer_source_breakdown[timer_source] += 1
            hours_elapsed = (ref_time_ny - anchor_time).total_seconds() / 3600.0
            
            if hours_elapsed > 48:
                workflow_status = "Follow-up Due"
            else:
                workflow_status = "Awaiting Response"
                
        workflow_status_count[workflow_status] = workflow_status_count.get(workflow_status, 0) + 1

    summary = {
        'ref_time_ny': ref_time_ny.isoformat(),
        'ollama_available': ollama_available,
        'ollama_model': 'llama3.2:latest',
        'total_db_records': len(records_87) + len(placeholders_2),
        'records_87_reconciled': len(records_87),
        'placeholders_2_count': len(placeholders_2),
        'classifications_count': classifications_count,
        'workflow_status_count': workflow_status_count,
        'needs_review_count': workflow_status_count.get("Needs Review", 0),
        'needs_review_reasons': needs_review_reasons,
        'follow_up_due_count': workflow_status_count.get("Follow-up Due", 0),
        'awaiting_response_count': workflow_status_count.get("Awaiting Response", 0),
        'in_evaluation_count': workflow_status_count.get("In Evaluation", 0),
        'interview_related_counts': {
            'interview_request': classifications_count.get(CategoryEnum.INTERVIEW_REQUEST_SCHEDULED.value, 0),
            'interview_scheduled': 0,
            'interview_awaiting_confirmation': 0
        },
        'manager_action_required_count': workflow_status_count.get("Manager Action Required", 0),
        'original_submission_anchors': timer_source_breakdown['original_submission'],
        'genuine_followup_anchors': timer_source_breakdown['manager_followup'],
        'meaningful_inbound_anchors': timer_source_breakdown['meaningful_inbound'],
        'automatic_replies_ignored': auto_replies_ignored,
        'low_confidence_error_count': low_confidence_error_count
    }
    
    return summary

if __name__ == '__main__':
    res = run_real_ollama_audit()
    print(json.dumps(res, indent=2))
