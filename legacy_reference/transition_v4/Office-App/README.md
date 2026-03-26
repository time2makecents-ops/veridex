Office App
Version: 1.0.0
Status: Development (V1 Core)

------------------------------------------------------------
OVERVIEW

Office App is a structured, room-based execution system designed to:

- Prevent conversational drift
- Prevent uncontrolled room switching
- Enforce institutional boundaries
- Provide deterministic internal memo routing
- Log all state mutations

This is not a chatbot extension.
It is a governed execution environment.

------------------------------------------------------------
CORE PRINCIPLES

1. Exactly one active_room at any time.
2. No implicit room switching.
3. Mailroom dispatch does not change active_room.
4. Memos are single-target only.
5. Destination rooms must respond immediately.
6. No back-and-forth inside Mailroom dispatch.
7. No persistence shortcut via memos.
8. All state changes are logged.

------------------------------------------------------------
PROJECT STRUCTURE

Office-App/
│
├── 01_Architecture/
│   ├── Mailroom_Dispatch_Contract_v1.0.0.md
│   └── Room_State_Model_v1.0.0.md
│
├── 02_MCP_Tools/
│   ├── office.bootstrap_v1.0.0.json
│   ├── office.state_get_v1.0.0.json
│   ├── office.room_set_v1.0.0.json
│   └── mailroom.dispatch_v1.0.0.json
│
├── 03_Database/
│   ├── schema_v1.0.0.sql
│   └── seed_v1.0.0.sql
│
├── 04_Test_Cases/
│   └── mailroom_behavior_tests_v1.0.0.md
│
└── README.md

------------------------------------------------------------
DATABASE INITIALIZATION (SQLite Example)

1. Create database:

sqlite3 office.db < 03_Database/schema_v1.0.0.sql

2. Seed:

sqlite3 office.db < 03_Database/seed_v1.0.0.sql

------------------------------------------------------------
AVAILABLE TOOLS (V1)

office.bootstrap
- Ensures workspace + room registry + default active room.
- Returns full state snapshot.

office.state_get
- Returns active_room + room registry.
- Read-only.

office.room_set
- Explicitly sets active_room.
- Logs state change.

mailroom.dispatch
- Dispatches a memo to exactly one room.
- Auto-generates subject.
- Returns required persona response.
- Does not change active_room.

------------------------------------------------------------
MAILROOM BEHAVIOR SUMMARY

- Header always emitted.
- Subject auto-generated.
- Single target only.
- Hard refusal on insufficient detail.
- Conditional closure appended only for substantive analysis.
- No questions initiated.
- No uploads requested.
- No canon mutation.
- No room switching.

------------------------------------------------------------
AUDIT MODEL

All state-changing operations append to audit_events.

Event types include:
- bootstrap_initialized
- bootstrap_loaded
- room_set
- memo_dispatch
- memo_refused
- invalid_room
- rule_block

Audit log is append-only.

------------------------------------------------------------
NEXT PHASE (IMPLEMENTATION)

Recommended next step:

Build minimal FastAPI server exposing:
- office.bootstrap
- office.state_get
- office.room_set
- mailroom.dispatch

Then connect via Apps SDK MCP server.

------------------------------------------------------------
LONG-TERM DIRECTION

V1 Goal:
Stable single-user institutional system with drift resistance.

Future versions may introduce:
- Multi-user workspace isolation
- Cooldown enforcement for rapid room switching
- Artifact Vault system
- Governance enforcement layer
- UI layer (Room Banner + Audit Viewer)

------------------------------------------------------------
END