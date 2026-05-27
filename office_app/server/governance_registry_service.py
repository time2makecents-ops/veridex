from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List


class GovernanceRegistryService:
    def __init__(
        self,
        *,
        registry_path: Path,
        governance_guide_path: Path,
        room_state_model_path: Path,
        mailroom_contract_path: Path,
        persona_registry_path: Path,
        room_registry_path: Path,
    ) -> None:
        self.registry_path = registry_path
        self.governance_guide_path = governance_guide_path
        self.room_state_model_path = room_state_model_path
        self.mailroom_contract_path = mailroom_contract_path
        self.persona_registry_path = persona_registry_path
        self.room_registry_path = room_registry_path

    def active_objects(self) -> List[Dict[str, str]]:
        if not self.registry_path.exists():
            return []
        with self.registry_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        return [
            {
                "object_id": str(row.get("object_id") or "").strip(),
                "version": str(row.get("version") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "tier": str(row.get("tier") or "").strip(),
                "scope": str(row.get("scope") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "definition_text": str(row.get("definition_text") or "").strip(),
            }
            for row in rows
            if str(row.get("status") or "").strip().lower() == "active"
        ]

    def active_gate_objects(self) -> List[Dict[str, str]]:
        rows = self.active_objects()
        return [
            row
            for row in rows
            if str(row.get("object_id") or "").strip().upper().startswith("GATE-")
            or str(row.get("object_id") or "").strip().upper().endswith("-GATE")
        ]
