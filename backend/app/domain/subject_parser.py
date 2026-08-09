"""
Subject parser module for extracting display-only metadata from email subject lines.

ACTUAL PRODUCTION FORMAT:
418326 - EP2026RA7415469 - Govinda Mundra - Technical Program Manager for AI PM - AMEX - Phoenix, AZ

MAPPING RULES:
- Position 1 (parts[0]) = Job ID (e.g., 418326, numeric or alphanumeric)
- Position 2 (parts[1]) = EP Reference (e.g., EP2026RA7415469, actual EP-style value, does not require "EP-")
- Position 3 (parts[2]) = Candidate Name (e.g., Govinda Mundra)
- Last Position (parts[-1]) = Location (e.g., Phoenix, AZ or Remote)
- Second-to-Last Position (parts[-2]) = Customer (e.g., AMEX)
- Middle Positions (parts[3:-2]) = Requirement / Skill (e.g., Technical Program Manager for AI PM, joining extra hyphens)

INVARIANTS:
1. Parsing failure MUST NOT affect message identity or TCS eligibility.
2. Job ID, EP Reference, Subject, Candidate Name, and Customer are metadata ONLY.
   They MUST NEVER be used for message association, thread linking, or reply matching.
"""

import re
from typing import Optional
from backend.app.domain.models import SubjectMetadata

EP_PATTERN = re.compile(r'(?i)\bEP-?([A-Z0-9]{4,15})\b')
JOB_PATTERN = re.compile(r'(?i)\b(?:JOB-?|REQ-?|POSITION-?|\b)([0-9]{4,8})\b')


def parse_subject_metadata(subject: str) -> SubjectMetadata:
    """
    Parse candidate name, Job ID, EP reference, requirement/skill, customer, and location.
    Uses stable positional parsing for production format, with fallback for secondary formats.
    """
    if not subject:
        return SubjectMetadata()

    metadata = SubjectMetadata()

    # Clean prefix like "TCS Submission:" or "Submissions:" if present
    cleaned_subject = re.sub(r'(?i)^\s*(?:re|fw|fwd|tcs\s+submission|submission|submissions)[:\s]*', '', subject).strip()

    # Split on a dash separator when at least one side contains whitespace.
    # Real Outlook subjects sometimes omit whitespace on one side ("-EP..."
    # or "(TPM)- Oracle") while genuine word hyphens must remain intact.
    parts = [
        p.strip()
        for p in re.split(r'(?:\s+[-–—]\s*|\s*[-–—]\s+)', cleaned_subject)
        if p.strip()
    ]

    if len(parts) >= 5:
        metadata.job_id = parts[0]
        metadata.ep_reference = parts[1]
        metadata.candidate_name = parts[2]
        metadata.location = parts[-1]
        metadata.customer = parts[-2]
        # Join any remaining middle parts as requirement/skill
        metadata.skill = " - ".join(parts[3:-2])
    elif len(parts) == 4:
        metadata.job_id = parts[0]
        metadata.ep_reference = parts[1]
        metadata.candidate_name = parts[2]
        metadata.customer = parts[3]
    else:
        # Fallback regex parser for non-standard formats
        ep_match = EP_PATTERN.search(subject)
        if ep_match:
            metadata.ep_reference = ep_match.group(0).upper()

        job_match = JOB_PATTERN.search(subject)
        if job_match:
            metadata.job_id = job_match.group(0).upper()

        clean_sub = re.sub(r'(?i)\b(?:tcs\s+submission|submission|submissions|re|fw|fwd)[:\s]*', '', subject)
        clean_sub = re.sub(r'(?i)\bEP-?[A-Z0-9]{4,15}\b', '', clean_sub)
        clean_sub = re.sub(r'(?i)\b(?:JOB-?|REQ-?)[A-Z0-9]{4,12}\b', '', clean_sub)
        sub_parts = [p.strip() for p in re.split(r'[-–—:|]', clean_sub) if p.strip()]
        if sub_parts:
            metadata.candidate_name = sub_parts[0]
        if len(sub_parts) > 1:
            metadata.skill = sub_parts[1]
        if len(sub_parts) > 2:
            metadata.customer = sub_parts[2]

    return metadata
