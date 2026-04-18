from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    workspace_id: str
    type: str
    title: str
    content: str
    format: str
    status: str
    created_by: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    source_refs: List[Any] = field(default_factory=list)
    archived: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["archived"] = bool(self.archived)
        return data


@dataclass(frozen=True)
class ArtifactCreateRequest:
    workspace_id: str
    type: str
    title: str
    content: str = ""
    format: str = "text/plain"
    status: str = "active"
    created_by: str = "user"
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_refs: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ArtifactUpdateRequest:
    title: Optional[str] = None
    content: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    source_refs: Optional[List[Any]] = None


@dataclass(frozen=True)
class ArtifactAppendRequest:
    content: str
    separator: str = "\n"
    metadata: Optional[Dict[str, Any]] = None
    source_refs: Optional[List[Any]] = None
