#!/usr/bin/env python3
"""
Navigator OS Minimal - Dispatcher
Deterministic command runner for registry/state/log.
"""
from __future__ import annotations
import json, csv, sys, hashlib, subprocess, os
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
STATE_PATH = BASE / "state.json"
REGISTRY_PATH = BASE / "registry.csv"
INCIDENT_LOG = BASE / "incident_log.csv"
TESTS = BASE / "tests.py"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def load_state() -> dict:
    s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return s

def save_state(s: dict) -> None:
    s["updated_at"] = utc_now()
    STATE_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")

def state_sha(s: dict) -> str:
    return sha256_bytes(json.dumps(s, sort_keys=True).encode("utf-8"))

def cmd_system_snapshot():
    s = load_state()
    reg_bytes = REGISTRY_PATH.read_bytes()
    out = {
        "source": {"registry_path": str(REGISTRY_PATH), "registry_sha256": sha256_bytes(reg_bytes)},
        "state": s,
        "state_sha256": state_sha(s),
        "execution": {"type": "tool-backed", "ts": utc_now()}
    }
    print(json.dumps(out, indent=2))

def cmd_list_objects():
    rows = []
    with REGISTRY_PATH.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({
                "object_id": row.get("object_id",""),
                "version": row.get("version",""),
                "status": row.get("status",""),
                "tier": row.get("tier",""),
                "scope": row.get("scope",""),
            })
    out = {"registry_path": str(REGISTRY_PATH), "count": len(rows), "objects": rows}
    print(json.dumps(out, indent=2))

def cmd_show_object(object_id: str):
    with REGISTRY_PATH.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("object_id","") == object_id:
                out = {"found": True, "object": row, "registry_path": str(REGISTRY_PATH)}
                print(json.dumps(out, indent=2))
                return
    print(json.dumps({"found": False, "object_id": object_id, "registry_path": str(REGISTRY_PATH)}, indent=2))
    raise SystemExit(2)

def cmd_run_regression_audit():
    # Tool-backed: executes tests.py and returns its JSON stdout
    p = subprocess.run([sys.executable, str(TESTS), str(REGISTRY_PATH)], capture_output=True, text=True)
    out = {
        "execution": {"type": "tool-backed", "ts": utc_now(), "exit_code": p.returncode},
        "stdout": p.stdout.strip(),
        "stderr": p.stderr.strip()
    }
    print(json.dumps(out, indent=2))
    raise SystemExit(p.returncode)

def cmd_log_incident(args: dict):
    s = load_state()
    sid = state_sha(s)
    incident_id = args.get("incident_id") or f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    row = [
        incident_id,
        utc_now(),
        args.get("severity","MEDIUM"),
        args.get("class","UNCLASSIFIED"),
        args.get("rule_or_gate",""),
        args.get("command",""),
        args.get("input_ref",""),
        args.get("output_ref",""),
        args.get("evidence_path",""),
        args.get("notes",""),
        sid
    ]
    with INCIDENT_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(row)
    print(json.dumps({"appended": True, "incident_id": incident_id, "state_sha256": sid, "ts": utc_now()}, indent=2))

def cmd_show_incident_log(limit: int = 50):
    with INCIDENT_LOG.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
    out = {"count": len(rows), "tail": rows[-limit:]}
    print(json.dumps(out, indent=2))

def main():
    if len(sys.argv) < 2:
        print("Usage: dispatcher.py <COMMAND> [args]")
        print("Commands: SYSTEM_SNAPSHOT, LIST_OBJECTS, SHOW_OBJECT, RUN_REGRESSION_AUDIT, LOG_INCIDENT, SHOW_INCIDENT_LOG")
        raise SystemExit(1)

    cmd = sys.argv[1].upper()

    if cmd == "SYSTEM_SNAPSHOT":
        cmd_system_snapshot()
    elif cmd == "LIST_OBJECTS":
        cmd_list_objects()
    elif cmd == "SHOW_OBJECT":
        if len(sys.argv) < 3:
            raise SystemExit("SHOW_OBJECT requires object_id")
        cmd_show_object(sys.argv[2])
    elif cmd == "RUN_REGRESSION_AUDIT":
        cmd_run_regression_audit()
    elif cmd == "LOG_INCIDENT":
        if len(sys.argv) < 3:
            raise SystemExit("LOG_INCIDENT requires JSON args string")
        args = json.loads(sys.argv[2])
        cmd_log_incident(args)
    elif cmd == "SHOW_INCIDENT_LOG":
        limit = int(sys.argv[2]) if len(sys.argv) >= 3 else 50
        cmd_show_incident_log(limit)
    else:
        raise SystemExit(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
