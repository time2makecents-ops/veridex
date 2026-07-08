# VERIDEX THREAD HANDOFF
Project: Veridex (formerly Office-App)
Developer: JR
Current branch: `feat/navigator-proactive-behavior`
Current base commit: `f6bd164 Merge pull request #1 from time2makecents-ops/fix/stabilization-setup`
Remote: tracks `origin/feat/routing-followup-reliability`
Environment: FastAPI backend + Next.js frontend
Purpose: Preserve system intent, architecture, and implementation state so development can continue in a new thread without design drift.

---

# 0. CURRENT HANDOFF SNAPSHOT

Use this when resuming on another computer.

## Current repository checkpoint

- PR #1 has been merged into `dev` at `f6bd164`.
- Branch `feat/routing-followup-reliability` starts from the merged PR #1 baseline.
- The merged stabilization baseline contains chat cleanup, request-tool extraction, runtime Git hygiene, room capability UI, governed room workflows, memo hardening, `/call` session-header propagation, and Conference Room internal meeting-state persistence through `MeetingStateStore`.
- The branch now includes the routing follow-up reliability work, the Nancy email-entry slice, the durable cross-room work context continuity slice, Navigator read-only diagnostics, Navigator allowlisted check execution, structured Navigator recommendations, and the in-app Navigator chat panel.
- The current active slice adds `office.navigator_run_check` as a governed diagnostic tool for explicit allowlisted checks such as standard smoke, work-context smoke, backend tests, and frontend build, and surfaces those recommendations in a dedicated Navigator panel.
- The routing follow-up reliability work keeps `/request` follow-up routing fail-closed for ambiguous and reflective follow-ups after unverified/no-info entity answers, while preserving anchored list, grounded search, session-search, and explicit search-confirmation follow-ups.
- The onboarding page now lets users continue to PIN setup without a face photo when camera permission, preview, or capture fails. Backend and frontend proxy onboarding were verified with missing `face_photo_data`.
- `office_app/backend/incident_log.csv` is intentionally removed from the Git index and ignored, but the local runtime file should remain on disk.

Latest validation baseline for the current Navigator allowlisted diagnostics and panel slice:

- `git diff --check` passed
- `python -m unittest discover -s office_app/server -p "test_*.py"` passed with 513 tests
- frontend targeted `vitest` helper pass completed with 57 tests
- `npm.cmd run build` passed
- `C:\Office-App\office_app\smoke_test.ps1` passed
- live `office.state_get` smoke confirmed active work context hydration
- live `office.workspace_activate` smoke confirmed activation responses carry active work context
- live `office.room_set` smoke confirmed room switches carry active work context
- live connected-account Gmail confirmation audit proved a pending Gmail send can be created, surfaced through active work, and dismissed without sending the email
- live connected-account Calendar confirmation audit proved a pending Calendar create can be created, surfaced through active work, survive a room switch, and be dismissed without creating the event
- `C:\Office-App\office_app\work_context_smoke.ps1` covers active work save, state hydration, optional managed-restart persistence, room switch hydration, session activation hydration, workspace activation hydration, completion, and active-list clearing
- Navigator diagnostics can now inspect health, tool registration, active room/persona state, safe config readiness, recent incident rows, and redacted backend/frontend log tails without arbitrary command execution.
- `office.navigator_status_report`, `office.navigator_recent_errors`, and `office.navigator_explain_error` are the current read-only Navigator diagnostics tools.
- `office.navigator_run_check` can run only explicit allowlisted checks; it does not accept arbitrary shell commands.
- `office.navigator_explain_error` now returns structured recommendations that point to allowlisted follow-up actions.
- The chat composer now includes a `Navigator` button that toggles a dedicated in-app Navigator panel for separate governance chat.

Re-run full validation after any additional backend or frontend continuity changes.

## Start

```powershell
cd C:\Office-App
.\veridex.cmd restart
```

Expected launch behavior:
- backend opens in a `cmd` window
- frontend opens as a `node` process/window
- this is intentional

Expected local ports:
- backend: `http://127.0.0.1:8078`
- frontend: `https://127.0.0.1:3078`

## Latest completed work

Frontend chat cleanup:

- Split `office_app/frontend/app/chat/page.tsx` into focused components for header, toolbar, transcript, composer, room directory, document reader, file panels, workspace panel, and session panel.
- Added chat hooks for menus, file operations, and room state.
- Added shared chat `types.ts` and `helpers.ts`.
- Kept behavior-preserving controller helpers in `page.tsx` for feedback, message append, draft state, workspace/session state, and notices.
- Preserved existing runtime behavior and validated with frontend build plus smoke test.

Integration smoke setup:

- Added `office_app/integration_smoke.ps1` for live, read-only Google integration checks.
- The script verifies connected Google status, Gmail search count, and Calendar list count for an active Veridex `session_id`.
- It refuses Gmail send, integration confirmation, and Calendar create/update/cancel paths.
- Canva connector still needs reconnect with `brandkit:read` before brand-kit smoke testing can pass.

Art Department image generation:

- Added `office.image_generate` for Art Department image prompts.
- It calls Gemini image generation and saves the generated image as a room-scoped workspace file.
- Routing sends Art Department image/picture/graphic/logo/poster requests to this tool.
- Live provider check reached Gemini but failed with quota: `You do not have enough quota to make this request.`
- `office_app\image_generation_smoke.ps1` now provides a repeatable live check for the Art Department provider path once quota or provider access changes.
- `README.md` now documents the free-first fallback: Art Department writes the prompt, the user generates/downloads the image in Microsoft Designer / Bing Image Creator, then uploads the chosen file back into Veridex as a room-scoped Art Department asset.

Department workflow routing:

- `office.room_capabilities` now returns room-specific operating notes, preferred plugins, collaborators, and approval boundaries instead of only a tool count.
- Sales, Marketing, Art Department, Conference Room, Finance, Law Office, and My Office can route explicit collaboration requests through `mailroom.dispatch`.
- Examples now covered by routing tests include `ask marketing to turn this research into a campaign plan`, `loop in art department for launch visuals`, `send this to finance for pricing`, and `coordinate with law office on this`.
- Natural-language memo access now routes `show recent memos`, `memo inbox`, and `read memo <memo_id>` to `office.memos_list` / `office.memo_get`.
- Memo list rows now include additive reply status metadata, and memo replies are sanitized so they cannot claim external side effects through the internal memo path.
- Sales and Marketing now also route explicit research requests like `research demographics for family restaurants in Seattle` and `find social media trends for coffee shops` to `office.search_web` without requiring the literal phrase `search the web`.
- The room directory and room status surface now mirror the room capability work with short per-room capability summaries in the UI.

Conference Room meeting flow:

- Conference Room can now save `agenda` artifacts from explicit requests with a usable title.
- Example supported pattern: `create agenda quarterly planning for vendor kickoff`.
- Conference Room can now prepare `office.calendar_create` confirmations from explicit scheduling requests with date and time.
- Example supported pattern: `schedule meeting quarterly planning on 2026-07-03 from 2pm to 3pm with sam@example.com`.
- Conference Room can now prepare `office.calendar_update` confirmations from explicit reschedule requests with an event id, date, and time.
- Example supported pattern: `reschedule meeting evt_12345 to 2026-07-03 from 3pm to 4pm`.
- Conference Room can now prepare `office.calendar_cancel` confirmations from explicit cancel requests with an event id.
- Example supported pattern: `cancel meeting evt_12345`.
- If the request is too vague, the router now asks for title, date, start time, and end time instead of guessing.
- Calendar writes still require the normal confirmation flow before Google Calendar is changed.
- Conference Room can now start and persist internal meeting state without creating Google Calendar events.
- Supported internal meeting-state patterns include `start meeting vendor kickoff`, `add agenda item review launch budget`, `record decision use option b`, `add action item Sam will send notes`, `add parking lot item pricing follow-up`, and `show meeting state`.
- Meeting state is file-backed per workspace through `MeetingStateStore` and tracks the active meeting per session.
- The Conference Room chat toolbar now exposes a Meeting panel for full persisted meeting editing:
  - start/load the active meeting state
  - edit the meeting title
  - add, edit, and delete agenda, decision, action-item, and parking-lot text items
  - save a deterministic `meeting_brief` artifact
  - optionally save a separate AI-polished `meeting_brief_polished` artifact linked to the deterministic source when available

Reliability checkpoint:

- `/call` now forwards `X-Session-Id` into tool arguments when `session_id` is not already present, so room switches through tool calls persist into the next `/request`.
- A user-style pass with isolated test data covered room switching, memo list/read, Sales/Marketing research routing, file upload/list/get/download, session/workspace lifecycle, calendar confirmation preparation, and Conference Room meeting-state persistence.

Nancy email compose checkpoint:

- Nancy now supports guided pending-email compose state in chat instead of treating email preparation as a one-shot routing-only flow.
- Contact cards now expose an Email action that starts the Nancy email-entry path from the selected contact.
- The current branch for this work is `feat/routing-followup-reliability`.

Durable work context continuity checkpoint:

- `WorkContextService` persists workspace work context in `work_context.json`.
- New tools are registered for `office.work_context_save`, `office.work_context_list`, and `office.work_context_complete`.
- Natural language routing supports active-work list/save/complete requests such as `what are we working on`, `track active work: ...`, `clear active work context`, and `complete active work 2`.
- `set current work to ...` now replaces the singular manual current-focus entry instead of appending another stale active item, while `track active work: ...` still appends when multiple active items are intentional.
- Active work context is injected into AI model context so room assistants can see durable work without depending only on the latest transcript.
- Nancy email compose and Gmail send-confirmation flows record active work context until completion.
- Nancy Gmail send confirmations are now restorable from active work context in the chat UI, so reloads and room/session/workspace transitions keep a confirm-send action instead of only a passive reminder.
- Pending Gmail and Calendar confirmations now also have an explicit dismissal path through `office.integration_cancel` and `/integrations/actions/{confirmation_id}/cancel`, so confirmation work can be cleared cleanly instead of being hidden with a generic `Done` action.
- Pending Nancy compose state is now hydrated through `office.state_get`, `office.room_set`, `office.session_activate`, `office.workspace_activate`, and session/workspace switch responses so the chat UI can show a durable “Nancy draft in progress” panel with the right next-step guidance after reload or navigation.
- Pending replacement-session naming state is now hydrated from backend session/workspace state as well, so the existing session-name modal can reappear after reload or session/workspace navigation instead of relying only on local React state.
- Pending session-rename state is now hydrated from backend session/workspace state and can reopen the same session-name modal in explicit rename mode after reload, navigation, or a fresh rename clarification response.
- Pending session-list confirmation state is now hydrated from backend session/workspace state and shown in the chat UI as explicit `List Sessions` / `Not Now` actions, so the session-list follow-up survives reload or navigation instead of depending on remembered yes/no context.
- Pending workspace-switch confirmations are now hydrated from backend session/workspace state and shown in the chat UI as explicit `Switch Now` / `Stay Here` actions, so workspace-creation follow-ups survive reload or navigation instead of depending on remembered yes/no context.
- Pending room-navigation confirmations are now hydrated from backend session/workspace state and shown in the chat UI as explicit `Move Now` / `Stay Here` actions, so conversational room moves survive reload or navigation instead of depending on remembered yes/no context.
- Cancel and negative-confirmation responses now explicitly clear stale continuity UI state for pending session prompts, pending session-list confirmations, and pending room navigation instead of relying on a later reload to remove those surfaces.
- Calendar create/update/cancel confirmations are now mirrored into durable work context and use the same active-work confirmation surface as Nancy Gmail sends, so non-Gmail integration confirmations remain actionable after reload, navigation, and restart.
- Connected-account live audits now cover both Gmail-send and Calendar-create confirmation continuity through create, persistence, room/state hydration, and dismiss cleanup without executing the external action.
- Gmail send confirmation completes the Nancy email work context after the confirmed send.
- Memo dispatch records completed work context for cross-room internal work.
- `office.state_get`, `office.room_set`, `office.session_activate`, and `office.workspace_activate` include active work context so frontend navigation can hydrate continuity from authoritative backend responses.
- The chat UI now renders an active-work strip above the room/global controls and structured work-context cards with a `Done` action.
- Frontend refreshes active work after relevant chat/tool actions and immediately consumes active-work state from room/session/workspace transitions.
- `office_app\work_context_smoke.ps1` is the repeatable live check for the continuity contract, and `-RestartBackend` verifies persistence through the managed `veridex.ps1 restart` path.

Next optional cleanup:

- Continue only if more refinement is worth the token/time cost.
- Workspace/session lifecycle logic has been split into focused hooks.
- `/request` tool-route execution is now split into `request_tool_execution.py`, so search/tool orchestration no longer lives inline in `app.py`.
- Minimal frontend helper coverage now runs through `npm.cmd test` with `vitest`.
- `office_app/backend/incident_log.csv` is now intended to stay local runtime state and is removed from the Git index without deleting the local file.
- Re-run the full backend, frontend, build, and smoke validation set after backend cleanup is complete.
- Avoid broad refactors unless a failing behavior or specific feature requires them.

## Last verified behavior

- session delete works and removes the session row plus transcript folder
- the delete confirmation popup is intentional
- `delete 1` on a workspace object list now deletes the actual workspace artifact
- `what objects are saved in this session` shows session facts only
- `what objects are saved in this workspace` shows workspace artifacts
- `what objects are saved in this room` routes to the active room's behavior memories
- room behavior memories and persona behavior memories are separate
- session objects are derived from transcript facts, not stored as standalone session rows

## Preserve these scope boundaries

- workspace objects
- session objects
- room behavior memories
- persona behavior memories

# 1. SYSTEM PURPOSE

Veridex is an **operating environment accessed through conversational interaction**.

Instead of interacting with a traditional application UI, the user operates inside a **structured office environment** composed of rooms, assistants, and departments.

The system combines:

• conversational interface  
• structured office model  
• modular backend services  

The goal is to create a **persistent work environment** where projects, artifacts, assistants, and commands coexist in a structured system rather than disconnected chat threads.

Veridex should behave more like an **operating system for workspaces** than a chatbot.

---

# 2. INTERACTION MODEL

The office metaphor is **structural**, not cosmetic.

Users interact with the system through:

### Rooms
Rooms represent functional areas.

Examples:
- Lobby
- My Office
- Marketing Department
- Engineering Lab
- Records Archive

Rules:

• only one room is active at a time  
• entering a new room closes the previous room  
• rooms expose specialized capabilities  

---

### Personas

Rooms contain personas responsible for tasks.

Examples:

Receptionist  
Nancy (executive assistant)  
Archivist  
Engineer  

Rules:

• persona behavior belongs to the room  
• personas should not overlap responsibilities  
• personas represent system authority for their domain  

---

### Nancy

Nancy is the **Executive Assistant persona**.

Rules:

• Nancy resides in **My Office**
• Nancy can be accessed globally
• Nancy assists with coordination, retrieval, and organization

Nancy does NOT replace the command router or system authority.

Implementation note:
- room behavior memories are saved as workspace artifacts and linked to a room
- persona behavior memories are also saved as artifacts, but they guide style rather than replace the room
- room behavior memory lists should stay room-scoped
- workspace object lists should stay workspace-scoped
- session object lists should stay session-scoped

---

### Artifacts

Artifacts are structured outputs produced by the system.

Examples:

reports  
design documents  
exports  
audit files  

Artifacts must be storable in the Records Archive.

---

# 3. COMMAND MODEL

Commands are routed through a **Command Router**.

Commands are intentionally simple and conversational.

Examples:

go to marketing department  
list commands  
show audit  
save that  

Rules:

• commands route through router authority  
• commands should require minimal syntax  
• commands should feel conversational  

---

# 4. SAVE BEHAVIOR

Save is a **system-level command**.

User phrase:

save that

Behavior:

1. system captures the last produced artifact
2. router calls archive_service
3. artifact stored in Records Archive
4. Archivist confirms storage

Save should require **no additional confirmation unless ambiguity exists**.

---

# 5. CORE ARCHITECTURE

Current backend structure:

office_app/
server/

app.py  
command_router.py  
request_pipeline.py  
workspace_kernel.py  
workspace_store.py  
memo_service.py  
archive_service.py  
nancy_service.py  
tools_registry.py  
errors.py  

---

# 6. KEY COMPONENTS

### FastAPI Server

File: app.py

Responsibilities:

• HTTP endpoints  
• tool discovery  
• command execution  

---

### Command Router

File: command_router.py

Responsibilities:

• register commands  
• route commands to handlers  

Example registration:

router.register("office.workspaces_list", handler)

The router replaces conditional routing previously located in app.py.

---

### Tools Registry

File: tools_registry.py

Responsibilities:

• command registration  
• command discovery  
• /tools endpoint  

---

### Workspace Kernel

File: workspace_kernel.py

Responsibilities:

• active workspace state  
• workspace lifecycle control  

---

### Workspace Store

File: workspace_store.py

Responsibilities:

• workspace persistence  
• workspace lookup  
• workspace listing  

---

### Request Pipeline

File: request_pipeline.py

Responsibilities:

• normalize responses  
• enforce consistent response structure  

---

### Archive Service

File: archive_service.py

Responsibilities:

• artifact storage  
• artifact retrieval  

Supports the **Records Archive** concept.

---

### Nancy Service

File: nancy_service.py

Responsibilities:

• assistant coordination  
• document retrieval  
• task assistance  

Nancy is accessible globally but conceptually resides in **My Office**.

---

### Memo Service

File: memo_service.py

Responsibilities:

• inter-room communication  
• internal message routing  

Implements the **mailroom concept**.

---

### Error System

File: errors.py

Responsibilities:

• structured error responses  
• consistent error codes  

---

# 7. WORK COMPLETED IN THIS THREAD

Major architectural work completed:

• command router implemented  
• router separated from app.py  
• workspace kernel separated from persistence  
• tools registry centralized  
• archive service modularized  
• Nancy service modularized  
• request pipeline standardized  

Documentation created:

SOURCES.md  
VERIDEX_ARCHITECTURE_OVERVIEW.md  
V1_VS_CURRENT_ARCHITECTURE_AUDIT.md  
BEHAVIORAL_CONTRACT.md  

This thread also produced:

VERIDEX_THREAD_HANDOFF.md

---

# 8. ISSUES ENCOUNTERED AND RESOLVED

Router registration error:

NameError: router not defined

Cause:
command registration occurred before router initialization.

Resolution:
router initialization corrected.

---

Import path error:

ModuleNotFoundError: office_app

Cause:
running uvicorn from wrong working directory.

Resolution:
run uvicorn from project root.

---

# 9. CURRENT SYSTEM STATUS

Architecture: stable  
Router: operational  
Workspace system: functional  
Command discovery: functional  

Project state: **ready for feature expansion**

---

# 10. KNOWN DESIGN RULES

Important system behavior rules established in this thread:

• router is central command authority  
• commands should be conversational  
• rooms define capability scope  
• artifacts must be archivable  
• save that → automatic archive  

---

# 11. NEXT DEVELOPMENT TARGETS

Recommended next steps:

### Artifact System

Track artifacts produced by commands.

---

### Archive Integration

Connect artifact capture to:

save that

---

### Room Model

Implement formal room state management.

---

### Persona Layer

Explicit persona definitions and authority mapping.

---

### System Map

Create visual architecture documentation.

---

# 12. GUIDING PRINCIPLE

Veridex is **not a chatbot wrapper**.

It is a **workspace operating environment with conversational access**.

Architecture decisions must preserve:

• command router authority  
• modular services  
• artifact archive  
• room-based interaction model
