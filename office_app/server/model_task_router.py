from __future__ import annotations

import re


HIGH_STAKES_RE = re.compile(
    r"\b(legal|lawyer|contract|lawsuit|medical|diagnosis|medication|doctor|financial|investment|tax|"
    r"security|cybersecurity|privacy|compliance|regulated|safety|risk assessment)\b",
    re.IGNORECASE,
)
CODING_RE = re.compile(
    r"\b(code|coding|program|programming|debug|bug|refactor|repository|repo|pull request|commit|"
    r"python|javascript|typescript|react|api|database|sql|function|class|unit test|integration test|"
    r"compile|build error|stack trace|exception|implement)\b",
    re.IGNORECASE,
)
MEDIA_RE = re.compile(
    r"\b(image|photo|picture|video|footage|thumbnail|illustration|graphic|render|crop|resize|"
    r"stabilize|colour grade|color grade|background removal|animation)\b",
    re.IGNORECASE,
)
PLANNING_RE = re.compile(
    r"\b(plan|planning|strategy|strategic|roadmap|architecture|architectural|system design|design the system|"
    r"project plan|implementation plan|milestone|sequence the work|compare options|decision framework)\b",
    re.IGNORECASE,
)
SIMPLE_RE = re.compile(
    r"^\s*(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you|ok|okay|got it)"
    r"[\s!.,?]*$",
    re.IGNORECASE,
)


def classify_model_task(request_text: str, *, active_room: str = "") -> str:
    """Classify a chat turn for deterministic model selection.

    Ordering is intentional: risk-sensitive work receives the strongest policy
    even when the same request also mentions code, media, or planning.
    """

    text = str(request_text or "").strip()
    if HIGH_STAKES_RE.search(text):
        return "high_stakes"
    if CODING_RE.search(text):
        return "coding"
    if MEDIA_RE.search(text):
        return "media"
    if PLANNING_RE.search(text):
        return "planning"
    if SIMPLE_RE.fullmatch(text):
        return "simple"
    return "conversation"
