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

Last documented stabilization checkpoint:

- Branch: `fix/stabilization-setup`
- Commit: `322c6b2 Refactor chat page cleanup`
- Status: pushed to `origin/fix/stabilization-setup`
- Fresh checks at closeout:
  - `git diff --check`
  - `npm.cmd run build`
  - `office_app/smoke_test.ps1`

Backend unit tests were not run for the chat cleanup checkpoint because no backend contracts changed.
