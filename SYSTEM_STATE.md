# Veridex System State

Last updated: 2026-05-02
Active branch: `ai_response_tuning`

## Current Status

Veridex is running on the current local development stack.

- Backend: `http://127.0.0.1:8078`
- Frontend: `https://127.0.0.1:3078`
- Frontend HTTPS certs are local-only mkcert files and are ignored by Git.
- Basic smoke test passes.
- Deep smoke test passes, including a real backend search call through SerpAPI.
- Backend unit tests pass.

## Current Start Commands

Preferred full app launcher:

```powershell
cd C:\Office-App
.\veridex.cmd restart
```

Manual backend:

```cmd
cd /d C:\Office-App
run_server.cmd
```

Manual frontend:

```cmd
cd /d C:\Office-App\office_app\frontend
node server.cjs
```

## Current Validation Commands

Basic runtime smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1
```

Deep runtime smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1 -Deep
```

Backend tests:

```powershell
cd C:\Office-App
python -m unittest discover office_app/server
```

Frontend build:

```powershell
cd C:\Office-App\office_app\frontend
npm.cmd run build
```

## Working Features

- FastAPI backend starts on port `8078`.
- HTTPS Next frontend starts on port `3078`.
- `/health` responds.
- `/tools` responds.
- Workspace creation, listing, selection, and activation work.
- Session creation, listing, activation, and transcript hydration work.
- Active room/persona state is restored per active session.
- Room navigation works through explicit user intent.
- Room transition messages are recorded in chat.
- Normal chat defaults to model response instead of aggressive tool routing.
- Search tools are available.
- Search provider order is `SerpAPI -> Google Custom Search -> DuckDuckGo`.
- Search results are synthesized into conversational model responses.
- File upload, scoped file listing, reader view, and download are available.
- OCR/text extraction works for uploaded documents.
- Save/load UI scopes are available for room, session, public, and private files.
- Smoke test verifies runtime ports, frontend HTTPS, backend health, tools, and search provider readiness.

## Search Provider State

Configured locally through `.env.local`:

- `SERPAPI_API_KEY`: set locally, not committed.
- `GOOGLE_SEARCH_ENGINE_ID`: set locally, not committed.
- `GEMINI_API_KEY`: set locally, not committed.

Provider behavior:

1. Use SerpAPI first for general web and review searches.
2. Fall back to Google Custom Search if configured and SerpAPI fails.
3. Fall back to DuckDuckGo HTML search if API providers are unavailable.

Google Programmable Search whole-web mode is deprecated for new engines, so Google Custom Search should be treated as secondary, not the main search solution.

## Active Registries

- `office_app/data/rooms.json`
- `office_app/data/personas.json`
- `office_app/data/room_policies.json`

## Active Runtime Paths

- `office_app/runtime/workspaces/`
- `office_app/runtime/veridex.db`
- `office_app/backend/incident_log.csv`
- `office_app/storage/`

## Current Architecture Reality

The intended model is:

- workspace = project folder
- session = thread inside a workspace
- room = stateless persona/context operating inside the active session
- files/artifacts = workspace-owned resources with scope rules

The current implementation mostly follows this model, but some orchestration remains centralized.

Known large files:

- `office_app/server/app.py`
- `office_app/server/request_pipeline.py`
- `office_app/frontend/app/chat/page.tsx`

These files are stable enough for current work but are the main maintainability risk.

## Remaining Drift / Risks

- `app.py` still contains too much orchestration.
- `request_pipeline.py` still mixes deterministic routing with conversational heuristics.
- `chat/page.tsx` still combines chat, room controls, workspace/session controls, save/load, upload/download, and reader UI.
- Runtime files are still partly tracked in Git and should be cleaned up carefully in a separate patch.
- Some architecture docs still describe older v1.3 plans and should not be treated as exact implementation state.
- The model still needs a cleaner conversational intent layer so normal chat feels more like ChatGPT while explicit commands remain backend-controlled.

## Next Priorities

1. Add a conversational intent layer before broad tool routing.
2. Split request/search synthesis out of `app.py`.
3. Split `chat/page.tsx` into focused components/hooks.
4. Clean tracked runtime/generated state from Git without deleting user data.
5. Update remaining architecture handoff docs to match the workspace/session/room model.
