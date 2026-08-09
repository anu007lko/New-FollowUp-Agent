import sys
import os
import sqlite3
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine

def main():
    persistence = EncryptedPersistenceEngine()
    db_path = persistence.db_path
    
    manager_email = "tarun@clifyx.com"
    
    stats = {
        'total_records': 0,
        'status_counts': {},
        'conv_1_msg': 0,
        'conv_multi_msg': 0,
        'conv_has_inbound': 0,
        'conv_has_sent': 0,
        'conv_has_both': 0,
        'total_messages': 0,
        'total_attachments_in_msgs': 0,
        'att_regular': 0,
        'att_inline_image_signature': 0,
        'att_item': 0,
        'att_reference': 0,
        'att_unsupported': 0,
        'decryption_failures': 0,
        'chronological_order_ok': 0,
        'chronological_order_fail': 0,
        'deterministic_ok': 0,
        'needs_ollama': 0,
        'missing_immutable_id': 0,
        'missing_conversation_id': 0,
    }
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        records = conn.execute("SELECT * FROM submission_records").fetchall()
        
        for row in records:
            stats['total_records'] += 1
            status = row['domain_status']
            stats['status_counts'][status] = stats['status_counts'].get(status, 0) + 1
            
            cipher = row['payload_ciphertext']
            try:
                decrypted = persistence.encryptor.decrypt(cipher)
                payload = json.loads(decrypted)
            except Exception:
                stats['decryption_failures'] += 1
                continue
                
            if not payload.get('graph_immutable_id'):
                stats['missing_immutable_id'] += 1
            if not payload.get('conversation_id'):
                stats['missing_conversation_id'] += 1
                
            msgs = payload.get('thread_messages', [])
            msg_count = len(msgs)
            
            if msg_count == 0:
                continue
                
            stats['total_messages'] += msg_count
            
            if msg_count == 1:
                stats['conv_1_msg'] += 1
            else:
                stats['conv_multi_msg'] += 1
                
            has_inbound = False
            has_sent = False
            
            # Sort msgs by receivedDateTime to check if they were already ordered
            msg_times = [m.get('receivedDateTime', '') for m in msgs]
            if msg_times == sorted(msg_times):
                stats['chronological_order_ok'] += 1
            else:
                stats['chronological_order_fail'] += 1
            
            is_deterministic = False
            for msg in msgs:
                sender = msg.get('from', {}).get('emailAddress', {}).get('address', '').lower()
                if sender == manager_email.lower():
                    has_sent = True
                else:
                    has_inbound = True
                    
                subj = msg.get('subject', '').lower()
                if 'automatic reply' in subj or 'out of office' in subj or 'undeliverable' in subj:
                    is_deterministic = True
                    
                atts = msg.get('attachments_metadata', [])
                for att in atts:
                    stats['total_attachments_in_msgs'] += 1
                    is_inline = att.get('isInline', False)
                    c_type = (att.get('contentType') or '').lower()
                    att_type = (att.get('@odata.type') or '').lower()
                    
                    if is_inline or 'image' in c_type:
                        stats['att_inline_image_signature'] += 1
                    elif 'itemattachment' in att_type:
                        stats['att_item'] += 1
                    elif 'referenceattachment' in att_type:
                        stats['att_reference'] += 1
                    elif 'unsupported' in att_type: # Mock condition
                        stats['att_unsupported'] += 1
                    else:
                        stats['att_regular'] += 1
                        
            if has_inbound: stats['conv_has_inbound'] += 1
            if has_sent: stats['conv_has_sent'] += 1
            if has_inbound and has_sent: stats['conv_has_both'] += 1
            
            if is_deterministic:
                stats['deterministic_ok'] += 1
            else:
                stats['needs_ollama'] += 1
            
    print(json.dumps(stats, indent=2))

if __name__ == '__main__':
    main()
