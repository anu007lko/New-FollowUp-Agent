import re
import os

files_to_fix = [
    "tests/test_authoritative_persistence_wiring.py",
    "tests/test_status_mapping_corrections.py",
    "tests/test_corrected_rules.py"
]

for file_path in files_to_fix:
    with open(file_path, "r") as f:
        content = f.read()
    
    # Add import os if not present
    if "import os" not in content:
        content = "import os\n" + content
    
    content = content.replace(
        "EncryptedPersistenceEngine()", 
        "EncryptedPersistenceEngine(db_path=os.path.expanduser('~/.recruitment_agent/records.db'))"
    )
    
    with open(file_path, "w") as f:
        f.write(content)

print("Updated test files to explicitly use the authoritative database.")
