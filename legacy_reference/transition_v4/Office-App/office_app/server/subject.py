def generate_subject(body: str) -> str:
    """
    Deterministic V1 subject generator (non-LLM).
    """
    b = " ".join((body or "").strip().split())
    if not b:
        return "Memo"

    b_lower = b.lower()

    intent = "Discussion"
    if any(k in b_lower for k in ["define", "definition", "what is", "meaning of"]):
        intent = "Definition"
    elif any(k in b_lower for k in ["rule", "policy", "gate", "compliance", "audit"]):
        intent = "Compliance review"
    elif any(k in b_lower for k in ["risk", "exposure", "liability"]):
        intent = "Risk review"
    elif any(k in b_lower for k in ["strategy", "posture", "plan"]):
        intent = "Strategic posture"

    words = b.split()
    primary = " ".join(words[:7])[:64].rstrip()

    return f"{intent} — {primary}"
