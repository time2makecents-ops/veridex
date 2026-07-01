from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException


def build_integration_handlers(*, integration_service, user_service) -> Dict[str, Any]:
    def user_id_for(args: Dict[str, Any]) -> str:
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            raise HTTPException(status_code=401, detail="Session ID required for integrations.")
        user = user_service.get_user_for_session(session_id)
        return str(user.get("user_id") or "").strip()

    def gmail_search(args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="Gmail search query is required.")
        messages = integration_service.gmail_search(user_id_for(args), query, int(args.get("max_results") or 10))
        return {"structuredContent": {"messages": messages}, "content": [{"type": "text", "text": f"Found {len(messages)} Gmail message(s)."}]}

    def gmail_read(args: Dict[str, Any]) -> Dict[str, Any]:
        message_id = str(args.get("message_id") or "").strip()
        if not message_id:
            raise HTTPException(status_code=400, detail="Gmail message_id is required.")
        message = integration_service.gmail_read(user_id_for(args), message_id)
        return {"structuredContent": {"message": message}, "content": [{"type": "text", "text": "Loaded Gmail message."}]}

    def gmail_draft(args: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"to": args.get("to"), "subject": str(args.get("subject") or ""), "body": str(args.get("body") or "")}
        speaker = str(args.get("assistant_persona") or "").strip()
        structured = {"draft": payload}
        if speaker:
            structured["speaker"] = speaker
        text = f"{speaker} prepared the email draft. Sending requires confirmation." if speaker else "Gmail draft prepared. Sending requires confirmation."
        return {"structuredContent": structured, "content": [{"type": "text", "text": text}]}

    def gmail_send(args: Dict[str, Any]) -> Dict[str, Any]:
        pending = integration_service.create_pending_action(
            user_id=user_id_for(args), action_kind="gmail.send",
            payload={"to": args.get("to"), "subject": str(args.get("subject") or ""), "body": str(args.get("body") or "")},
        )
        speaker = str(args.get("assistant_persona") or "").strip()
        if speaker:
            pending["speaker"] = speaker
        text = f"{speaker} prepared the Gmail send confirmation. Review the details and confirm to send." if speaker else "Gmail send is pending confirmation."
        return {"structuredContent": pending, "content": [{"type": "text", "text": text}]}

    def calendar_list(args: Dict[str, Any]) -> Dict[str, Any]:
        events = integration_service.calendar_list(user_id_for(args), args.get("time_min"), args.get("time_max"))
        return {"structuredContent": {"events": events}, "content": [{"type": "text", "text": f"Found {len(events)} calendar event(s)."}]}

    def calendar_write(action_kind: str):
        def handler(args: Dict[str, Any]) -> Dict[str, Any]:
            payload = dict(args.get("event") or {})
            if action_kind in {"calendar.update", "calendar.cancel"}:
                payload["event_id"] = str(args.get("event_id") or "").strip()
            pending = integration_service.create_pending_action(user_id=user_id_for(args), action_kind=action_kind, payload=payload)
            return {"structuredContent": pending, "content": [{"type": "text", "text": f"Calendar {action_kind.rsplit('.', 1)[-1]} is pending confirmation."}]}
        return handler

    def confirm(args: Dict[str, Any]) -> Dict[str, Any]:
        confirmation_id = str(args.get("confirmation_id") or "").strip()
        if not confirmation_id:
            raise HTTPException(status_code=400, detail="Confirmation ID is required.")
        result = integration_service.confirm_action(user_id=user_id_for(args), confirmation_id=confirmation_id)
        return {"structuredContent": {"result": result}, "content": [{"type": "text", "text": "Google action completed."}]}

    return {
        "office.gmail_search": gmail_search,
        "office.gmail_read": gmail_read,
        "office.gmail_draft": gmail_draft,
        "office.gmail_send": gmail_send,
        "office.calendar_list": calendar_list,
        "office.calendar_create": calendar_write("calendar.create"),
        "office.calendar_update": calendar_write("calendar.update"),
        "office.calendar_cancel": calendar_write("calendar.cancel"),
        "office.integration_confirm": confirm,
    }
