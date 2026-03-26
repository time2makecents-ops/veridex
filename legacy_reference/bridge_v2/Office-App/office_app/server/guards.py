def ensure_single_target(room: str) -> None:
    """
    V1: One memo may target only one room.
    Rejects common multi-target patterns.
    """
    s = (room or "").strip()
    if not s:
        raise ValueError("to_room is required.")

    s_lower = s.lower()

    if "," in s:
        raise ValueError("Only one room may be targeted per memo.")
    if " and " in s_lower:
        raise ValueError("Only one room may be targeted per memo.")
    if "&" in s:
        raise ValueError("Only one room may be targeted per memo.")
