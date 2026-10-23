import re

_URL_PATTERN = re.compile(r"https?://[^\s)\]>]+", re.I)
_NUMBERED_CITATION_PATTERN = re.compile(r"\[(?:\d+|source\s*\d+)\]", re.I)

_DIAGNOSIS_CLAIM_PATTERNS = (
    re.compile(r"\b(?:you (?:definitely|probably|likely) have|diagnosis is|i diagnose you with)\b", re.I),
    re.compile(r"\bthis is (?:definitely|certainly) (?:a |an )?[a-z-]+\b", re.I),
)
_PRESCRIPTION_PATTERNS = (
    re.compile(
        r"\b(?:take|start|stop|increase|decrease|use)\b.{0,60}"
        r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|μg|g|ml|tablets?|capsules?)\b",
        re.I,
    ),
    re.compile(r"\b(?:i recommend|you should take|take this|start taking)\b.{0,50}\b(?:medicine|medication|antibiotic|tablet|capsule)\b", re.I),
)
_PERSONAL_TREATMENT_REQUEST_PATTERNS = (
    re.compile(r"\b(?:what|which)\s+(?:prescription\s+)?(?:medicine|medication|drug|antibiotic|tablet|capsule)\b", re.I),
    re.compile(r"\b(?:what|which)\s+(?:is\s+)?(?:the\s+)?(?:dose|dosage)\b", re.I),
    re.compile(r"\b(?:how much|what dose)\b.{0,60}\b(?:take|medicine|medication|drug|tablet|capsule)\b", re.I),
    re.compile(r"\b(?:prescribe|prescription|dosage)\b", re.I),
    re.compile(r"\b(?:kaunsi|konsi)\s+(?:dawa|medicine|tablet)\b", re.I),
    re.compile(r"\b(?:kitni|kitna)\s+(?:dawa|dose|dosage)\b", re.I),
    re.compile(r"\bdose\b.{0,20}\b(?:batao|len[ae]|lena)\b", re.I),
)


# Detects if user prompt asks for prescriptive drug dosing or personalized medications.
def is_personal_treatment_request(message: str) -> bool:
    content = (message or "").strip()
    return any(pattern.search(content) for pattern in _PERSONAL_TREATMENT_REQUEST_PATTERNS)


# Validates that AI assistant response adheres to non-diagnostic safety and citation rules.
def is_safe_assistant_reply(reply: str, verified_sources: tuple[str, ...] = ()) -> bool:
    content = (reply or "").strip()
    if not content or any(
        pattern.search(content)
        for pattern in (*_DIAGNOSIS_CLAIM_PATTERNS, *_PRESCRIPTION_PATTERNS)
    ):
        return False
    if _NUMBERED_CITATION_PATTERN.search(content):
        return False
    approved = {source.rstrip(".,;") for source in verified_sources}
    return all(url.rstrip(".,;") in approved for url in _URL_PATTERN.findall(content))
