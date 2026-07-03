from __future__ import annotations

import html
import re
from typing import Any, Dict

from fastapi import HTTPException


def build_integration_handlers(*, integration_service, user_service) -> Dict[str, Any]:
    def clean_gmail_body_text(value: Any) -> str:
        text = re.sub(r"\r\n?", "\n", str(value or "")).strip()
        if not text:
            return ""
        html_match = re.search(r"(?is)<(?:html|body|div|span|blockquote|br|p|table|a)\b", text)
        if html_match:
            plain_before_html = text[:html_match.start()].strip()
            if plain_before_html:
                text = plain_before_html
            else:
                text = re.sub(r"(?i)<br\s*/?>", "\n", text)
                text = re.sub(r"(?i)</(?:div|p|blockquote|li|tr|h[1-6])>", "\n", text)
                text = re.sub(r"(?is)<[^>]+>", "", text)
                text = html.unescape(text)
        text = re.split(r"(?im)^\s*On .+? wrote:\s*$", text, maxsplit=1)[0].strip()
        text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def clean_gmail_message(message: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(message)
        if "body_text" in cleaned:
            cleaned["body_text"] = clean_gmail_body_text(cleaned.get("body_text"))
        return cleaned

    def user_id_for(args: Dict[str, Any]) -> str:
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            raise HTTPException(status_code=401, detail="Session ID required for integrations.")
        user = user_service.get_user_for_session(session_id)
        return str(user.get("user_id") or "").strip()

    def google_connection(user_id: str) -> Dict[str, Any]:
        return dict(integration_service.google_connection_status(user_id))

    def disconnected_google_response(*, action_label: str, speaker: str, connection: Dict[str, Any]) -> Dict[str, Any]:
        configured = bool(connection.get("configured"))
        prefix = f"{speaker}: " if speaker else ""
        if configured:
            text = (
                f"{prefix}Google is configured but not connected. "
                f"Connect Google from Profile before I can {action_label}."
            )
        else:
            text = (
                f"{prefix}Google integration is not configured on this server. "
                f"Configure Google OAuth before I can {action_label}."
            )
        return {
            "structuredContent": {
                "provider": "google",
                "google_connection": connection,
                "action_blocked": action_label,
            },
            "content": [{"type": "text", "text": text}],
        }

    def gmail_search(args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="Gmail search query is required.")
        session_id = str(args.get("session_id") or "").strip()
        user_id = user_id_for(args)
        messages = integration_service.gmail_search(user_id, query, int(args.get("max_results") or 10))
        if session_id and hasattr(integration_service, "remember_gmail_results"):
            integration_service.remember_gmail_results(user_id, session_id, messages)
        for index, message in enumerate(messages, start=1):
            message["index"] = index
        text = (
            f"Found {len(messages)} Gmail message(s). Select an email card from the email cards to open the thread."
            if messages
            else "Found 0 Gmail message(s)."
        )
        return {"structuredContent": {"messages": messages, "gmail_messages": messages}, "content": [{"type": "text", "text": text}]}

    def gmail_read(args: Dict[str, Any]) -> Dict[str, Any]:
        message_id = str(args.get("message_id") or "").strip()
        if not message_id and args.get("message_index") is not None:
            user_id = user_id_for(args)
            session_id = str(args.get("session_id") or "").strip()
            try:
                message_index = int(args.get("message_index") or 0)
            except Exception:
                message_index = 0
            selected = integration_service.gmail_result_by_index(user_id, session_id, message_index)
            message_id = str((selected or {}).get("id") or "").strip()
        if not message_id:
            raise HTTPException(status_code=400, detail="Gmail message_id is required.")
        message = clean_gmail_message(integration_service.gmail_read(user_id_for(args), message_id))
        lines = [
            "Loaded Gmail message.",
            f"From: {message.get('from') or 'Unknown sender'}",
            f"To: {message.get('to') or ''}",
            f"Subject: {message.get('subject') or '(no subject)'}",
        ]
        if message.get("date"):
            lines.append(f"Date: {message.get('date')}")
        lines.extend(["", "Would you like to reply?"])
        return {"structuredContent": {"message": message, "gmail_message": message}, "content": [{"type": "text", "text": "\n".join(lines)}]}

    def gmail_thread_read(args: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = str(args.get("thread_id") or "").strip()
        if not thread_id and args.get("message_index") is not None:
            user_id = user_id_for(args)
            session_id = str(args.get("session_id") or "").strip()
            try:
                message_index = int(args.get("message_index") or 0)
            except Exception:
                message_index = 0
            selected = integration_service.gmail_result_by_index(user_id, session_id, message_index)
            thread_id = str((selected or {}).get("threadId") or "").strip()
        if not thread_id:
            raise HTTPException(status_code=400, detail="Gmail thread_id is required.")
        messages = [clean_gmail_message(message) for message in integration_service.gmail_thread_read(user_id_for(args), thread_id)]
        lines = [f"Loaded Gmail thread with {len(messages)} message(s)."]
        if messages:
            latest = messages[-1]
            lines.extend([
                "",
                f"From: {latest.get('from') or 'Unknown sender'}",
                f"To: {latest.get('to') or ''}",
                f"Subject: {latest.get('subject') or '(no subject)'}",
            ])
            if latest.get("date"):
                lines.append(f"Date: {latest.get('date')}")
        lines.extend(["", "Would you like to reply?"])
        return {
            "structuredContent": {
                "gmail_thread": messages,
                "thread_id": thread_id,
                "speaker": "Nancy",
            },
            "content": [{"type": "text", "text": "\n".join(lines)}],
        }

    def gmail_draft(args: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"to": args.get("to"), "subject": str(args.get("subject") or ""), "body": str(args.get("body") or "")}
        speaker = str(args.get("assistant_persona") or "").strip()
        user_id = user_id_for(args)
        connection = google_connection(user_id)
        structured = {"draft": payload}
        if speaker:
            structured["speaker"] = speaker
        structured["google_connection"] = connection
        text = f"{speaker} prepared the email draft. Sending requires confirmation." if speaker else "Gmail draft prepared. Sending requires confirmation."
        if not connection.get("connected"):
            text += " Please connect Google from Profile before sending through Gmail."
        return {"structuredContent": structured, "content": [{"type": "text", "text": text}]}

    def gmail_send(args: Dict[str, Any]) -> Dict[str, Any]:
        user_id = user_id_for(args)
        speaker = str(args.get("assistant_persona") or "").strip()
        connection = google_connection(user_id)
        if not connection.get("connected"):
            return disconnected_google_response(action_label="send Gmail", speaker=speaker, connection=connection)
        review = {"to": args.get("to"), "subject": str(args.get("subject") or ""), "body": str(args.get("body") or "")}
        pending = integration_service.create_pending_action(
            user_id=user_id, action_kind="gmail.send",
            payload=review,
        )
        if speaker:
            pending["speaker"] = speaker
        pending["google_connection"] = connection
        pending["email_review"] = review
        recipient_text = ", ".join(str(item) for item in review.get("to") or [])
        text = "\n".join([
            f"{speaker} prepared the Gmail send confirmation." if speaker else "Gmail send is pending confirmation.",
            "",
            f"To: {recipient_text}",
            f"Subject: {review['subject']}",
            f"Body: {review['body']}",
            "",
            "Review the details and confirm to send.",
        ])
        return {"structuredContent": pending, "content": [{"type": "text", "text": text}]}

    def contact_resolve_email(args: Dict[str, Any]) -> Dict[str, Any]:
        name = str(args.get("name") or args.get("query") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Contact name is required.")
        matches = integration_service.search_contacts(user_id_for(args), name, 5)
        if not matches:
            return {
                "structuredContent": {"speaker": "Nancy", "contact_query": name, "contacts": []},
                "content": [{"type": "text", "text": f"Nancy could not find a saved email contact for {name}. What email address should I use?"}],
            }
        contact = matches[0]
        email = str(contact.get("email") or "").strip()
        display_name = str(contact.get("display_name") or name).strip() or name
        text = f"What subject should I use for the email to {email}?\nContact: {display_name}"
        return {
            "structuredContent": {
                "speaker": "Nancy",
                "resolved_contact": contact,
                "response_text": text,
            },
            "content": [{"type": "text", "text": text}],
        }

    def contact_save(args: Dict[str, Any]) -> Dict[str, Any]:
        aliases = args.get("aliases")
        if not isinstance(aliases, list):
            aliases = []
        contact = integration_service.save_contact(
            user_id_for(args),
            email=str(args.get("email") or ""),
            display_name=str(args.get("display_name") or ""),
            aliases=[str(item) for item in aliases],
            source="manual",
        )
        return {
            "structuredContent": {"speaker": "Nancy", "contact": contact},
            "content": [{"type": "text", "text": f"Saved contact: {contact.get('display_name') or contact.get('email')} <{contact.get('email')}>"}],
        }

    def contact_list(args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").strip()
        contacts = integration_service.search_contacts(user_id_for(args), query or "@", int(args.get("max_results") or 20))
        text = (
            f"Found {len(contacts)} contact(s). Select from the contact cards when composing with Nancy."
            if contacts
            else "Found 0 contact(s)."
        )
        return {"structuredContent": {"speaker": "Nancy", "contacts": contacts}, "content": [{"type": "text", "text": text}]}

    def calendar_list(args: Dict[str, Any]) -> Dict[str, Any]:
        events = integration_service.calendar_list(user_id_for(args), args.get("time_min"), args.get("time_max"))
        return {"structuredContent": {"events": events}, "content": [{"type": "text", "text": f"Found {len(events)} calendar event(s)."}]}

    def calendar_write(action_kind: str):
        def handler(args: Dict[str, Any]) -> Dict[str, Any]:
            user_id = user_id_for(args)
            speaker = str(args.get("assistant_persona") or "").strip()
            connection = google_connection(user_id)
            if not connection.get("connected"):
                action_name = action_kind.rsplit(".", 1)[-1]
                return disconnected_google_response(action_label=f"{action_name} Calendar events", speaker=speaker, connection=connection)
            payload = dict(args.get("event") or {})
            if action_kind in {"calendar.update", "calendar.cancel"}:
                payload["event_id"] = str(args.get("event_id") or "").strip()
            pending = integration_service.create_pending_action(user_id=user_id, action_kind=action_kind, payload=payload)
            if speaker:
                pending["speaker"] = speaker
            pending["google_connection"] = connection
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
        "office.gmail_thread_read": gmail_thread_read,
        "office.gmail_draft": gmail_draft,
        "office.gmail_send": gmail_send,
        "office.contact_resolve_email": contact_resolve_email,
        "office.contact_save": contact_save,
        "office.contact_list": contact_list,
        "office.calendar_list": calendar_list,
        "office.calendar_create": calendar_write("calendar.create"),
        "office.calendar_update": calendar_write("calendar.update"),
        "office.calendar_cancel": calendar_write("calendar.cancel"),
        "office.integration_confirm": confirm,
    }
