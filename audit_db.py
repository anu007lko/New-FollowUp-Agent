import sqlite3
import os
import json
import time

db_path = os.path.expanduser("~/.recruitment_agent/records.db")
stat = os.stat(db_path)
print(f"DB Path: {db_path}")
print(f"DB Size: {stat.st_size} bytes")
print(f"DB MTime: {time.ctime(stat.st_mtime)}")

with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT count(*) FROM submission_records").fetchone()[0]
    print(f"Total Records: {count}")
    
    rows = conn.execute("SELECT domain_status, count(*) FROM submission_records GROUP BY domain_status ORDER BY domain_status").fetchall()
    print("Workflow counts:")
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
    
    try:
        versions = conn.execute("SELECT record_version, count(*) FROM submission_records GROUP BY record_version").fetchall()
        print("Record Versions:")
        for r in versions:
            print(f"  Version {r[0]}: {r[1]}")
    except sqlite3.OperationalError:
        print("Record Versions: Column 'record_version' does not exist yet (expected for unmodified database).")
