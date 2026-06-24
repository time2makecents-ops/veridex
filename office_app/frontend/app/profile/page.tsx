"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { disconnectIntegration, getCurrentUser, listIntegrations, startGoogleConnection, type IntegrationConnection, type UserRecord } from "@/lib/api";
import { getStoredSessionId } from "@/lib/session";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [profile, nextConnections] = await Promise.all([getCurrentUser(), listIntegrations()]);
      setUser(profile);
      setConnections(nextConnections);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!getStoredSessionId()) {
      router.replace("/");
      return;
    }
    void load();
  }, [router]);

  const google = connections.find((connection) => connection.provider === "google");

  const connectGoogle = async () => {
    setBusy(true);
    setError("");
    try {
      const authorizationUrl = await startGoogleConnection();
      window.location.assign(authorizationUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start Google connection.");
      setBusy(false);
    }
  };

  const disconnectGoogle = async () => {
    setBusy(true);
    setError("");
    try {
      await disconnectIntegration("google");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect Google.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="screen lobby-page lobby-page-plain">
      <section className="card lobby-page-header stack">
        <div className="lobby-title-row">
          <div>
            <div className="terminal-label">Veridex Profile</div>
            <h1 className="title">{user?.display_name || user?.name || "Profile"}</h1>
            <p className="muted">Connected Apps are private to your Veridex account. Admin does not approve or access their credentials.</p>
          </div>
          <button type="button" className="option-button" onClick={() => router.push("/chat")}>Back to Veridex</button>
        </div>
        {error ? <div className="admin-error">{error}</div> : null}
        {loading ? <p className="muted">Loading connected apps...</p> : null}
        {!loading ? (
          <section className="dropdown-group">
            <div className="dropdown-group-title">Connected Apps</div>
            <div className="admin-info-block">
              <div>
                <strong>Google</strong>
                <div className="muted">Gmail and Google Calendar</div>
                {google?.connected ? <div className="muted">Connected as {google.account_email || "Google account"}</div> : null}
                {google?.connected && google.scopes.length ? <div className="muted">Permissions: {google.scopes.join(", ")}</div> : null}
                {!google?.configured ? <div className="admin-error">Google integration is not configured on this server.</div> : null}
              </div>
              <div className="toolbar-row">
                {google?.connected ? (
                  <button type="button" className="secondary" disabled={busy} onClick={() => void disconnectGoogle()}>Disconnect</button>
                ) : (
                  <button type="button" className="primary" disabled={busy || !google?.configured} onClick={() => void connectGoogle()}>Connect Google</button>
                )}
              </div>
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}
