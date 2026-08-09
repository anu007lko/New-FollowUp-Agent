import os
from backend.app.infrastructure.keychain import KeychainAdapter
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine
from backend.app.application.backup_engine import create_encrypted_backup_v2, restore_backup_to_quarantine

def run():
    print("Initializing...")
    keychain = KeychainAdapter(use_memory_fallback=False)
    db_path = os.path.expanduser("~/.recruitment_agent/records.db")
    engine = EncryptedPersistenceEngine(db_path=db_path)
    
    backup_dir = os.path.expanduser("~/.recruitment_agent/backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    print("Creating Format 2.0 Backup...")
    res = create_encrypted_backup_v2(
        persistence_engine=engine,
        manager_identity="tarun@clifyx.com",
        backup_dir=backup_dir,
        keychain_adapter=keychain
    )
    
    print(f"Backup created: {res.backup_file_path}")
    print(f"Record count: {res.record_count}")
    
    print("Restoring to quarantine to verify...")
    quarantine_dir = os.path.join(backup_dir, "quarantine_verify")
    os.makedirs(quarantine_dir, exist_ok=True)
    
    restore_res, quarantined = restore_backup_to_quarantine(
        backup_file_path=res.backup_file_path,
        manager_identity="tarun@clifyx.com",
        keychain_adapter=keychain,
        quarantine_dir=quarantine_dir
    )
    
    print(f"Quarantine restore success! Found {restore_res.quarantined_record_count} records.")

if __name__ == "__main__":
    run()
