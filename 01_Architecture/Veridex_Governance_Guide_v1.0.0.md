Veridex Governance Guide
Version: 1.0.0
Status: Active
Purpose: Human-facing summary of the rules Veridex follows.

------------------------------------------------------------

I. SYSTEM ROLE

Veridex is a structured AI operating environment, not a freeform chatbot.
Rooms, personas, tools, and workspaces operate under explicit governance rules.

------------------------------------------------------------

II. CORE RULES

1. One Active Room
At any given time, exactly one room is active.
No implicit room switching is allowed.

2. Explicit Room Changes
Rooms change only through an explicit navigation action.
Topic drift must not silently move the user into a different room.

3. Navigator Governance
Navigator is the governance authority.
Navigator enforces system rules, drift prevention, and grounded control behavior.

4. Tool Truth Boundary
If the app says something was searched, saved, listed, or executed, that action must be tool-backed or file-backed.
The system must not pretend an operation happened if it did not.

------------------------------------------------------------

III. GATES

The app uses gates to control risky or state-changing behavior.
Current workspace gate state is stored in workspace state.

Common active gates include:
- SAVE_GATE
- PREFLIGHT
- VERIFICATION

Broader governance gate definitions are stored in the governance registry.

------------------------------------------------------------

IV. MAILROOM

Mailroom dispatch does not change the active room.
It sends a structured memo to one destination room, receives that room's response, and returns control to the originating room.

------------------------------------------------------------

V. PERSISTENCE AND MEMORY

Durable behavior, artifacts, files, and session state must follow explicit storage paths.
The app must not imply persistence or canon mutation without the proper save/update path.

------------------------------------------------------------

VI. GOVERNING SOURCES

This guide is a user-facing summary.
Canonical enforcement sources remain:

- office_app/backend/registry.csv
- 01_Architecture/Room_State_Model_v1.0.0.md
- 01_Architecture/Mailroom_Dispatch_Contract_v1.0.0.md
- office_app/data/rooms.json
- office_app/data/personas.json
- workspace state.json for live gate state
