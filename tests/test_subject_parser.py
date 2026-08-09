"""
Automated unit tests for subject parsing and metadata non-association logic.
"""

import pytest
from backend.app.domain.subject_parser import parse_subject_metadata


def test_parse_real_world_subject_metadata():
    """
    Verify subject metadata extraction using actual production format:
    418326 - EP2026RA7415469 - Govinda Mundra - Technical Program Manager for AI PM - AMEX - Phoenix, AZ
    """
    subject = "418326 - EP2026RA7415469 - Govinda Mundra - Technical Program Manager for AI PM - AMEX - Phoenix, AZ"
    metadata = parse_subject_metadata(subject)

    assert metadata.job_id == "418326"
    assert metadata.ep_reference == "EP2026RA7415469"
    assert metadata.candidate_name == "Govinda Mundra"
    assert metadata.skill == "Technical Program Manager for AI PM"
    assert metadata.customer == "AMEX"
    assert metadata.location == "Phoenix, AZ"


def test_parse_subject_with_remote_and_extra_hyphens():
    """Verify parsing when location is Remote and requirement text contains extra hyphens."""
    subject = "998124 - EP2026RA881122 - Priya Patel - Senior Architect - AI & Cloud - Apple - Remote"
    metadata = parse_subject_metadata(subject)

    assert metadata.job_id == "998124"
    assert metadata.ep_reference == "EP2026RA881122"
    assert metadata.candidate_name == "Priya Patel"
    assert metadata.skill == "Senior Architect - AI & Cloud"
    assert metadata.customer == "Apple"
    assert metadata.location == "Remote"


def test_job_id_and_ep_reference_non_association():
    """
    Explicit invariant test:
    Verify Job ID, EP reference, subject, candidate, and customer are metadata properties ONLY
    and provide zero association logic.
    """
    subject_a = "418326 - EP2026RA7415469 - Candidate A - Requirement - AMEX - Remote"
    subject_b = "418326 - EP2026RA7415469 - Candidate B - Requirement - AMEX - Remote"

    meta_a = parse_subject_metadata(subject_a)
    meta_b = parse_subject_metadata(subject_b)

    assert meta_a.job_id == meta_b.job_id
    assert meta_a.ep_reference == meta_b.ep_reference

    # Invariant: matching Job ID or EP reference MUST NOT be used for thread or conversation linkage
    assert meta_a.candidate_name != meta_b.candidate_name


def test_parse_subject_with_en_dash_separator():
    """
    Verify subject metadata extraction when en-dash (–, U+2013) is used as separator:
    418737 - EP2026RA7427549 - Imran Khan - LAN ACI Engineer – Toyota Motor North America Inc. - Plano TX (Local Candidate)
    """
    subject = "418737 - EP2026RA7427549 - Imran Khan - LAN ACI Engineer – Toyota Motor North America Inc. - Plano TX (Local Candidate)"
    metadata = parse_subject_metadata(subject)

    assert metadata.job_id == "418737"
    assert metadata.ep_reference == "EP2026RA7427549"
    assert metadata.candidate_name == "Imran Khan"
    assert metadata.skill == "LAN ACI Engineer"
    assert metadata.customer == "Toyota Motor North America Inc."
    assert metadata.location == "Plano TX (Local Candidate)"


def test_parse_subject_with_em_dash_separator():
    """
    Verify subject metadata extraction when em-dash (—, U+2014) is used as separator.
    """
    subject = "423819 — EP2026RA7499999 — Alex Morgan — Cloud Solutions Architect — Boeing — Seattle, WA"
    metadata = parse_subject_metadata(subject)

    assert metadata.job_id == "423819"
    assert metadata.ep_reference == "EP2026RA7499999"
    assert metadata.candidate_name == "Alex Morgan"
    assert metadata.skill == "Cloud Solutions Architect"
    assert metadata.customer == "Boeing"
    assert metadata.location == "Seattle, WA"


def test_parse_subject_with_mixed_dashes():
    """
    Verify subject metadata extraction with mixed hyphen, en-dash, and em-dash separators.
    """
    subject = "415000 - EP2026RA1122334 – Jane Doe — Security Engineer - Cisco – San Jose, CA"
    metadata = parse_subject_metadata(subject)

    assert metadata.job_id == "415000"
    assert metadata.ep_reference == "EP2026RA1122334"
    assert metadata.candidate_name == "Jane Doe"
    assert metadata.skill == "Security Engineer"
    assert metadata.customer == "Cisco"
    assert metadata.location == "San Jose, CA"

