# Veridex

**Version:** 1.3 (In Progress)  
**Status:** Core Architecture Implemented  

---

Planning: see [TODO.md](TODO.md) for active work items and the Apps SDK / app-in-ChatGPT path.

---

# Overview

Veridex is a **structured AI operating environment** built around a workspace-based architecture.

Rather than interacting with a traditional chatbot, users operate inside a **virtual office environment** composed of:

- Rooms  
- Personas  
- Artifacts  
- Commands  
- Workspace state  

Veridex provides a **governed execution environment** designed to prevent conversational drift, enforce architectural discipline, and support complex workflows.

Veridex behaves more like an **operating system for workspaces** than a conversational assistant.

---

# Core Concepts

## Workspace

A workspace is the primary container for system state.

Workspace state may include:

- active room  
- active persona  
- transcript pointer  
- task queue  
- artifact references  
- overlays (Navigator / Nancy)

Workspace state is owned by the **workspace kernel**.

---

## Rooms

Rooms are stateless execution environments.

Examples:

- Lobby  
- My Office  
- Marketing  
- Archive  
- Engineering  

Rooms:

- read workspace state  
- execute domain logic  
- return responses  
- do not store persistent state  

---

## Personas

Rooms may operate through personas.

Examples:

- Receptionist  
- Nancy (Executive Assistant)  
- Archivist  
- Engineer  

Only **one room persona** may be active at a time.

---

## Navigator

Navigator is the governance layer.

Responsibilities:

- enforce system rules  
- prevent invalid operations  
- maintain scope boundaries  
- detect conflicts  

Navigator oversees the system but does not execute operational tasks.

---

## Nancy

Nancy is the administrative assistant layer.

Responsibilities:

- artifact retrieval  
- task coordination  
- workspace briefing  
- operational assistance  

Nancy functions as:

- Room persona inside My Office  
- Overlay assistant outside My Office

---

# Architecture

Veridex follows a layered architecture:

- **FastAPI backend** for tools, request handling, workspace/session state, files, artifacts, and integrations.
- **Next.js frontend** for the lobby/chat workspace UI.
- **Workspace kernel and stores** as the source of truth for workspace, session, room, file, artifact, and transcript state.
- **Command/router layers** for deterministic system commands, while normal chat remains conversational.
- **Art Department image generation** through `office.image_generate`, backed by Gemini image models and saved as workspace files when `GEMINI_API_KEY` has image-generation quota.
- **Free-first Art Department fallback** through Microsoft Designer / Bing Image Creator when Gemini image quota is unavailable.

Art Department image workflow:

1. Ask Veridex in `art_department` for the prompt, brief, or asset direction.
2. If Gemini image generation is available, use `office.image_generate`.
3. If Gemini image quota is unavailable, use the Art Department prompt in Microsoft Designer / Bing Image Creator, download the selected image, then upload it back into Veridex.
4. Store the uploaded asset as a room-scoped Art Department file so the workspace keeps the image with the rest of the project state.
5. When quota is expected to be fixed, run `office_app\image_generation_smoke.ps1` to verify the live provider path and room-scoped file save behavior.

Department collaboration workflow:

1. Sales, Marketing, Art Department, Conference Room, Finance, Law Office, and My Office can route explicit collaboration requests through the memo system.
2. Requests like `ask marketing to turn this research into a campaign plan`, `loop in art department for launch visuals`, `send this to finance for pricing`, or `coordinate with law office on this` dispatch directly to the destination room instead of falling back to generic chat.
3. `show recent memos`, `memo inbox`, and `read memo <memo_id>` route to the memo list/read tools so the mailroom is usable from chat.
4. In `sales_department` and `marketing_room`, explicit research requests like `research demographics for family restaurants in Seattle` or `find social media trends for coffee shops` now prepare `office.search_web` directly.
5. This keeps cross-department work inside governed room boundaries without forcing the user to write literal mailroom commands.
6. The room directory and room status surface both show a short capability summary for each room so the user can see what a room is for before switching into it.

Conference Room meeting workflow:

1. In `conference_room`, explicit scheduling requests can prepare `office.calendar_create` confirmations directly.
2. Explicit agenda requests such as `create agenda quarterly planning for vendor kickoff` can save an `agenda` artifact directly in the workspace.
3. Use a concrete format such as `schedule meeting quarterly planning on 2026-07-03 from 2pm to 3pm with sam@example.com`.
4. Explicit reschedule requests such as `reschedule meeting evt_12345 to 2026-07-03 from 3pm to 4pm` can prepare `office.calendar_update` confirmations.
5. Explicit cancel requests such as `cancel meeting evt_12345` can prepare `office.calendar_cancel` confirmations.
6. Internal meeting state requests such as `start meeting vendor kickoff`, `add agenda item review launch budget`, `record decision use option b`, `add action item Sam will send notes`, `add parking lot item pricing follow-up`, and `show meeting state` persist deterministic meeting notes without creating Google Calendar events.
7. The chat toolbar shows a Meeting panel in Conference Room for persisted title/item edits, item deletion, deterministic meeting brief artifact creation, and optional AI-polished brief artifact creation.
8. Calendar actions still require the normal confirmation flow before anything is written to Google Calendar.

The current frontend chat surface has been split out of `office_app/frontend/app/chat/page.tsx` into focused components and hooks:

- chat header, toolbar, transcript, composer, document reader, room directory
- workspace/session panels
- save/load/upload/download file panels
- chat menu, file, and room-state hooks
- shared chat types and helpers

---

# Development

## Preferred Startup

```powershell
cd C:\Office-App
.\veridex.cmd restart
```

Expected local ports:

- backend: `http://127.0.0.1:8078`
- frontend: `https://127.0.0.1:3078`

## Validation

Frontend build:

```powershell
cd C:\Office-App\office_app\frontend
npm.cmd run build
```

Smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1
```

Live Google integration smoke test, after signing in and connecting Google from Profile:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\integration_smoke.ps1 -SessionId "<active-session-id>"
```

This checks the connected Google provider, Gmail search, and Calendar list paths with count-only output. It refuses Gmail send, integration confirmation, and Calendar write tools.

Backend unit tests, when backend contracts change:

```powershell
cd C:\Office-App
python -m unittest discover -s office_app/server -p "test_*.py"
```

---

# Current Checkpoint

Current development checkpoint:

- Branch: `feat/routing-followup-reliability`
- Base commit: `f6bd164 Merge pull request #1 from time2makecents-ops/fix/stabilization-setup`
- Status: PR #1 has been merged into `dev`; new stabilization work should continue in smaller focused branches.
- Current slice:
  - `/request` follow-up routing now fails closed when a short choice follow-up such as `which one?` follows an unverified/no-info entity response.
  - Anchored choice follow-ups after real numbered or plain-sentence option lists still rewrite to model prompts.
  - The change is limited to the final conversation-planner fallback in `RequestFollowupRouter`; deterministic commands, grounded search follow-ups, session-search follow-ups, and explicit search confirmations remain routed before that fallback.
  - Onboarding now lets users continue to PIN setup without a face photo when camera permission, preview, or capture fails; backend onboarding already accepts a missing `face_photo_data`.
- Fresh checks for this slice:
  - `git diff --check` passed
  - `python -m unittest discover -s office_app/server -p "test_*.py"` passed with 371 tests
  - `npm.cmd test` passed with 19 frontend tests
  - `npm.cmd run build` passed
  - `office_app/smoke_test.ps1` passed
