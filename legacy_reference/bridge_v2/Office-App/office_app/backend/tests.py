#!/usr/bin/env python3
"""
Navigator OS Minimal - Registry Regression Tests
Deterministic checks against registry.csv.
"""
from __future__ import annotations
import csv, re, sys, json, hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Tuple

REQUIRED_COLS = [
    "object_id","version","status","tier","scope","channel","owner",
    "effective_date","type","description","definition_text","definition_hash16","definition_complete"
]

ID_TOKEN_RE = re.compile(r"^[A-Z0-9-]+$")

def canonicalize(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+","-",s)
    s = re.sub(r"-+","-",s).strip("-")
    return s.upper()

@dataclass(frozen=True)
class TestResult:
    name: str
    passed: bool
    detail: str

def load_registry(path: Path) -> Tuple[List[Dict[str,str]], str]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows: List[Dict[str,str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames is None:
            raise SystemExit("Registry has no header row.")
        missing = [c for c in REQUIRED_COLS if c not in r.fieldnames]
        if missing:
            raise SystemExit(f"Missing required columns: {missing}")
        for row in r:
            rows.append(row)
    return rows, sha

def run_tests(rows: List[Dict[str,str]]) -> List[TestResult]:
    out: List[TestResult] = []

    # T01: object_id uniqueness
    ids = [r["object_id"] for r in rows]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    out.append(TestResult("T01_object_id_unique", len(dup)==0, f"duplicates={dup}"))

    # T02: definition_hash16 uniqueness among active rows
    hashes = [r["definition_hash16"] for r in rows if r.get("status","").strip().lower()=="active"]
    duph = sorted({x for x in hashes if hashes.count(x) > 1})
    out.append(TestResult("T02_hash_unique_active", len(duph)==0, f"duplicates={duph}"))

    # T03: effective_date present for active rows
    missing_dates = [r["object_id"] for r in rows if r.get("status","").strip().lower()=="active" and not str(r.get("effective_date","")).strip()]
    out.append(TestResult("T03_effective_date_present_active", len(missing_dates)==0, f"missing={missing_dates}"))

    # T04: canonical_id token compliance (recommended)
    bad = []
    for r in rows:
        canon = canonicalize(r["object_id"])
        if not ID_TOKEN_RE.match(canon):
            bad.append((r["object_id"], canon))
    out.append(TestResult("T04_canonical_id_token_ok", len(bad)==0, f"bad={bad[:10]}{' ...' if len(bad)>10 else ''}"))

    # T05: definition_complete must be TRUE-ish
    bad_comp = [r["object_id"] for r in rows if str(r.get("definition_complete","")).strip().upper() not in {"TRUE","YES","1"}]
    out.append(TestResult("T05_definition_complete_truthy", len(bad_comp)==0, f"bad={bad_comp}"))

    # T06: status must be Active/Deprecated
    bad_status = [r["object_id"] for r in rows if str(r.get("status","")).strip().lower() not in {"active","deprecated","disabled"}]
    out.append(TestResult("T06_status_enum", len(bad_status)==0, f"bad={bad_status}"))

    return out

def as_report(results: List[TestResult], registry_sha: str) -> Dict[str, Any]:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    return {
        "registry_sha256": registry_sha,
        "summary": {"passed": passed, "total": total},
        "results": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results],
        "exit_code": 0 if passed==total else 2
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: tests.py <path_to_registry_csv>")
        raise SystemExit(1)
    reg = Path(sys.argv[1])
    rows, sha = load_registry(reg)
    results = run_tests(rows)
    report = as_report(results, sha)
    print(json.dumps(report, indent=2))
    raise SystemExit(report["exit_code"])

if __name__ == "__main__":
    main()
