Navigator OS Minimal (Deterministic Substrate v0.1)

This bundle makes your governance layer *mechanically verifiable* using files + a tiny Python dispatcher.

Files
- registry.csv            : your current Master Governance Registry (copied)
- state.json              : canonical runtime state (single source of truth)
- incident_log.csv        : append-only incident log (CSV)
- command_map.json        : derived canonical_id mapping (recommendation helper)
- tests.py                : deterministic registry regression tests
- dispatcher.py           : command dispatcher (tool-backed execution)

Quick start
1) Run a snapshot:
   python dispatcher.py SYSTEM_SNAPSHOT

2) List objects:
   python dispatcher.py LIST_OBJECTS

3) Show one object:
   python dispatcher.py SHOW_OBJECT "Command Registry"

4) Run regression audit (tests):
   python dispatcher.py RUN_REGRESSION_AUDIT

5) Append an incident (example):
   python dispatcher.py LOG_INCIDENT '{"severity":"HIGH","class":"AUTHORITY_ILLUSION","rule_or_gate":"Truth Boundary","command":"SYSTEM SNAPSHOT","evidence_path":"screenshots/breach1.png","notes":"Snapshot claimed unverified objects"}'

Design rules enforced by substrate
- Anything that says "executed" is literally tool-backed (dispatcher/tests).
- Anything "saved" is a file write (state.json / incident_log.csv / registry.csv copy).
- Audits are reproducible (same registry.csv -> same tests.py output).

Next hardening steps (not applied here)
- Introduce canonical_id column into the registry itself
- Add effective_date population + mutation workflow
- Add a signing step (hash chain) for incident_log.csv

Generated from:
/mnt/data/master_governance_registry_v1_0_0.csv
