# Veridex Office App — Authoritative Paths

## Authoritative Registries
- `office_app/data/rooms.json`
- `office_app/data/personas.json`
- `office_app/data/room_policies.json`
- `office_app/backend/registry.csv`
- `office_app/backend/master_governance_registry_v1_0_0.json`
- `01_Architecture/Veridex_Governance_Guide_v1.0.0.md` (human-facing governance summary)

## Authoritative Runtime Storage
- `office_app/runtime/workspaces/`
  - `index.json`
  - `ws_<id>/state.json`
  - `ws_<id>/transcript.ndjson`
  - `ws_<id>/memos/`

## Authoritative Logging
- `office_app/backend/incident_log.csv`

## Transitional / Legacy Paths
- `office_app/runtime/memos/`
- `office_app/backend/state.json`
- `storage/state.json`
- `storage/incident_log.csv`

## Notes
Current app.py is workspace-aware.
Workspace state is authoritative.
Governance object definitions are authoritative in `office_app/backend/registry.csv`.
The JSON governance registry is a structured mirror of that CSV for deterministic lookup.
Legacy memo path exists only for compatibility with `default_workspace`.
No legacy paths should be used for new development unless explicitly required.
