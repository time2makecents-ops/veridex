from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

from office_app.server.env_loader import load_env_files


GOOGLE_PROVIDER = "google"
GOOGLE_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class IntegrationError(Exception):
    """An actionable integration failure safe to return to the UI."""


class TokenCipher:
    """Authenticated secret-box style storage using stdlib primitives.

    The configured key must be high entropy. The nonce, ciphertext, and tag are
    stored together; plaintext tokens never leave this class.
    """

    def __init__(self, key: str) -> None:
        raw = str(key or "").strip().encode("utf-8")
        if len(raw) < 32:
            raise IntegrationError("VERIDEX_INTEGRATION_ENCRYPTION_KEY must be at least 32 characters.")
        self._key = hashlib.sha256(raw).digest()

    def _stream(self, nonce: bytes, length: int) -> bytes:
        output = bytearray()
        counter = 0
        while len(output) < length:
            output.extend(hmac.new(self._key, b"veridex-token-v1" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1
        return bytes(output[:length])

    def encrypt(self, value: str) -> str:
        nonce = secrets.token_bytes(24)
        plaintext = value.encode("utf-8")
        stream = self._stream(nonce, len(plaintext))
        ciphertext = bytes(left ^ right for left, right in zip(plaintext, stream))
        tag = hmac.new(self._key, b"veridex-token-tag-v1" + nonce + ciphertext, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(value.encode("ascii"))
            nonce, tag, ciphertext = raw[:24], raw[24:56], raw[56:]
        except Exception as exc:
            raise IntegrationError("Stored integration credential is invalid. Reconnect the account.") from exc
        expected = hmac.new(self._key, b"veridex-token-tag-v1" + nonce + ciphertext, hashlib.sha256).digest()
        if len(nonce) != 24 or not hmac.compare_digest(tag, expected):
            raise IntegrationError("Stored integration credential failed integrity validation. Reconnect the account.")
        stream = self._stream(nonce, len(ciphertext))
        return bytes(left ^ right for left, right in zip(ciphertext, stream)).decode("utf-8")


class IntegrationStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_integrations (
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_email TEXT NOT NULL DEFAULT '',
                    scopes_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'connected',
                    access_token_ciphertext TEXT NOT NULL,
                    refresh_token_ciphertext TEXT NOT NULL,
                    access_token_expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, provider)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_pending_actions (
                    confirmation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    action_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    def get_connection(self, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM user_integrations WHERE user_id = ? AND provider = ?", (user_id, provider)).fetchone()
        return self._row(row) if row else None

    def list_connections(self, user_id: str) -> list[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM user_integrations WHERE user_id = ? ORDER BY provider", (user_id,)).fetchall()
        return [self._row(row) for row in rows]

    def upsert_connection(self, record: Dict[str, Any]) -> None:
        columns = (
            "user_id", "provider", "account_email", "scopes_json", "status", "access_token_ciphertext",
            "refresh_token_ciphertext", "access_token_expires_at", "created_at", "updated_at",
        )
        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO user_integrations ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
                "ON CONFLICT(user_id, provider) DO UPDATE SET "
                "account_email=excluded.account_email, scopes_json=excluded.scopes_json, status=excluded.status, "
                "access_token_ciphertext=excluded.access_token_ciphertext, refresh_token_ciphertext=excluded.refresh_token_ciphertext, "
                "access_token_expires_at=excluded.access_token_expires_at, updated_at=excluded.updated_at",
                [record[column] for column in columns],
            )
            conn.commit()

    def delete_connection(self, user_id: str, provider: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM user_integrations WHERE user_id = ? AND provider = ?", (user_id, provider))
            conn.commit()

    def save_state(self, *, state_hash: str, provider: str, user_id: str, session_id: str, expires_at: str, created_at: str) -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO integration_oauth_states VALUES (?, ?, ?, ?, ?, ?)", (state_hash, provider, user_id, session_id, expires_at, created_at))
            conn.commit()

    def consume_state(self, state_hash: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM integration_oauth_states WHERE state_hash = ?", (state_hash,)).fetchone()
            conn.execute("DELETE FROM integration_oauth_states WHERE state_hash = ?", (state_hash,))
            conn.commit()
        return self._row(row) if row else None

    def save_pending_action(self, record: Dict[str, Any]) -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO integration_pending_actions VALUES (?, ?, ?, ?, ?, ?, ?)", (
                record["confirmation_id"], record["user_id"], record["provider"], record["action_kind"],
                record["payload_json"], record["expires_at"], record["created_at"],
            ))
            conn.commit()

    def consume_pending_action(self, confirmation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM integration_pending_actions WHERE confirmation_id = ? AND user_id = ?",
                (confirmation_id, user_id),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "DELETE FROM integration_pending_actions WHERE confirmation_id = ? AND user_id = ?",
                    (confirmation_id, user_id),
                )
            conn.commit()
        return self._row(row) if row else None


class IntegrationService:
    def __init__(self, *, runtime_dir: Path, now_fn=utc_now_iso, env: Optional[Dict[str, str]] = None) -> None:
        self.now = now_fn
        if env is None:
            root_dir = Path(__file__).resolve().parents[2]
            package_dir = Path(__file__).resolve().parents[1]
            load_env_files((root_dir / ".env.local", root_dir / ".env", package_dir / ".env.local"))
            self.env = os.environ
        else:
            self.env = env
        self.store = IntegrationStore(Path(runtime_dir) / "veridex.db")

    def _config(self, key: str) -> str:
        return str(self.env.get(key) or "").strip()

    def _cipher(self) -> TokenCipher:
        return TokenCipher(self._config("VERIDEX_INTEGRATION_ENCRYPTION_KEY"))

    def _google_configured(self) -> bool:
        return bool(self._config("GOOGLE_OAUTH_CLIENT_ID") and self._config("GOOGLE_OAUTH_CLIENT_SECRET") and self._config("GOOGLE_OAUTH_REDIRECT_URI") and self._config("VERIDEX_INTEGRATION_ENCRYPTION_KEY"))

    def list_connections(self, user_id: str) -> list[Dict[str, Any]]:
        records = {row["provider"]: row for row in self.store.list_connections(user_id)}
        result: list[Dict[str, Any]] = []
        for provider, configured in ((GOOGLE_PROVIDER, self._google_configured()),):
            row = records.get(provider)
            result.append({
                "provider": provider,
                "configured": configured,
                "connected": bool(row and row.get("status") == "connected"),
                "account_email": str(row.get("account_email") or "") if row else "",
                "scopes": json.loads(str(row.get("scopes_json") or "[]")) if row else [],
                "access_token_expires_at": str(row.get("access_token_expires_at") or "") if row else "",
                "updated_at": str(row.get("updated_at") or "") if row else "",
            })
        return result

    def begin_google_connect(self, *, user_id: str, session_id: str) -> str:
        if not self._google_configured():
            raise HTTPException(status_code=503, detail="Google integration is not configured. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI, and VERIDEX_INTEGRATION_ENCRYPTION_KEY.")
        now = datetime.now(timezone.utc)
        nonce = secrets.token_urlsafe(32)
        signing_key = self._config("VERIDEX_INTEGRATION_ENCRYPTION_KEY").encode("utf-8")
        signature = hmac.new(signing_key, nonce.encode("utf-8"), hashlib.sha256).hexdigest()
        state = f"{nonce}.{signature}"
        self.store.save_state(
            state_hash=hashlib.sha256(state.encode("utf-8")).hexdigest(), provider=GOOGLE_PROVIDER,
            user_id=user_id, session_id=session_id,
            expires_at=(now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"), created_at=self.now(),
        )
        query = urlencode({
            "client_id": self._config("GOOGLE_OAUTH_CLIENT_ID"), "redirect_uri": self._config("GOOGLE_OAUTH_REDIRECT_URI"),
            "response_type": "code", "scope": " ".join(GOOGLE_SCOPES), "access_type": "offline",
            "prompt": "consent", "include_granted_scopes": "true", "state": state,
        })
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    def complete_google_connect(self, *, code: str, state: str) -> Dict[str, Any]:
        nonce, separator, signature = str(state or "").partition(".")
        key = self._config("VERIDEX_INTEGRATION_ENCRYPTION_KEY").encode("utf-8")
        expected = hmac.new(key, nonce.encode("utf-8"), hashlib.sha256).hexdigest() if nonce else ""
        saved = self.store.consume_state(hashlib.sha256(str(state).encode("utf-8")).hexdigest())
        if not separator or not saved or not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=400, detail="Google authorization state is invalid or already used.")
        if str(saved.get("expires_at") or "") <= self.now():
            raise HTTPException(status_code=400, detail="Google authorization expired. Start the connection again.")
        token = self._post_form("https://oauth2.googleapis.com/token", {
            "code": code, "client_id": self._config("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": self._config("GOOGLE_OAUTH_CLIENT_SECRET"), "redirect_uri": self._config("GOOGLE_OAUTH_REDIRECT_URI"),
            "grant_type": "authorization_code",
        })
        access_token = str(token.get("access_token") or "")
        refresh_token = str(token.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise HTTPException(status_code=502, detail="Google did not return the required offline authorization. Reconnect and approve the requested permissions.")
        identity = self._google_json(access_token, "GET", "https://openidconnect.googleapis.com/v1/userinfo")
        now = self.now()
        expires_in = int(token.get("expires_in") or 3600)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in - 60))).isoformat().replace("+00:00", "Z")
        cipher = self._cipher()
        self.store.upsert_connection({
            "user_id": saved["user_id"], "provider": GOOGLE_PROVIDER, "account_email": str(identity.get("email") or ""),
            "scopes_json": json.dumps(str(token.get("scope") or " ".join(GOOGLE_SCOPES)).split()), "status": "connected",
            "access_token_ciphertext": cipher.encrypt(access_token), "refresh_token_ciphertext": cipher.encrypt(refresh_token),
            "access_token_expires_at": expires_at, "created_at": now, "updated_at": now,
        })
        return {"provider": GOOGLE_PROVIDER, "account_email": str(identity.get("email") or "")}

    def disconnect(self, user_id: str, provider: str) -> None:
        if provider != GOOGLE_PROVIDER:
            raise HTTPException(status_code=404, detail="Integration provider not found.")
        row = self.store.get_connection(user_id, provider)
        if row:
            try:
                self._post_form("https://oauth2.googleapis.com/revoke", {"token": self._cipher().decrypt(row["refresh_token_ciphertext"])})
            except IntegrationError:
                pass
        self.store.delete_connection(user_id, provider)

    def create_pending_action(self, *, user_id: str, action_kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"gmail.send", "calendar.create", "calendar.update", "calendar.cancel"}
        if action_kind not in allowed:
            raise HTTPException(status_code=400, detail="Unsupported Google write action.")
        confirmation_id = f"confirm_{secrets.token_urlsafe(18)}"
        now = datetime.now(timezone.utc)
        self.store.save_pending_action({
            "confirmation_id": confirmation_id, "user_id": user_id, "provider": GOOGLE_PROVIDER,
            "action_kind": action_kind, "payload_json": json.dumps(payload),
            "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"), "created_at": self.now(),
        })
        return {"confirmation_id": confirmation_id, "provider": GOOGLE_PROVIDER, "action_kind": action_kind, "payload": payload, "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")}

    def confirm_action(self, *, user_id: str, confirmation_id: str) -> Dict[str, Any]:
        record = self.store.consume_pending_action(confirmation_id, user_id)
        if not record:
            raise HTTPException(status_code=404, detail="Confirmation request not found.")
        if str(record["expires_at"]) <= self.now():
            raise HTTPException(status_code=409, detail="Confirmation request expired. Create the action again.")
        payload = json.loads(record["payload_json"])
        action = str(record["action_kind"])
        if action == "gmail.send":
            return self._send_gmail(user_id, payload)
        if action == "calendar.create":
            return self._calendar_request(user_id, "POST", "", payload)
        if action == "calendar.update":
            event_id = str(payload.pop("event_id", "")).strip()
            if not event_id:
                raise HTTPException(status_code=400, detail="Calendar event_id is required.")
            return self._calendar_request(user_id, "PUT", event_id, payload)
        if action == "calendar.cancel":
            event_id = str(payload.get("event_id") or "").strip()
            if not event_id:
                raise HTTPException(status_code=400, detail="Calendar event_id is required.")
            return self._calendar_request(user_id, "DELETE", event_id, None)
        raise HTTPException(status_code=400, detail="Unsupported confirmation action.")

    def gmail_search(self, user_id: str, query: str, max_results: int = 10) -> list[Dict[str, Any]]:
        params = urlencode({"q": query, "maxResults": max(1, min(max_results, 25))})
        response = self._google_authorized_json(user_id, "GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{params}")
        return list(response.get("messages") or [])

    def gmail_read(self, user_id: str, message_id: str) -> Dict[str, Any]:
        return self._google_authorized_json(user_id, "GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full")

    def calendar_list(self, user_id: str, time_min: Optional[str] = None, time_max: Optional[str] = None) -> list[Dict[str, Any]]:
        params: Dict[str, Any] = {"singleEvents": "true", "orderBy": "startTime", "maxResults": 50}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        response = self._google_authorized_json(user_id, "GET", f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{urlencode(params)}")
        return list(response.get("items") or [])

    def _access_token(self, user_id: str) -> str:
        row = self.store.get_connection(user_id, GOOGLE_PROVIDER)
        if not row or row.get("status") != "connected":
            raise HTTPException(status_code=409, detail="Google is not connected for this user. Connect it from Profile first.")
        cipher = self._cipher()
        if str(row.get("access_token_expires_at") or "") > self.now():
            return cipher.decrypt(row["access_token_ciphertext"])
        refresh = cipher.decrypt(row["refresh_token_ciphertext"])
        token = self._post_form("https://oauth2.googleapis.com/token", {
            "client_id": self._config("GOOGLE_OAUTH_CLIENT_ID"), "client_secret": self._config("GOOGLE_OAUTH_CLIENT_SECRET"),
            "refresh_token": refresh, "grant_type": "refresh_token",
        })
        access_token = str(token.get("access_token") or "")
        if not access_token:
            self.store.delete_connection(user_id, GOOGLE_PROVIDER)
            raise HTTPException(status_code=409, detail="Google authorization expired or was revoked. Reconnect Google from Profile.")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(token.get("expires_in") or 3600) - 60))).isoformat().replace("+00:00", "Z")
        updated = dict(row)
        updated.update({"access_token_ciphertext": cipher.encrypt(access_token), "access_token_expires_at": expires_at, "updated_at": self.now()})
        self.store.upsert_connection(updated)
        return access_token

    def _google_authorized_json(self, user_id: str, method: str, url: str, payload: Any = None) -> Dict[str, Any]:
        return self._google_json(self._access_token(user_id), method, url, payload)

    def _calendar_request(self, user_id: str, method: str, event_id: str, payload: Any) -> Dict[str, Any]:
        suffix = f"/{event_id}" if event_id else ""
        return self._google_authorized_json(user_id, method, f"https://www.googleapis.com/calendar/v3/calendars/primary/events{suffix}", payload)

    def _send_gmail(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        recipients = payload.get("to")
        if not isinstance(recipients, list) or not recipients or not all(isinstance(item, str) and item.strip() for item in recipients):
            raise HTTPException(status_code=400, detail="Gmail send requires at least one recipient in to.")
        subject = str(payload.get("subject") or "").replace("\n", " ").replace("\r", " ")
        body = str(payload.get("body") or "")
        raw = "\r\n".join([f"To: {', '.join(recipients)}", f"Subject: {subject}", "MIME-Version: 1.0", "Content-Type: text/plain; charset=UTF-8", "", body])
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        return self._google_authorized_json(user_id, "POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {"raw": encoded})

    def _post_form(self, url: str, form: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_json("POST", url, urlencode(form).encode("utf-8"), {"Content-Type": "application/x-www-form-urlencoded"})

    def _google_json(self, access_token: str, method: str, url: str, payload: Any = None) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {access_token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        return self._request_json(method, url, body, headers)

    @staticmethod
    def _request_json(method: str, url: str, body: Optional[bytes], headers: Dict[str, str]) -> Dict[str, Any]:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail).get("error", {}).get("message") or detail
            except Exception:
                message = detail
            raise HTTPException(status_code=502, detail=f"Google API error: {message}") from exc
        except URLError as exc:
            raise HTTPException(status_code=503, detail="Google integration is unavailable. Try again shortly.") from exc
        if not raw:
            return {"ok": True}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Google returned an invalid response.") from exc
