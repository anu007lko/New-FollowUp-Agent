"""
Deterministic TCS eligibility evaluator.

INVARIANT:
A submission is eligible ONLY when its original message has at least one @tcs.com recipient
in the To or CC list. Additional end-client co-recipients are allowed.
Messages without a @tcs.com recipient in To/CC are strictly excluded, even if the subject
contains TCS keywords.
"""

from typing import List, Tuple, Optional


def evaluate_tcs_eligibility(
    to_recipients: List[str],
    cc_recipients: List[str],
    subject: str = ""
) -> Tuple[bool, Optional[str], List[str], List[str]]:
    """
    Evaluate deterministic TCS eligibility.
    Returns: (is_eligible, exclusion_reason, tcs_recipients, co_recipients)
    """
    tcs_recipients: List[str] = []
    co_recipients: List[str] = []

    all_recipients = to_recipients + cc_recipients

    for email in all_recipients:
        clean_email = email.strip().lower()
        if clean_email.endswith("@tcs.com"):
            tcs_recipients.append(clean_email)
        else:
            co_recipients.append(clean_email)

    if tcs_recipients:
        return True, None, tcs_recipients, co_recipients
    else:
        reason = "No @tcs.com recipient in To or CC list (original message must address at least one @tcs.com recipient)."
        return False, reason, [], co_recipients
