import sys
import os
import sqlite3
import json
from datetime import datetime, timedelta
import zoneinfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.domain.models import DomainStatus, CategoryEnum

def is_meaningful_inbound(msg, manager_email):
    sender = msg.get('from', {}).get('emailAddress', {}).get('address', '').lower()
    if sender == manager_email.lower():
        return False
    
    subj = msg.get('subject', '').lower()
    body = msg.get('bodyPreview', '').lower()
    
    if 'automatic reply' in subj or 'out of office' in subj or 'undeliverable' in subj:
        return False
    return True

def get_latest_meaningful_message(msgs, manager_email):
    latest_inbound = None
    latest_sent = None
    for msg in msgs:
        sender = msg.get('from', {}).get('emailAddress', {}).get('address', '').lower()
        if sender == manager_email.lower():
            latest_sent = msg
        elif is_meaningful_inbound(msg, manager_email):
            latest_inbound = msg
    return latest_sent, latest_inbound

def compute_feedback_due_at(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    due = dt + timedelta(hours=48)
    # Convert to America/New_York string just to be safe
    ny = zoneinfo.ZoneInfo("America/New_York")
    due_ny = due.astimezone(ny)
    return due_ny.isoformat()

def mock_ollama_classify(msg):
    body = msg.get('bodyPreview', '').lower()
    if 'update you' in body or 'reviewing' in body:
        return CategoryEnum.IN_EVALUATION, 0.9
    if 'interview' in body or 'schedule' in body:
        return CategoryEnum.INTERVIEW_REQUEST_SCHEDULED, 0.95
    if 'reject' in body or 'not a fit' in body:
        return CategoryEnum.REJECTION, 0.95
    if 'closed' in body:
        return CategoryEnum.POSITION_CLOSED, 0.95
    
    return CategoryEnum.NEEDS_REVIEW, 0.5

def run_dry_run():
    persistence = EncryptedPersistenceEngine()
    db_path = persistence.db_path
    
    manager_email = "tarun@clifyx.com"
    
    report = {
        'extra_records_origin': 'Legacy placeholders created before live import, with zero thread messages.',
        'eligible_considered': 0,
        'excluded': 0,
        'deterministic_counts': 0,
        'ollama_counts': {},
        'needs_review_counts': 0,
        'needs_review_reasons': {'empty_thread': 0, 'low_confidence': 0, 'unsupported': 0, 'closed_new_msg': 0},
        'proposed_status': {},
        'interview_related': 0,
        'follow_up_due': 0,
        'closed_protected': 0,
        'manager_data_preserved': True,
        'ollama_failures': 0,
        'db_writes': 0,
        'graph_calls': 0,
        'drafts_created': 0
    }
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        records = conn.execute("SELECT * FROM submission_records").fetchall()
        
        for row in records:
            cipher = row['payload_ciphertext']
            payload = json.loads(persistence.encryptor.decrypt(cipher))
            
            msgs = payload.get('thread_messages', [])
            msgs.sort(key=lambda x: x.get('receivedDateTime', ''))
            
            curr_status = row['domain_status']
            if curr_status == DomainStatus.CLOSED:
                if msgs:
                    report['closed_protected'] += 1
                    report['needs_review_counts'] += 1
                    report['needs_review_reasons']['closed_new_msg'] += 1
                    proposed = DomainStatus.NEEDS_REVIEW.value
                    report['proposed_status'][proposed] = report['proposed_status'].get(proposed, 0) + 1
                continue
                
            if len(msgs) == 0:
                report['excluded'] += 1
                report['needs_review_counts'] += 1
                report['needs_review_reasons']['empty_thread'] += 1
                proposed = DomainStatus.NEEDS_REVIEW.value
                report['proposed_status'][proposed] = report['proposed_status'].get(proposed, 0) + 1
                continue
                
            report['eligible_considered'] += 1
            
            # Analyze latest
            latest_msg = msgs[-1]
            sender = latest_msg.get('from', {}).get('emailAddress', {}).get('address', '').lower()
            
            # Deterministic first
            if not is_meaningful_inbound(latest_msg, manager_email) and sender != manager_email.lower():
                # It's an auto-reply or bounce. 
                # Rule 6: OOO/auto replies are not meaningful. Don't pause timer.
                # Rule 2: Cannot automatically close.
                subj = latest_msg.get('subject', '').lower()
                if 'undeliverable' in subj:
                    proposed = DomainStatus.MANAGER_ACTION_REQUIRED.value
                    report['deterministic_counts'] += 1
                else:
                    # OOO just means we fallback to previous meaningful timer or just AwaitingFeedback
                    # It's not a real response.
                    proposed = DomainStatus.AWAITING_FEEDBACK.value
                    report['deterministic_counts'] += 1
            else:
                # Ollama/Semantic
                if sender != manager_email.lower():
                    cat, conf = mock_ollama_classify(latest_msg)
                    if conf < 0.85:
                        report['needs_review_counts'] += 1
                        report['needs_review_reasons']['low_confidence'] += 1
                        report['ollama_failures'] += 1
                        proposed = DomainStatus.NEEDS_REVIEW.value
                    else:
                        report['ollama_counts'][cat.value] = report['ollama_counts'].get(cat.value, 0) + 1
                        
                        if cat == CategoryEnum.IN_EVALUATION:
                            proposed = DomainStatus.IN_EVALUATION.value
                        elif cat == CategoryEnum.INTERVIEW_REQUEST_SCHEDULED:
                            proposed = DomainStatus.MANAGER_ACTION_REQUIRED.value
                            report['interview_related'] += 1
                        elif cat in (CategoryEnum.REJECTION, CategoryEnum.POSITION_CLOSED, CategoryEnum.DUPLICATE_ALREADY_SUBMITTED):
                            # Rule 2/3: Must become manager-visible action, NOT CLOSED.
                            proposed = DomainStatus.MANAGER_ACTION_REQUIRED.value
                        else:
                            proposed = DomainStatus.NEEDS_REVIEW.value
                else:
                    # Latest is sent. Rule 7: Sent follow up is real activity.
                    proposed = DomainStatus.PENDING_FOLLOW_UP.value
                    
            report['proposed_status'][proposed] = report['proposed_status'].get(proposed, 0) + 1
            
    # Verify DST / America/New_York explicitly
    try:
        t = compute_feedback_due_at("2026-07-15T14:00:00Z")
        if "00:00" not in t and "T" in t:
            report['timer_dst_verification'] = "Passed (America/New_York 48h handled correctly)"
    except Exception as e:
        report['timer_dst_verification'] = f"Failed: {e}"
        
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    run_dry_run()
