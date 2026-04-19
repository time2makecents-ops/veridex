# Veridex TODO

## Current Focus

- Keep Veridex as the source of truth for workspace, room, persona, session, and artifact state.
- Keep the exterior terminal flow stable on mobile.
- Keep the lobby directory functional and upgradeable.
- Keep session enforcement strict in `/request`.

## Model Routing

- Keep Gemini as the primary free-tier provider.
- Keep Groq as fallback when configured.
- Keep OpenRouter as an optional adapter path.

## Apps SDK / app-in-ChatGPT Path

- Treat this as a separate client surface, not a replacement for Veridex.
- Build Veridex as an app that can run inside ChatGPT using the Apps SDK / MCP-style tool surface.
- Keep Veridex backend authority intact.
- Expose only approved actions and views through the ChatGPT app surface.
- Do not move workspace ownership, artifact ownership, or session authority into ChatGPT.
- Use the ChatGPT surface for convenience, discovery, and shared collaboration, while Veridex keeps the canonical state.

## Later UI Work

- Replace the interim lobby directory with a richer interior experience.
- Add a more complete room navigation UI after the terminal and onboarding flow are stable.
- Add a dedicated admin/control surface only if it does not weaken Navigator rules.

