Veridex Architecture Change Log
Version 1.3.0 — Archive & Nancy Subsystems Introduced

Date: 3/11/2026
Status: Implemented and validated

Summary

Introduced two core subsystems that restore the original Veridex office architecture while preserving the modular service structure introduced after v1.0.

The system now includes a formal Records Archive service and a Nancy assistant subsystem, both exposed through the tool surface and validated through automated testing.

This change moves the system closer to the intended Veridex operating model:

app
 ↓
request_pipeline
 ↓
workspace_kernel
 ↓
rooms
 ↓
services (nancy / archive / memo)
New Components
Records Archive Service

File:

office_app/server/archive_service.py

Responsibilities:

workspace-scoped artifact storage

artifact indexing

artifact retrieval

artifact preview generation

Artifacts are stored per workspace:

runtime/workspaces/<workspace_id>/artifacts/

Each artifact is registered in:

artifacts/index.json

Supported operations:

office.archive_store_text
office.archive_list
office.archive_get
Nancy Assistant Subsystem

File:

office_app/server/nancy_service.py

Nancy now functions as a workspace administrative assistant rather than a simple routing helper.

Nancy’s canonical home:

My Office

Operational modes:

Inside My Office
    Nancy acts as the active room persona

Outside My Office
    Nancy acts as an assistant overlay

Nancy responsibilities currently include:

artifact listing

artifact opening

workspace briefing

Supported tools:

office.nancy_artifacts_list
office.nancy_artifact_open
office.nancy_workspace_briefing
app.py Update

File updated:

office_app/server/app.py

Changes:

integrated ArchiveService

integrated NancyService

exposed new tool routes

preserved thin entrypoint architecture

Tool surface expanded to include:

office.archive_store_text
office.archive_list
office.archive_get
office.nancy_artifacts_list
office.nancy_artifact_open
office.nancy_workspace_briefing
Architectural Result

The Veridex runtime now has the following service layers:

FastAPI transport
        ↓
Request Pipeline
        ↓
Workspace Kernel
        ↓
Rooms / Personas
        ↓
Subsystem Services
    • Archive
    • Nancy
    • Memo

This restores the office operating system model while maintaining the modular separation introduced in the later architecture revisions.

Validation

Full validation script executed successfully:

test_veridex_v13.ps1

Test coverage included:

health endpoint

tool discovery

workspace creation

workspace bootstrap

room change

artifact storage

artifact retrieval

Nancy artifact access

Nancy workspace briefing

mailroom dispatch

memo retrieval

All operations completed without errors.

Next Planned Work

Nancy Phase 2 expansion:

email drafting
calendar event drafting
artifact save routing
workspace task summary

Archive Phase 2:

artifact tagging
artifact search
artifact type classification




v1.3 (In Progress)
Base Codebase Decision

The current application at:

C:\Office-App

is the authoritative base for v1.3.

Older versions are retained only as reference donors in:

legacy_reference/
    office_v1/
    bridge_v2/
    transition_v4/

No legacy version will replace the current base.

Architectural Governance Decisions
Layered Server Architecture

The server architecture is being reorganized into layered subsystems to prevent cross-dependency drift.

Target structure:
server/
    app.py

    core/
        workspace_kernel.py
        request_pipeline.py
        guards.py
        errors.py

    registry/
        room_registry.py
        persona_registry.py
        policy_registry.py

    messaging/
        memo_service.py
        memo_store.py
        subject.py

    rooms/
        lobby.py
        conference.py

    services/
        archive_service.py
        nancy_service.py
		
		Purpose:
Clear separation of responsibilities and prevention of circular dependencies.

Dependency Direction Rule

Modules may only depend on lower architectural layers.

Allowed dependency direction:

config
↓
registry
↓
core
↓
messaging
↓
rooms
↓
services
↓
transport

Upward dependencies are prohibited.

Workspace State Governance
Workspace Owns State

Persistent system state must be owned by the workspace runtime.

Examples of valid workspace state:

active_room

active_persona

overlays (Navigator / Nancy)

transcript pointer

task queue

workspace metadata

Rooms Must Not Store Persistent State

Rooms are execution contexts only.

Room modules must not maintain internal state or persistent memory.

Persistent data must reside in:

workspace runtime
memo store
transcript
archive service

Rooms act as stateless processors.

One Active Room Rule

To prevent context drift:

Only one room persona may be active at a time within a workspace.

Overlay entities such as:

Navigator

Nancy

may remain present without replacing the active room persona.

Registry Normalization

Existing server files will be renamed for clarity:

room_router.py → room_registry.py
room_policy_registry.py → policy_registry.py

Purpose: unify registry naming conventions.

Archive Service (New)

A new subsystem will be introduced:

archive_service.py

Responsibilities:

canonical artifact storage

artifact retrieval

workspace artifact index

long-term persistence

The archive is the authoritative record system.

Nancy Assistant Service (New)

Nancy becomes a system service, not a room.

nancy_service.py

Responsibilities:

retrieve artifacts

draft emails

calendar interaction

administrative coordination

Restrictions:

Nancy cannot modify governance, canonical artifacts, or room policies.

Kernel Future Capability
Multi-Agent Capability (Deferred)

The kernel will eventually support multiple internal worker contexts.

Example internal structure:

workers[]
task_queue[]

This capability will remain disabled in v1.3 to avoid complexity and persona drift.

The architecture will simply allow future expansion.

Architectural Merge Plan

The v1.3 upgrade will follow this merge order:

configuration

registry layer

execution core

room behavior

messaging layer

transport layer

new services

This order prevents cascading breakage during the merge process.

Design Principle

Rooms are execution contexts, not memory containers.

Workspace runtime and system services are responsible for all durable state.

## Cross-Room Initiation Rule

Cross-room work is initiated primarily by the user or by Nancy acting as the workspace’s executive assistant coordinator.

Rooms may recommend or request cross-room actions but do not autonomously execute cross-room coordination by default.

Navigator remains the governance layer and may approve, deny, constrain, or require confirmation for cross-room actions, but is not the normal initiator of operational work.

Current Status

v1.3 architecture planning complete.
Implementation merge in progress.