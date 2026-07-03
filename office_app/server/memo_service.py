from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from office_app.server.errors import error_memo_not_found
from office_app.server.memo_store import MemoStore
from office_app.server.models import Memo
from office_app.server.room_router import normalize_external_room, validate_room
from office_app.server.subject import generate_subject


class MemoService:
    def __init__(self, store, legacy_memos_dir: Path, utc_now_fn):
        self.store = store
        self.legacy_memos_dir = legacy_memos_dir
        self.utc_now = utc_now_fn

    def memo_store_for(self, workspace_id: str) -> MemoStore:
        if workspace_id == "default_workspace" and self.legacy_memos_dir.exists():
            return MemoStore(self.legacy_memos_dir)
        return MemoStore(self.store.memos_dir(workspace_id))

    def dispatch_memo(
        self,
        *,
        workspace_id: str,
        from_room: str,
        to_room: str,
        body: str,
        explicit_persona: Optional[str],
        policy_check_fn,
        subject: Optional[str] = None,
    ) -> Dict[str, Any]:
        to_room_external = normalize_external_room(to_room)
        policy_check_fn(from_room, to_room_external)
        dest_room = validate_room(to_room_external)

        memo_subject = str(subject or "").strip() or generate_subject(body)
        memo_id = __import__("uuid").uuid4().hex
        to_persona = explicit_persona or str(dest_room.get("default_persona") or "Navigator")

        memo = Memo(
            memo_id=memo_id,
            from_room=from_room,
            to_room=to_room_external,
            to_persona=to_persona,
            subject=memo_subject,
            body=body,
            created_utc=self.utc_now(),
            thread_id=None,
        )
        self.memo_store_for(workspace_id).append(memo)
        self.store.append_transcript(workspace_id, "system", from_room, f"Memo dispatched to {to_room_external}: {memo_subject}")

        return {
            "memo_id": memo_id,
            "to_room": to_room_external,
            "to_persona": to_persona,
            "subject": memo_subject,
            "dest_room_title": dest_room["title"],
        }

    def record_memo_reply(
        self,
        *,
        workspace_id: str,
        memo_id: str,
        reply_text: str,
        reply_room: str,
        reply_persona: str,
        reply_is_refusal: bool = False,
        reply_closure_appended: bool = False,
    ) -> Dict[str, Any]:
        mstore = self.memo_store_for(workspace_id)
        memos_dir = getattr(mstore, "dir", None) or self.store.memos_dir(workspace_id)
        path = Path(memos_dir) / f"{memo_id}.json"
        if not path.exists():
            raise error_memo_not_found(memo_id)

        obj = self._read_json(path, {})
        obj["reply_text"] = str(reply_text or "").strip()
        obj["reply_room"] = str(reply_room or "").strip()
        obj["reply_persona"] = str(reply_persona or "").strip()
        obj["replied_utc"] = self.utc_now()
        obj["reply_is_refusal"] = bool(reply_is_refusal)
        obj["reply_closure_appended"] = bool(reply_closure_appended)
        path.write_text(__import__("json").dumps(obj, indent=2), encoding="utf-8")
        return obj

    def list_memos(self, workspace_id: str, limit: int) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        mstore = self.memo_store_for(workspace_id)
        memos_dir = getattr(mstore, "dir", None) or self.store.memos_dir(workspace_id)
        files = sorted(Path(memos_dir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

        rows: List[Dict[str, Any]] = []
        for p in files:
            obj = self._read_json(p, {})
            rows.append(
                {
                    "memo_id": obj.get("memo_id"),
                    "created_utc": obj.get("created_utc"),
                    "from_room": obj.get("from_room"),
                    "to_room": obj.get("to_room"),
                    "to_persona": obj.get("to_persona"),
                    "subject": obj.get("subject"),
                    "reply_status": "replied" if str(obj.get("reply_text") or "").strip() else "pending",
                    "reply_persona": obj.get("reply_persona"),
                    "reply_room": obj.get("reply_room"),
                    "replied_utc": obj.get("replied_utc"),
                    "is_refusal": bool(obj.get("reply_is_refusal")),
                }
            )
        return rows

    def get_memo(self, workspace_id: str, memo_id: str) -> Tuple[Dict[str, Any], str]:
        mstore = self.memo_store_for(workspace_id)
        memos_dir = getattr(mstore, "dir", None) or self.store.memos_dir(workspace_id)
        path = Path(memos_dir) / f"{memo_id}.json"
        if not path.exists():
            raise error_memo_not_found(memo_id)

        obj = self._read_json(path, {})
        body = obj.get("body", "")
        return obj, body

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        import json
        return json.loads(path.read_text(encoding="utf-8"))
