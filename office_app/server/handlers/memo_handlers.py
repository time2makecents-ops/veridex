from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from office_app.server.dialog_contracts import DEFAULT_CONTRACT
from office_app.server.guards import ensure_single_target
from office_app.server.model_router import ModelRoutingError
from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.room_router import validate_room

from .dependencies import HandlerDeps


def _room_behavior_memory_text(*, deps: HandlerDeps, workspace_id: str, room_id: str) -> str:
    if deps.archive_service is None or deps.receptionist_context_service is None:
        return ""
    refs = deps.receptionist_context_service.room_behavior_memory_refs(
        workspace_id=workspace_id,
        room_id=room_id,
    )
    if not isinstance(refs, list):
        return ""
    lines: List[str] = []
    seen: set[Tuple[str, str]] = set()
    for ref in refs[-20:]:
        if not isinstance(ref, dict):
            continue
        artifact_id = str(ref.get("artifact_id") or "").strip()
        artifact_workspace_id = str(ref.get("workspace_id") or workspace_id).strip() or workspace_id
        key = (artifact_workspace_id, artifact_id)
        if not artifact_id or key in seen:
            continue
        seen.add(key)
        try:
            record = deps.archive_service.get_artifact(artifact_workspace_id, artifact_id)
        except Exception:
            continue
        metadata = record.get("metadata")
        content = re.sub(r"\s+", " ", str(record.get("content") or "").strip())
        if not content:
            continue
        lowered = content.lower()
        if (
            (isinstance(metadata, dict) and str(metadata.get("memory_kind") or "").strip().lower() in {"persona_behavior", "persona_style"})
            or "how to win friends and influence people" in lowered
            or "dale carnegie" in lowered
            or "48 laws of power" in lowered
            or "in mind" in lowered
            or "from now on" in lowered
            or "filter your advice" in lowered
            or "answer my sales questions" in lowered
        ):
            continue
        lines.append(f"- {content}")
    return "\n".join(lines)


def _persona_style_guidance_text(content: str) -> str:
    lowered = re.sub(r"\s+", " ", str(content or "").strip().lower())
    if not lowered:
        return ""
    if "how to win friends and influence people" in lowered or "dale carnegie" in lowered:
        return (
            "Use a friendly, empathetic, relationship-first style. "
            "Prioritize trust, encouragement, and practical interpersonal advice."
        )
    if "48 laws of power" in lowered:
        return (
            "Use a strategic, power-aware style. "
            "Prioritize positioning, perception, and careful leverage."
        )
    cleaned = re.sub(r"\bthe book\b.*?(?:in mind|as a guide|when giving advice)\b", "", str(content), flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:how to win friends and influence people|dale carnegie|48 laws of power)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;?!")
    if not cleaned:
        return ""
    if len(cleaned) > 220:
        cleaned = cleaned[:217].rstrip() + "..."
    return cleaned


def _persona_behavior_memory_text(*, deps: HandlerDeps, workspace_id: str, room_id: str, persona_name: str) -> str:
    if deps.archive_service is None or deps.receptionist_context_service is None:
        return ""
    refs = deps.receptionist_context_service.persona_behavior_memory_refs(
        workspace_id=workspace_id,
        room_id=room_id,
        persona_name=persona_name,
    )
    room_refs = deps.receptionist_context_service.room_behavior_memory_refs(
        workspace_id=workspace_id,
        room_id=room_id,
    )
    combined = list(refs or []) + list(room_refs or [])
    lines: List[str] = []
    seen: set[Tuple[str, str]] = set()
    for ref in combined[-20:]:
        if not isinstance(ref, dict):
            continue
        artifact_id = str(ref.get("artifact_id") or "").strip()
        artifact_workspace_id = str(ref.get("workspace_id") or workspace_id).strip() or workspace_id
        key = (artifact_workspace_id, artifact_id)
        if not artifact_id or key in seen:
            continue
        seen.add(key)
        try:
            record = deps.archive_service.get_artifact(artifact_workspace_id, artifact_id)
        except Exception:
            continue
        guidance = _persona_style_guidance_text(str(record.get("content") or "").strip())
        if guidance:
            lines.append(f"- {guidance}")
    return "\n".join(lines)


def _memo_reply_prompt(
    *,
    dest_room_title: str,
    to_persona: str,
    persona_purpose: str,
    persona_style: str,
    room_memory_text: str,
    persona_memory_text: str,
    subject: str,
    body: str,
    from_room: str,
) -> tuple[str, str]:
    room_memory_block = f"\nActive room behavior memory:\n{room_memory_text}\n" if room_memory_text else ""
    persona_memory_block = f"\nActive persona style guidance:\n{persona_memory_text}\n" if persona_memory_text else ""
    system_prompt = (
        f"You are {to_persona} in Veridex room {dest_room_title}. "
        f"Your purpose is: {persona_purpose or 'Respond within your room responsibilities.'} "
        f"Your style is: {persona_style or 'professional'}."
        f"{room_memory_block}"
        f"{persona_memory_block}"
        "\nRespond to the memo as the destination persona.\n"
        "Rules:\n"
        "- Return only the destination persona response body.\n"
        "- Do not repeat the mailroom header.\n"
        "- Do not ask questions.\n"
        "- Do not mention saving, logging, backend state, room switching, queueing, or system mutation.\n"
        f"- If the memo lacks enough detail, state what is missing using declarative sentences and end with this exact line: {DEFAULT_CONTRACT.closure_line}\n"
        f"- Append this exact closure line only for insufficient-detail responses or substantive analysis/recommendation: {DEFAULT_CONTRACT.closure_line}\n"
        "- For simple factual or brief logical responses, end cleanly with no closure line."
    )
    user_prompt = (
        f"From room: {from_room}\n"
        f"Memo subject: {subject}\n"
        f"Memo body: {body}\n\n"
        "Write the destination persona response now."
    )
    return system_prompt, user_prompt


def _normalize_memo_reply(text: str) -> str:
    reply = str(text or "").strip()
    reply = re.sub(r"^Memo filed to:.*?(?:\r?\n){1,2}", "", reply, flags=re.IGNORECASE | re.DOTALL)
    reply = re.sub(r"^Subject:.*?(?:\r?\n){1,2}", "", reply, flags=re.IGNORECASE | re.DOTALL)
    reply = re.sub(r"\n{3,}", "\n\n", reply)
    return reply.strip()


def _memo_reply_flags(reply_text: str) -> tuple[bool, bool]:
    lowered = str(reply_text or "").strip().lower()
    is_refusal = bool(
        "does not specify" in lowered
        or "cannot be performed without" in lowered
        or "cannot be completed without" in lowered
        or "insufficient detail" in lowered
    )
    closure_appended = DEFAULT_CONTRACT.closure_line in str(reply_text or "")
    return is_refusal, closure_appended


def build_memo_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_mailroom_dispatch(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        for field in ("to_room", "body"):
            if field not in args:
                raise deps.error_missing_required_field(field)

        to_room_raw = str(args["to_room"])
        ensure_single_target(to_room_raw)
        if "," in to_room_raw or " and " in to_room_raw.lower() or "&" in to_room_raw:
            raise HTTPException(status_code=400, detail="One memo may target only one room. Send separate memos.")

        body = str(args["body"]).strip()
        explicit_persona = str(args.get("explicit_persona", "")).strip() or None

        # Mailroom memos are text-only. Do not let a model reply imply that Nancy sent email.
        if str(to_room_raw or "").strip().lower() in {"my_office", "nancy", "nancy office"} and re.search(r"\b(?:draft|send)\b.*\b(?:email|gmail)\b|\bsend\s+that\s+drafted\s+email\b", body, re.IGNORECASE):
            response_text = (
                "No email was sent. Email actions cannot run through a memo to Nancy. "
                "Use: Nancy, send an email to name@example.com subject: Your subject body: Your message."
            )
            return {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "response_text": response_text,
                    "email_action_blocked": True,
                },
                "content": [{"type": "text", "text": response_text}],
            }

        state = deps.kernel.get_state(workspace_id)
        from_room_external = state.get("active_room", "lobby")
        memo_result = deps.memo_service.dispatch_memo(
            workspace_id=workspace_id,
            from_room=from_room_external,
            to_room=to_room_raw,
            body=body,
            explicit_persona=explicit_persona,
            policy_check_fn=deps.pipeline.assert_mailroom_allowed,
        )

        destination_room = validate_room(memo_result["to_room"])
        to_persona = str(memo_result["to_persona"] or destination_room.get("default_persona") or "Navigator").strip()
        persona_profile = persona_profile_for_name(to_persona)
        room_memory_text = _room_behavior_memory_text(
            deps=deps,
            workspace_id=workspace_id,
            room_id=str(memo_result["to_room"] or "").strip(),
        )
        persona_memory_text = _persona_behavior_memory_text(
            deps=deps,
            workspace_id=workspace_id,
            room_id=str(memo_result["to_room"] or "").strip(),
            persona_name=to_persona,
        )
        system_prompt, user_prompt = _memo_reply_prompt(
            dest_room_title=str(memo_result["dest_room_title"] or destination_room.get("title") or memo_result["to_room"]).strip(),
            to_persona=to_persona,
            persona_purpose=str(persona_profile.get("purpose") or "").strip(),
            persona_style=str(persona_profile.get("style") or "").strip(),
            room_memory_text=room_memory_text,
            persona_memory_text=persona_memory_text,
            subject=str(memo_result["subject"] or "").strip(),
            body=body,
            from_room=from_room_external,
        )
        try:
            reply_result = deps.model_router.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context={
                    "workspace_id": workspace_id,
                    "active_room": str(memo_result["to_room"] or "").strip(),
                    "active_persona": to_persona,
                    "room_behavior_memory_text": room_memory_text,
                    "persona_behavior_memory_text": persona_memory_text,
                    "conversation_history_text": "",
                    "session_summary_text": "",
                    "session_facts_text": "",
                },
                settings={
                    "temperature": 0.2,
                    "max_output_tokens": 420,
                },
                task_type="planning",
            )
            reply_text = _normalize_memo_reply(reply_result.text)
        except ModelRoutingError:
            reply_text = (
                "A complete assessment cannot be performed at this time due to an internal processing failure.\n\n"
                f"{DEFAULT_CONTRACT.closure_line}"
            )

        if not reply_text:
            reply_text = (
                "The memo does not specify enough detail for a complete assessment.\n"
                "A complete assessment cannot be performed without those elements.\n\n"
                f"{DEFAULT_CONTRACT.closure_line}"
            )

        reply_is_refusal, reply_closure_appended = _memo_reply_flags(reply_text)
        deps.memo_service.record_memo_reply(
            workspace_id=workspace_id,
            memo_id=memo_result["memo_id"],
            reply_text=reply_text,
            reply_room=str(memo_result["to_room"] or "").strip(),
            reply_persona=to_persona,
            reply_is_refusal=reply_is_refusal,
            reply_closure_appended=reply_closure_appended,
        )

        deps.append_incident(
            severity="LOW",
            clazz="MEMO_DISPATCH",
            rule_or_gate="Mailroom Dispatch Contract v1.1.0",
            command="mailroom.dispatch",
            input_ref=json.dumps(
                {
                    "workspace_id": workspace_id,
                    "from_room": from_room_external,
                    "to_room": memo_result["to_room"],
                    "memo_id": memo_result["memo_id"],
                }
            ),
            output_ref="(tool_response)",
            evidence_path=str(deps.store.memos_dir(workspace_id)),
            notes="Recorded memo dispatch (single-target).",
            state_sha256=deps.stable_state_sha(state),
        )

        return deps.pipeline.mailroom_response(
            workspace_id=workspace_id,
            memo_id=memo_result["memo_id"],
            from_room=from_room_external,
            to_room=memo_result["to_room"],
            to_persona=memo_result["to_persona"],
            subject=memo_result["subject"],
            dest_room_title=memo_result["dest_room_title"],
            reply_text=reply_text,
            reply_room=str(memo_result["to_room"] or "").strip(),
            reply_persona=to_persona,
            is_refusal=reply_is_refusal,
            closure_appended=reply_closure_appended,
        )

    def handle_memos_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        limit = int(args.get("limit", 25))
        rows = deps.memo_service.list_memos(workspace_id, limit=limit)
        return deps.pipeline.memos_list_response(workspace_id, rows)

    def handle_memo_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        memo_id = str(args.get("memo_id", "")).strip()
        if not memo_id:
            raise deps.error_missing_required_field("memo_id")

        obj, body = deps.memo_service.get_memo(workspace_id, memo_id)
        return deps.pipeline.memo_get_response(obj, body)

    return {
        "mailroom.dispatch": handle_mailroom_dispatch,
        "office.memos_list": handle_memos_list,
        "office.memo_get": handle_memo_get,
    }
