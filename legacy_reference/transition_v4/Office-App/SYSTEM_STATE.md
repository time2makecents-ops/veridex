# Veridex Office App — System State

## Current Status
The app is currently running and smoke test passes.

## Working Features
- FastAPI server starts successfully
- `/tools` responds
- `office.workspace_new` works
- `office.workspaces_list` works
- `office.bootstrap` works
- `office.state_get` works
- `office.room_set` works
- `mailroom.dispatch` works
- `office.memos_list` works
- `office.memo_get` works
- `active_persona_profile` appears in state responses
- workspace transcript logging works
- workspace memo storage works
- incident logging works

## Active Registries
- `office_app/data/rooms.json`
- `office_app/data/personas.json`
- `office_app/data/room_policies.json`

## Active Runtime Paths
- `office_app/runtime/workspaces/`
- `office_app/backend/incident_log.csv`

## Transitional / Legacy Items
- `app.py` still contains too much orchestration logic
- `personas.json` is active, but loader logic is still inside `app.py`
- legacy `runtime/memos/` compatibility still exists
- `default_workspace` fallback still exists
- `storage/` may be legacy
- `backend/state.json` may be legacy

## Next Priorities
1. Define authoritative storage locations
2. Move persona loading into `persona_registry.py`
3. Move room loading into a dedicated registry/router layer
4. Increase room policy enforcement
5. Build Nancy routing behavior