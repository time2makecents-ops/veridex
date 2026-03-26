-- Office App Bootstrap / Seed Script
-- Version: 1.0.0
-- Purpose: Initialize single-user workspace and default state.

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- 1) CREATE DEFAULT WORKSPACE (IF NOT EXISTS)
------------------------------------------------------------

-- In V1 we assume single-user.
-- Workspace ID can be constant, e.g., 'default_workspace'.

INSERT OR IGNORE INTO workspaces (workspace_id)
VALUES ('default_workspace');

------------------------------------------------------------
-- 2) ENSURE ROOM REGISTRY EXISTS
-- (If schema was applied first, this will no-op.)
------------------------------------------------------------

INSERT OR IGNORE INTO rooms (room_id, room_title, default_persona) VALUES
  ('lobby',      'Lobby',         'Navigator'),
  ('payroll',    'Payroll',       'Payroll'),
  ('law_office', 'The Law Office','Mr. Nice'),
  ('stock_room', 'Stock Room',    'Ira'),
  ('facilities', 'Facilities',    'Facilities');

------------------------------------------------------------
-- 3) INITIALIZE ACTIVE ROOM (IF NOT SET)
------------------------------------------------------------

INSERT OR IGNORE INTO office_state (workspace_id, active_room)
VALUES ('default_workspace', 'lobby');

------------------------------------------------------------
-- 4) BOOTSTRAP AUDIT ENTRY
------------------------------------------------------------

INSERT INTO audit_events (
  event_id,
  workspace_id,
  event_type,
  actor_type,
  details_json
)
VALUES (
  'bootstrap_' || strftime('%Y%m%d%H%M%f','now'),
  'default_workspace',
  'bootstrap_initialized',
  'system',
  '{"initial_room":"lobby"}'
);

------------------------------------------------------------
-- END OF SEED
------------------------------------------------------------