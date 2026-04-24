from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class HandlerDeps:
    kernel: Any
    store: Any
    pipeline: Any
    archive_service: Any
    memo_service: Any
    nancy_service: Any
    receptionist_context_service: Any
    workspace_file_service: Any
    private_file_service: Any
    search_service: Any
    ocr_service: Any
    model_router: Any
    user_service: Any
    utc_now: Callable[[], str]
    stable_state_sha: Callable[[dict], str]
    append_incident: Callable[..., str]
    error_missing_required_field: Callable[[str], Exception]
    resolve_workspace_id: Callable[[str, dict], str]
