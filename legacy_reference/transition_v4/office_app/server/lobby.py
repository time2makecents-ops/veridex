def lobby_welcome(user_name: str | None = None) -> str:
    if user_name:
        greet = f"Welcome, {user_name}."
    else:
        greet = "Welcome."

    return (
        f"{greet}\n\n"
        "You are currently in the Lobby.\n\n"
        "Suggested next step: attend onboarding in the Conference Room.\n\n"
        "To attend, say:\n"
        "Go to Conference Room\n"
    )
