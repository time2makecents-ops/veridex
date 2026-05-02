# Veridex TODO

Last updated: 2026-05-02

## Current Focus

- Stabilize core behavior before feature expansion.
- Keep Veridex as the source of truth for workspace, session, room, file, artifact, and transcript state.
- Preserve the current stripped-down UI until backend behavior is reliable.
- Make normal chat feel conversational while keeping explicit system commands deterministic.
- Keep startup and smoke testing simple enough to diagnose without guessing.

## Immediate Priorities

1. Conversational intent layer
   - Normal chat should be the default.
   - Explicit commands should still route deterministically.
   - Ambiguous requests should ask a clarifying question.
   - Recent chat context should only be used for clear follow-ups, not broad room/capability questions.

2. Request orchestration cleanup
   - Move search result synthesis out of `app.py`.
   - Keep `/request` focused on request lifecycle and transcript recording.
   - Keep routing decisions in one testable layer.

3. Frontend chat cleanup
   - Split `chat/page.tsx` into focused pieces.
   - Suggested pieces:
     - chat transcript
     - composer
     - room directory
     - workspace/session menus
     - save/load panel
     - file reader
     - upload/download panel

4. Runtime/Git hygiene
   - Remove generated runtime state from tracked source control in a careful patch.
   - Do not delete local user data.
   - Keep `.env.local`, local certs, storage, logs, and runtime databases ignored.

5. Documentation alignment
   - Treat `SYSTEM_STATE.md` as the current implementation state.
   - Treat architecture docs as design intent unless recently updated.
   - Update handoff docs after major stabilization milestones.

## Search

Current provider order:

1. SerpAPI
2. Google Custom Search
3. DuckDuckGo fallback

Notes:

- SerpAPI is the preferred general web search path.
- Google Programmable Search whole-web mode is deprecated for new engines, so it should not be relied on as the main whole-web provider.
- DuckDuckGo remains useful as a no-key fallback.
- Search answers should be synthesized conversationally by the model instead of dumping raw result text.

## Model Providers

Current intended provider behavior:

- Gemini remains the primary conversation provider when configured.
- Groq remains a fallback when configured.
- OpenRouter remains optional and should only be used when enabled.

Keep provider configuration in `.env.local`, not in committed files.

## Startup / Operations

Preferred app restart:

```powershell
cd C:\Office-App
.\veridex.cmd restart
```

Backend manual start:

```cmd
cd /d C:\Office-App
run_server.cmd
```

Frontend manual start:

```cmd
cd /d C:\Office-App\office_app\frontend
node server.cjs
```

Smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1
```

Deep smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1 -Deep
```

## Deferred UI Work

- Visual polish.
- Room interior graphics.
- Draggable/movable page elements.
- Overlay selection tools.
- Richer room navigation.
- Dedicated admin/control panel.

Do not resume these until core chat, search, session, file, and startup behavior remain stable through repeated smoke tests.

## Do Not Do Yet

- Do not add another agent framework as a source of truth.
- Do not let browser/search tools own Veridex memory.
- Do not create separate durable room memory.
- Do not expand the UI before splitting the current chat page.
- Do not replace the router with model-only behavior; explicit commands still need backend authority.
