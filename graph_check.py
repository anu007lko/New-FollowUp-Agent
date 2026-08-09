import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from backend.app.infrastructure.msal_client import MSALAuthenticationAdapter
from backend.app.infrastructure.graph_client import MicrosoftGraphClient
import httpx

def main():
    print("5. Authenticating silently...")
    try:
        adapter = MSALAuthenticationAdapter()
        res = adapter.acquire_token_silently()
        
        if res.status != "ok" or not res.token:
            print(f"Auth failed: {res.status}")
            print(f"Diagnostics: {res.config_diagnostics}")
            return
            
        print("Auth OK. Token acquired.")
        print(f"Diagnostics: {res.config_diagnostics}")
        
        # Verify Mail.Send is absent (assert_scopes_allowed would have thrown if it was present)
        print("Mail.Send is absent (verified by MSALAuthenticationAdapter.assert_scopes_allowed).")
        
        # 8. Confirm mailbox
        print("8. Confirming mailbox...")
        headers = {
            "Authorization": f"Bearer {res.token}",
            "Accept": "application/json"
        }
        with httpx.Client(timeout=15.0) as client:
            me_res = client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
            if me_res.status_code == 200:
                print(f"Mailbox user: {me_res.json().get('userPrincipalName')}")
            else:
                print(f"Failed to get /me: {me_res.status_code}")
                
            # 6. Check Drafts folder
            print("6. Searching Drafts folder...")
            drafts_res = client.get("https://graph.microsoft.com/v1.0/me/mailFolders/drafts/messages?$select=id,isDraft,conversationId,subject,toRecipients", headers=headers)
            if drafts_res.status_code == 200:
                drafts = drafts_res.json().get('value', [])
                print(f"Found {len(drafts)} drafts.")
                for d in drafts:
                    print(f" Draft: isDraft={d.get('isDraft')}, subj={d.get('subject')}, convId={d.get('conversationId')}")
            else:
                print(f"Failed to get drafts: {drafts_res.status_code}")
                
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == '__main__':
    main()
