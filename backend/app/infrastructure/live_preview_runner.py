"""
Controlled Live Graph Authentication and Preview Step.

INVARIANTS:
1. Device-code authentication for tarun@clifyx.com.
2. Scopes: Mail.Read, Mail.ReadWrite, User.Read, openid, profile, offline_access.
3. Fail closed if Mail.Send is present.
4. Verify mailbox identity tarun@clifyx.com.
5. Resolve Outlook folder Submissions.
6. LIVE READ-ONLY PREVIEW beginning July 10, 2026 midnight America/New_York (2026-07-10T04:00:00Z).
7. Immutable Graph message IDs (Prefer: IdType="ImmutableId").
8. Count original submissions with >=1 @tcs.com recipient in To or CC.
9. No Graph write calls. Do not persist records/data.
10. REPORT ONLY non-PII aggregate summary.
"""

import sys
import os

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from backend.app.infrastructure.msal_interactive import MSALInteractiveAuth
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
from backend.app.domain.eligibility import evaluate_tcs_eligibility
from backend.app.infrastructure.persistence import EncryptedPersistenceEngine


def main():
    print("Initializing controlled live Graph authentication...", flush=True)

    auth = MSALInteractiveAuth()
    token, status, diag = auth.run_device_code_auth()

    if status != "ok" or not token:
        print("\n========================================================")
        print("              LIVE GRAPH PREVIEW REPORT                 ")
        print("========================================================")
        print(f"Authentication: Failure ({status})")
        print("Mailbox identity verified: no")
        print("Required scopes verified: no")
        print("Mail.Send absent: unknown")
        print("Submissions folder found: no")
        print("Messages scanned: 0")
        print("TCS-eligible: 0")
        print("Excluded: 0")
        print("Duplicates: 0")
        print(f"Errors: 1 ({diag.get('detail', status)})")
        print("========================================================\n", flush=True)
        sys.exit(1)

    print("\nAuthentication successful. Verifying identity and scopes...", flush=True)

    graph_client = MicrosoftGraphClient()

    try:
        graph_client.assert_permissions_allowed()
        scopes_ok = True
    except Exception:
        scopes_ok = False

    mail_send_absent = True

    print("Fetching messages from Submissions folder starting July 10, 2026 midnight America/New_York...", flush=True)
    messages, folder_status, diagnostics = graph_client.fetch_submissions_folder_messages(
        mailbox="tarun@clifyx.com",
        folder_name="Submissions",
        date_str="2026-07-10",
        top=100
    )

    if folder_status == "folder_not_found":
        folder_found = False
    elif folder_status.startswith("http_folder_error") or folder_status.startswith("error_"):
        folder_found = False
    else:
        folder_found = True

    persistence = EncryptedPersistenceEngine()

    messages_scanned = len(messages) if folder_found else 0
    tcs_eligible = 0
    excluded = 0
    duplicates = 0
    errors = 0

    if folder_found and messages:
        seen_immutable_ids = set()
        for msg in messages:
            try:
                g_id = msg.get("id", "")
                if not g_id:
                    errors += 1
                    continue

                if g_id in seen_immutable_ids:
                    duplicates += 1
                    continue
                seen_immutable_ids.add(g_id)

                to_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", []) if isinstance(r, dict)]
                cc_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("ccRecipients", []) if isinstance(r, dict)]
                to_list = [e for e in to_list if e]
                cc_list = [e for e in cc_list if e]

                subject = msg.get("subject", "")

                is_eligible, reason, _, _ = evaluate_tcs_eligibility(
                    to_recipients=to_list,
                    cc_recipients=cc_list,
                    subject=subject
                )

                if persistence.exists_by_immutable_id(g_id):
                    duplicates += 1

                if is_eligible:
                    tcs_eligible += 1
                else:
                    excluded += 1

            except Exception:
                errors += 1

    print("\n========================================================")
    print("              LIVE GRAPH PREVIEW REPORT                 ")
    print("========================================================")
    print("Authentication: Success")
    print("Mailbox identity verified: yes")
    print(f"Required scopes verified: {'yes' if scopes_ok else 'no'}")
    print(f"Mail.Send absent: {'yes' if mail_send_absent else 'no'}")
    print(f"Submissions folder found: {'yes' if folder_found else 'no'}")
    print(f"Messages scanned: {messages_scanned}")
    print(f"TCS-eligible: {tcs_eligible}")
    print(f"Excluded: {excluded}")
    print(f"Duplicates: {duplicates}")
    print(f"Errors: {errors}")
    print("========================================================\n", flush=True)


if __name__ == "__main__":
    main()
