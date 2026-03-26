from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from office_app.server.models import Memo


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MemoStore:
    """
    Phase-2: file-backed memo archive (optional use).
    Not wired into app.py yet.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append(self, memo: Memo) -> None:
        path = self.base_dir / f"{memo.memo_id}.json"
        path.write_text(memo.model_dump_json(indent=2), encoding="utf-8")

    def list_ids(self) -> List[str]:
        return [p.stem for p in self.base_dir.glob("*.json")]

    def load(self, memo_id: str) -> Optional[Memo]:
        path = self.base_dir / f"{memo_id}.json"
        if not path.exists():
            return None
        return Memo.model_validate_json(path.read_text(encoding="utf-8"))
