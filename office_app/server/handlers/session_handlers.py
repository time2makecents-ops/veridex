from __future__ import annotations

import re
from typing import Any, Dict

from fastapi import HTTPException

from office_app.server.errors import error_missing_required_field

from .dependencies import HandlerDeps


SESSION_START_RE = re.compile(
    r"^(?:new|start|create)(?:\s+a|\s+an|\s+the)?\s+session(?:\s+for|\s+about|\s+called|\s+named)?\s*(.*)$",
    re.IGNORECASE,
)


def _normalize_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return "New Session"
    if len(text) > 48:
        text = text[:48].rstrip()
    return text[:1].upper() + text[1:] if text else "New Session"


def _extract_topic(request_text: str) -> str:
    text = str(request_text or "").strip()
    if not text:
        return ""
    match = SESSION_START_RE.match(text)
    if not match:
        return ""
    remainder = str(match.group(1) or "").strip(" .,:;")
    if remainder.lower().startswith("for "):
        remainder = remainder[4:].strip(" .,:;")
    if remainder.lower().startswith("about "):
        remainder = remainder[6:].strip(" .,:;")
    return remainder


def build_session_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    FOLLOWUP_CONTEXT_RE = re.compile(
        r"\b(it|they|their|them|there|again|hours?|open|location|where|state|city|address|live music|music|events?|shows?|concerts?|website|contact|phone|owner|pricing|founded|started)\b",
        re.IGNORECASE,
    )
    FACT_SIGNAL_RE = re.compile(
        r"\b(located|location|hours?|open|address|contact|website|live music|music venue|arcade|nightclub|eugene|oregon)\b",
        re.IGNORECASE,
    )
    TIME_SIGNAL_RE = re.compile(r"\b\d{1,2}\s*(?:a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)

    def _compact_excerpt(text: str, max_chars: int = 220) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 1].rstrip() + "..."

    def _append_unique_excerpt(excerpts: list[str], text: str) -> None:
        cleaned = str(text or "").strip()
        if cleaned and cleaned not in excerpts:
            excerpts.append(cleaned)

    def _is_session_meta_text(text: str) -> bool:
        lowered = str(text or "").casefold()
        return any(
            marker in lowered
            for marker in (
                "matching session(s) for",
                "search other sessions",
                "search all sessions",
                "searching other sessions for information about",
                "searching all sessions for information about",
                "search the sessions in",
                "i've searched the sessions",
                "searched the sessions in",
                "sessions are individual chat threads",
                "here are the sessions:",
                "you are now in session",
                "what should i name the new session",
                "started new session",
                "active room set to",
                "session created:",
                "workspaces act like project folders",
            )
        )

    def _is_generic_unknown_text(text: str) -> bool:
        lowered = str(text or "").casefold()
        return (
            "don't have any verified information about" in lowered
            or "doesn't have any verified information about" in lowered
            or "do not have verified information about" in lowered
            or "does not have any verified information about" in lowered
        )

    def _row_text(row: Dict[str, Any]) -> str:
        return re.sub(r"\s+", " ", str(row.get("text") or "").strip())

    def _format_session_line(speaker: str, text: str, *, compact: bool) -> str:
        body = _compact_excerpt(text) if compact else re.sub(r"\s+", " ", str(text or "").strip())
        return f"{speaker}: {body}"

    def _assistant_candidates(rows: list[Dict[str, Any]], lowered_query: str) -> list[tuple[int, int, str, str]]:
        candidates: list[tuple[int, int, str, str]] = []
        for index, row in enumerate(rows):
            role = str(row.get("role") or "").strip().lower()
            if role != "assistant":
                continue
            text = _row_text(row)
            if not text or _is_session_meta_text(text):
                continue
            prev_user = ""
            for back in range(index - 1, -1, -1):
                if str(rows[back].get("role") or "").strip().lower() == "user":
                    prev_user = _row_text(rows[back])
                    break
            recent_context_mentions_query = any(lowered_query in _row_text(item).casefold() for item in rows[max(0, index - 6) : index])
            score = 0
            lowered_text = text.casefold()
            lowered_prev_user = prev_user.casefold()
            if lowered_query in lowered_text:
                score += 8
            if lowered_query in lowered_prev_user:
                score += 6
            elif prev_user and FOLLOWUP_CONTEXT_RE.search(prev_user) and recent_context_mentions_query:
                score += 4
            if lowered_text.startswith("search results describe"):
                score += 3
            if FACT_SIGNAL_RE.search(text):
                score += 2
            if TIME_SIGNAL_RE.search(text):
                score += 2
            if "blairally 3" in lowered_text:
                score -= 2
            if score > 0 and len(text) >= 120:
                score += 1
            if _is_generic_unknown_text(text):
                score -= 4
            if score <= 0:
                continue
            speaker = str(row.get("speaker") or row.get("role") or "Unknown").strip() or "Unknown"
            candidates.append((score, index, speaker, text))
        return candidates

    def _matched_session_excerpts(rows: list[Dict[str, Any]], lowered_query: str, *, detail: bool, expand_full: bool) -> list[str]:
        limit = 8 if detail else 1
        assistant_candidates = _assistant_candidates(rows, lowered_query)
        if assistant_candidates:
            if expand_full:
                selected = [sorted(assistant_candidates, key=lambda item: (-item[0], item[1]))[0]]
            elif detail:
                selected = sorted(assistant_candidates, key=lambda item: (-item[0], item[1]))[:limit]
            else:
                selected = [sorted(assistant_candidates, key=lambda item: (-item[0], item[1]))[0]]
            candidate_texts = [
                _format_session_line(item[2], item[3], compact=not expand_full)
                for item in selected
            ]
            if any(not _is_generic_unknown_text(text) for text in candidate_texts):
                candidate_texts = [text for text in candidate_texts if not _is_generic_unknown_text(text)]
            deduped: list[str] = []
            seen = set()
            for text in candidate_texts:
                normalized = re.sub(r"\s+", " ", text.casefold()).strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                deduped.append(text)
            return deduped[:limit]

        excerpts: list[str] = []
        for index, row in enumerate(rows):
            text = _row_text(row)
            if not text or lowered_query not in text.casefold():
                continue
            role = str(row.get("role") or "").strip().lower()
            speaker = str(row.get("speaker") or row.get("role") or "Unknown").strip() or "Unknown"
            if role == "assistant" and not _is_session_meta_text(text):
                _append_unique_excerpt(excerpts, _format_session_line(speaker, text, compact=not expand_full))
            elif role == "user":
                _append_unique_excerpt(excerpts, _format_session_line(speaker, text, compact=not expand_full))
            if len(excerpts) >= limit:
                break
        return excerpts[:limit]

    def _sorted_sessions(*, current_session_id: str, workspace_id: str, user_id: str) -> list[Dict[str, Any]]:
        rows = deps.user_service.list_sessions(user_id, workspace_id=workspace_id)
        sessions = []
        for row in rows:
            sessions.append(
                {
                    **row,
                    "active_room": row.get("active_room") or "lobby",
                    "active_persona": row.get("active_persona") or "Receptionist",
                    "is_current": row.get("session_id") == current_session_id,
                }
            )
        sessions.sort(
            key=lambda item: (
                1 if item.get("is_current") else 0,
                str(item.get("last_active_at") or ""),
                str(item.get("updated_at") or ""),
                str(item.get("created_at") or ""),
                str(item.get("session_id") or ""),
            ),
            reverse=True,
        )
        return sessions

    def _resolve_session_ref(*, current_session_id: str, workspace_id: str, user_id: str, session_ref: str) -> Dict[str, Any]:
        sessions = _sorted_sessions(current_session_id=current_session_id, workspace_id=workspace_id, user_id=user_id)
        ref = re.sub(r"\s+", " ", str(session_ref or "").strip())
        if not ref:
            raise HTTPException(status_code=400, detail="Session reference required.")
        numeric_match = re.fullmatch(r"#?(\d{1,3})", ref)
        if numeric_match:
            index = int(numeric_match.group(1))
            if 1 <= index <= len(sessions):
                return sessions[index - 1]
            raise HTTPException(status_code=404, detail=f"Session {index} was not found.")
        lowered_ref = ref.casefold()
        for session in sessions:
            title = str(session.get("title") or "").strip()
            session_id_value = str(session.get("session_id") or "").strip()
            if title.casefold() == lowered_ref or session_id_value.casefold() == lowered_ref:
                return session
        for session in sessions:
            title = str(session.get("title") or "").strip()
            session_id_value = str(session.get("session_id") or "").strip()
            if title.casefold().startswith(lowered_ref) or session_id_value.casefold().startswith(lowered_ref):
                return session
        raise HTTPException(status_code=404, detail=f"Session '{ref}' was not found.")

    def handle_sessions_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.sessions_list", args)
        user = deps.user_service.get_user_for_session(str(args.get("session_id") or "").strip())
        current_session_id = str(user.get("last_active_session_id") or "").strip()
        current_workspace = deps.kernel.get_state(workspace_id)
        sessions = _sorted_sessions(
            current_session_id=current_session_id,
            workspace_id=workspace_id,
            user_id=str(user["user_id"]),
        )
        lines = ["Here are the sessions:"]
        items = []
        for index, item in enumerate(sessions, start=1):
            title = str(item.get("title") or item.get("session_id") or f"Session {index}").strip()
            session_id = str(item.get("session_id") or "").strip()
            description = title
            if session_id and session_id != title:
                description = f"{title} ({session_id})"
            if item.get("is_current"):
                description += " [Active]"
            lines.append(f"{index}. {description}")
            items.append({"index": index, "description": description})
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "current_session_id": current_session_id,
                "current_workspace_id": current_workspace.get("workspace_id", workspace_id),
                "count": len(sessions),
                "sessions": sessions,
                "items": items,
                "response_text": "\n".join(lines),
            },
            "content": [{"type": "text", "text": "\n".join(lines)}],
        }

    def handle_sessions_search(args: Dict[str, Any]) -> Dict[str, Any]:
        current_session_id = str(args.get("session_id") or "").strip()
        if not current_session_id:
            raise error_missing_required_field("session_id")
        workspace_id = deps.resolve_workspace_id("office.sessions_search", args)
        current_user = deps.user_service.get_user_for_session(current_session_id)
        query = re.sub(r"\s+", " ", str(args.get("query") or "").strip())
        if not query:
            raise error_missing_required_field("query")
        include_current = bool(args.get("include_current"))
        detail = bool(args.get("detail"))
        expand_full = bool(args.get("expand_full"))
        target_session_id = str(args.get("target_session_id") or "").strip()
        sessions = _sorted_sessions(
            current_session_id=current_session_id,
            workspace_id=workspace_id,
            user_id=str(current_user["user_id"]),
        )
        lowered_query = query.casefold()
        matches = []
        for session in sessions:
            if not include_current and session.get("is_current"):
                continue
            session_id_value = str(session.get("session_id") or "").strip()
            if not session_id_value:
                continue
            if target_session_id and session_id_value != target_session_id:
                continue
            rows = deps.store.load_transcript(workspace_id, limit=200, session_id=session_id_value)
            excerpts = _matched_session_excerpts(rows, lowered_query, detail=detail, expand_full=expand_full)
            if excerpts:
                matches.append(
                    {
                        "session_id": session_id_value,
                        "title": str(session.get("title") or session_id_value).strip() or session_id_value,
                        "is_current": bool(session.get("is_current")),
                        "excerpts": excerpts,
                    }
                )
        scope_text = "sessions" if include_current else "other sessions"
        if not matches:
            response_text = f'No matches found in {scope_text} for "{query}".'
            return {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "session_id": current_session_id,
                    "query": query,
                    "count": 0,
                    "matches": [],
                    "expand_full": expand_full,
                    "response_text": response_text,
                },
                "content": [{"type": "text", "text": response_text}],
            }
        if expand_full and target_session_id and matches:
            match = matches[0]
            title = match["title"]
            session_id_value = match["session_id"]
            lines = [f'Here is the full response from {title} ({session_id_value}) about "{query}":']
            lines.extend(match["excerpts"])
            response_text = "\n".join(lines)
            return {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "session_id": current_session_id,
                    "query": query,
                    "count": len(matches),
                    "matches": matches,
                    "detail": detail,
                    "expand_full": expand_full,
                    "response_text": response_text,
                },
                "content": [{"type": "text", "text": response_text}],
            }
        lines = [f'I found {len(matches)} matching session(s) for "{query}":']
        items = []
        for index, match in enumerate(matches, start=1):
            title = match["title"]
            session_id_value = match["session_id"]
            first_excerpt = match["excerpts"][0]
            description = f"{title} ({session_id_value}) - {first_excerpt}"
            lines.append(f"{index}. {description}")
            if detail:
                for extra_excerpt in match["excerpts"][1:]:
                    lines.append(f"   - {extra_excerpt}")
            items.append({"index": index, "description": description})
        response_text = "\n".join(lines)
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "session_id": current_session_id,
                "query": query,
                "count": len(matches),
                "matches": matches,
                "detail": detail,
                "expand_full": expand_full,
                "items": items,
                "response_text": response_text,
            },
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_session_create(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        current_user = deps.user_service.get_user_for_session(session_id)
        workspace_id = deps.resolve_workspace_id("office.session_create", args)
        request_text = str(args.get("request_text") or "").strip()
        title = str(args.get("title") or "").strip()
        description = str(args.get("description") or "").strip()
        if not title and request_text:
            topic = _extract_topic(request_text)
            title = _normalize_title(topic or "New Session")
            description = topic or description
        title = _normalize_title(title or "New Session")
        description = description or title
        session = deps.user_service.create_session(
            user_id=str(current_user["user_id"]),
            title=title,
            description=description,
            workspace_id=workspace_id,
            workspace_label=title,
        )
        workspace_state = deps.kernel.get_state(session["active_workspace_id"])
        return {
            "structuredContent": {
                "session_id": session["session_id"],
                "workspace_id": session["active_workspace_id"],
                "title": session["title"],
                "description": session["description"],
                "workspace_state": workspace_state,
            },
            "content": [{"type": "text", "text": f"Started new session {session['title']}."}],
        }

    def handle_session_info(args: Dict[str, Any]) -> Dict[str, Any]:
        current_session_id = str(args.get("session_id") or "").strip()
        if not current_session_id:
            raise error_missing_required_field("session_id")
        session = deps.user_service.get_session(current_session_id)
        workspace_id = str(session.get("active_workspace_id") or "").strip()
        title = str(session.get("title") or current_session_id).strip() or current_session_id
        description = str(session.get("description") or "").strip()
        response_text = f'This session is called "{title}".'
        payload = {
            "session_id": session["session_id"],
            "workspace_id": workspace_id,
            "title": title,
            "description": description,
            "response_text": response_text,
        }
        return {
            "structuredContent": payload,
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_session_activate(args: Dict[str, Any]) -> Dict[str, Any]:
        current_session_id = str(args.get("session_id") or "").strip()
        session_ref = re.sub(r"\s+", " ", str(args.get("session_ref") or "").strip(" .,:;"))
        target_session_id = current_session_id
        if session_ref:
            if not current_session_id:
                raise error_missing_required_field("session_id")
            current_user = deps.user_service.get_user_for_session(current_session_id)
            workspace_id = deps.resolve_workspace_id("office.session_activate", args)
            target = _resolve_session_ref(
                current_session_id=current_session_id,
                workspace_id=workspace_id,
                user_id=str(current_user["user_id"]),
                session_ref=session_ref,
            )
            target_session_id = str(target.get("session_id") or "").strip()
        if not target_session_id:
            raise error_missing_required_field("session_id")
        session = deps.user_service.select_session_for_user(target_session_id)
        try:
            workspace_state = deps.kernel.get_state(session["active_workspace_id"])
        except HTTPException:
            workspace_state = {}
        return {
            "structuredContent": {
                "session_id": session["session_id"],
                "workspace_id": session["active_workspace_id"],
                "title": session["title"],
                "description": session["description"],
                "workspace_state": workspace_state,
            },
            "content": [{"type": "text", "text": f"You are now in session {session['title']} ({session['session_id']})."}],
        }

    def handle_session_rename(args: Dict[str, Any]) -> Dict[str, Any]:
        current_session_id = str(args.get("session_id") or "").strip()
        if not current_session_id:
            raise error_missing_required_field("session_id")
        title = str(args.get("title") or "").strip()
        if not title:
            raise error_missing_required_field("title")
        description = str(args.get("description") or "").strip()
        normalized_title = _normalize_title(title)
        normalized_description = description or normalized_title
        current_user = deps.user_service.get_user_for_session(current_session_id)
        result = deps.user_service.rename_session(
            user_id=str(current_user["user_id"]),
            session_id=current_session_id,
            title=normalized_title,
            description=normalized_description,
        )
        workspace_id = str(result.get("workspace_id") or "").strip()
        if workspace_id:
            try:
                workspace_state = deps.kernel.get_state(workspace_id)
                pending_map = workspace_state.get("pending_session_create_by_session")
                if isinstance(pending_map, dict):
                    next_map = dict(pending_map)
                    next_map.pop(current_session_id, None)
                    if next_map:
                        workspace_state["pending_session_create_by_session"] = next_map
                    else:
                        workspace_state.pop("pending_session_create_by_session", None)
                    deps.kernel.store.save_state(workspace_id, workspace_state)
            except HTTPException:
                pass
        session = result["session"]
        response_text = f"Renamed session to {session['title']}."
        return {
            "structuredContent": {
                "session_id": result["session_id"],
                "workspace_id": result["workspace_id"],
                "title": session["title"],
                "description": session["description"],
                "response_text": response_text,
            },
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_session_delete(args: Dict[str, Any]) -> Dict[str, Any]:
        current_session_id = str(args.get("session_id") or "").strip()
        if not current_session_id:
            raise error_missing_required_field("session_id")
        current_user = deps.user_service.get_user_for_session(current_session_id)
        target_session_id = str(args.get("target_session_id") or args.get("session_ref") or current_session_id).strip()
        result = deps.user_service.delete_session(
            user_id=str(current_user["user_id"]),
            session_id=target_session_id,
        )
        deleted_session = result.get("deleted_session") or {}
        active_session = result.get("session") or {}
        deleted_title = str(deleted_session.get("title") or deleted_session.get("session_id") or target_session_id).strip()
        active_title = str(active_session.get("title") or active_session.get("session_id") or "").strip()
        active_session_id = str(active_session.get("session_id") or "").strip()
        replacement_session = result.get("replacement_session") or {}
        replacement_session_id = str(replacement_session.get("session_id") or "").strip()
        created_replacement_session = bool(result.get("created_replacement_session"))
        if created_replacement_session and active_session_id == replacement_session_id and replacement_session_id:
            try:
                current_state = deps.kernel.get_state(str(result.get("workspace_id") or ""))
                pending_map = dict(current_state.get("pending_session_create_by_session") or {})
                pending_map[replacement_session_id] = {
                    "request_text": "new session",
                    "ts": deps.utc_now(),
                }
                current_state["pending_session_create_by_session"] = pending_map
                current_state.pop("pending_room_navigation", None)
                deps.kernel.store.save_state(str(result.get("workspace_id") or ""), current_state)
            except HTTPException:
                pass
        lines = [f"Deleted session {deleted_title} ({target_session_id})."]
        if active_session_id and active_session_id != target_session_id:
            lines.append(f"Active session is now {active_title} ({active_session_id}).")
        if created_replacement_session and active_session_id == replacement_session_id:
            lines.append("What should I name the new session?")
        structured = {
            "deleted_session_id": target_session_id,
            "deleted_title": deleted_title,
            "session_id": active_session_id or current_session_id,
            "workspace_id": result.get("workspace_id"),
            "title": active_title or deleted_title,
            "description": str(active_session.get("description") or ""),
            "replacement_session_id": replacement_session_id,
            "remaining_count": result.get("remaining_count", 0),
            "workspace_state": result.get("workspace_state") or {},
            "deleted_session": deleted_session,
            "active_session": active_session,
            "created_replacement_session": created_replacement_session,
        }
        response_text = "\n".join(lines)
        structured["response_text"] = response_text
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_workspace_activate(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not workspace_id:
            raise error_missing_required_field("workspace_id")
        current_user = deps.user_service.get_user_for_session(session_id)
        result = deps.user_service.activate_workspace(user_id=str(current_user["user_id"]), workspace_id=workspace_id)
        workspace_state = result["workspace_state"]
        session = result["session"]
        return {
            "structuredContent": {
                "workspace_id": result["workspace_id"],
                "session_id": session["session_id"],
                "title": session["title"],
                "description": session["description"],
                "workspace_state": workspace_state,
            },
            "content": [{"type": "text", "text": f"Activated workspace {workspace_id}."}],
        }

    return {
        "office.sessions_list": handle_sessions_list,
        "office.sessions_search": handle_sessions_search,
        "office.session_create": handle_session_create,
        "office.session_info": handle_session_info,
        "office.session_activate": handle_session_activate,
        "office.session_rename": handle_session_rename,
        "office.session_delete": handle_session_delete,
        "office.workspace_activate": handle_workspace_activate,
    }
