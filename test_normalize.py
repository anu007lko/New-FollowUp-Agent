import re
_PREFIX = re.compile(r"^(?:(?:re|fw|fwd|tcs\s+submission|submission|submissions)\s*:\s*)+", re.IGNORECASE)
def normalize_full_subject(subject: str | None) -> str:
    value = _PREFIX.sub("", (subject or "").strip())
    return " ".join(value.split()).casefold()

print(normalize_full_subject("TCS Submission: 418542 - EP2026RA7308068 - Rani Ciriguri - SAP S/4HANA OTC / SD Consultant - Advantage Sales & Marketing LLC - Remote"))
print(normalize_full_subject("Re: Submissions: 418542 - EP2026RA7308068 - Rani Ciriguri - SAP S/4HANA OTC / SD Consultant - Advantage Sales & Marketing LLC - Remote"))
print(normalize_full_subject("Re: 418542 - EP2026RA7308068 - Rani Ciriguri - SAP S/4HANA OTC / SD Consultant - Advantage Sales & Marketing LLC - Remote"))
