# Veridex

**Version:** 1.3 (In Progress)  
**Status:** Core Architecture Implemented  

---

Planning: see [TODO.md](TODO.md) for active work items and the Apps SDK / app-in-ChatGPT path.

Local Codex integration: see `C:\codex2veridex\README.md` for the two-way bridge.
It lets Codex activate a governed Veridex session and makes authenticated Codex
the primary Veridex chat provider, without an OpenAI API key. Gemini and Groq
remain available only as an explicit opt-in fallback.

The current local test build uses `VERIDEX_SINGLE_USER_MODE=true`. Opening the
web UI bypasses PIN entry and onboarding, restores the stable local Admin
account, and continues using separate workspaces and sessions. Chat turns are
still persisted to each session transcript.

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
