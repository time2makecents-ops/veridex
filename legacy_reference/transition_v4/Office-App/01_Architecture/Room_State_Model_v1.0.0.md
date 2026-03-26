Room State Model
Version: 1.0.0
Status: Active
Purpose: Prevent drift and uncontrolled room switching.

------------------------------------------------------------

I. CORE PRINCIPLE

The system operates with exactly one active_room at any given time.

All actions are evaluated against active_room.

Room changes must be explicit.
No implicit switching.
No conversational inference switching.

------------------------------------------------------------

II. STATE VARIABLE

active_room: string

Valid values:
- lobby
- payroll
- law_office
- stock_room
- facilities
- (extendable via registry)

The server is authoritative for active_room.
The user cannot spoof origin.

------------------------------------------------------------

III. ROOM SWITCH RULE

Room switching occurs only via:

office.room_set

Natural language like:
"Go to payroll"
"Let's head to the law office"

Must be parsed into an explicit room_set call.

Mailroom.dispatch does NOT change active_room.

------------------------------------------------------------

IV. DRIFT PREVENTION RULES

1. No Implicit Room Inference
The system must not switch rooms based on topic.

2. Sticky Room Behavior
All requests are interpreted within active_room until explicitly changed.

3. Dispatch Isolation
Mail dispatch:
- Invokes target room
- Returns response
- Restores original active_room

4. No Persona Bleed
Persona state does not persist across rooms unless explicitly invoked.

------------------------------------------------------------

V. SWITCH RATE CONTROL (V1 — PASSIVE MODEL)

V1 does not enforce time-based cooldown.

However, system must log:
- Every room_set
- Timestamp
- Previous room
- New room

Future versions may introduce:
- Cooldown threshold
- Escalation warning
- Multi-switch guard

------------------------------------------------------------

VI. INVALID SWITCH HANDLING

If user attempts to switch to:
- Non-existent room
- Unauthorized room

System must refuse with:

"Room not recognized. Valid rooms: [list]"

No partial switching.
No fallback guesses.

------------------------------------------------------------

VII. LOBBY BEHAVIOR

Lobby is a neutral room.

It may:
- Dispatch memos
- Set rooms
- Access read-only state tools

It does not override enforcement rules.

------------------------------------------------------------

VIII. STATE RESTORATION AFTER DISPATCH

If active_room = payroll
User dispatches memo to law_office

Execution:

1. Record from_room = payroll
2. Temporarily invoke law_office
3. Generate response
4. Restore active_room = payroll

No state mutation allowed during dispatch.

------------------------------------------------------------

IX. AUDIT REQUIREMENTS

Every state-changing action must log:

- event_type (room_set)
- previous_room
- new_room
- timestamp

Dispatch must log:

- event_type (memo_dispatch)
- from_room
- to_room
- memo_id
- timestamp

Audit log must be append-only.

------------------------------------------------------------

X. EXTENSIBILITY RULE

New rooms must be added via:

Room registry update (architecture file revision)
Version bump required if behavior changes.

------------------------------------------------------------

END OF MODEL