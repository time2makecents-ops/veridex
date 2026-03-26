-- Office App — Minimal Schema
-- Version: 1.0.0
-- Purpose: Support Room State + Mailroom Dispatch + Append-only Audit

-- NOTE (SQLite):
--   - Uses TEXT for ids (store UUIDs as TEXT).
--   - Uses CHECK constraints for basic enums.
-- NOTE (Postgres):
--   - You can replace TEXT ids with UUID type if desired.
--   - Replace datetime('now') with now().

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- 1) WORKSPACE (single-user V1, but future-proofed)
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS workspaces (
  workspace_id      TEXT PRIMARY KEY,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

------------------------------------------------------------
-- 2) ROOM REGISTRY (authoritative allowed rooms)
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rooms (
  room_id           TEXT PRIMARY KEY,
  room_title        TEXT NOT NULL,
  default_persona   TEXT NOT NULL,
  is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Seed minimal rooms (idempotent inserts)
INSERT OR IGNORE INTO rooms (room_id, room_title, default_persona) VALUES
  ('lobby',      'Lobby',        'Navigator'),
  ('payroll',    'Payroll',      'Payroll'),
  ('law_office', 'The Law Office','Mr. Nice'),
  ('stock_room', 'Stock Room',   'Ira'),
  ('facilities', 'Facilities',   'Facilities');

------------------------------------------------------------
-- 3) OFFICE STATE (one active_room per workspace)
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS office_state (
  workspace_id      TEXT PRIMARY KEY,
  active_room       TEXT NOT NULL,
  updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
  FOREIGN KEY (active_room)  REFERENCES rooms(room_id)
);

------------------------------------------------------------
-- 4) MEMOS (Mailroom Dispatch records)
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS memos (
  memo_id           TEXT PRIMARY KEY,
  workspace_id      TEXT NOT NULL,

  from_room         TEXT NOT NULL,
  to_room           TEXT NOT NULL,

  -- Persona actually used for the response (can be default or explicit)
  to_persona        TEXT NOT NULL,

  -- Auto-generated. User must not provide subject.
  subject           TEXT NOT NULL,

  -- Raw user instruction/body
  body              TEXT NOT NULL,

  -- Response characteristics
  is_refusal        INTEGER NOT NULL DEFAULT 0 CHECK (is_refusal IN (0, 1)),
  closure_appended  INTEGER NOT NULL DEFAULT 0 CHECK (closure_appended IN (0, 1)),

  -- Full formatted response text (header + persona response)
  response_text     TEXT NOT NULL,

  created_at        TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
  FOREIGN KEY (from_room)    REFERENCES rooms(room_id),
  FOREIGN KEY (to_room)      REFERENCES rooms(room_id)
);

CREATE INDEX IF NOT EXISTS idx_memos_workspace_created
ON memos (workspace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_memos_to_room_created
ON memos (to_room, created_at);

------------------------------------------------------------
-- 5) AUDIT EVENTS (append-only)
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_events (
  event_id          TEXT PRIMARY KEY,
  workspace_id      TEXT NOT NULL,

  -- Examples: 'room_set', 'memo_dispatch', 'memo_refused', 'invalid_room', 'rule_block'
  event_type        TEXT NOT NULL,

  actor_type        TEXT NOT NULL DEFAULT 'system'
    CHECK (actor_type IN ('user', 'system')),

  -- Optional linkage
  memo_id           TEXT NULL,

  -- Optional room context
  from_room         TEXT NULL,
  to_room           TEXT NULL,
  previous_room     TEXT NULL,
  new_room          TEXT NULL,

  -- Machine-readable detail blob (JSON string)
  details_json      TEXT NOT NULL DEFAULT '{}',

  created_at        TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
  FOREIGN KEY (memo_id)      REFERENCES memos(memo_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_workspace_created
ON audit_events (workspace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_event_type
ON audit_events (event_type);

------------------------------------------------------------
-- OPTIONAL: Trigger to keep workspaces.updated_at current
-- (SQLite trigger; in Postgres use a trigger function)
------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_workspace_updated_at_memos
AFTER INSERT ON memos
BEGIN
  UPDATE workspaces
     SET updated_at = datetime('now')
   WHERE workspace_id = NEW.workspace_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_workspace_updated_at_state
AFTER UPDATE ON office_state
BEGIN
  UPDATE workspaces
     SET updated_at = datetime('now')
   WHERE workspace_id = NEW.workspace_id;
END;