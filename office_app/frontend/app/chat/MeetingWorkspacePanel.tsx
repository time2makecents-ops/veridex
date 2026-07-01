import { useEffect, useMemo, useState } from "react";

import { callTool, type ToolResponse } from "@/lib/api";

import {
  MEETING_SECTION_CONFIG,
  meetingBriefArtifactId,
  meetingStateFromStructuredContent,
  type MeetingSectionKey,
  type MeetingState,
} from "./meetingWorkspace";

type MeetingWorkspacePanelProps = {
  sessionId: string;
  workspaceId: string;
  onArtifactSaved: () => void;
};

type SectionDrafts = Record<MeetingSectionKey, string[]>;
type AddDrafts = Record<MeetingSectionKey, string>;

const EMPTY_SECTION_DRAFTS: SectionDrafts = {
  agenda: [],
  decisions: [],
  action_items: [],
  parking_lot: [],
};

const EMPTY_ADD_DRAFTS: AddDrafts = {
  agenda: "",
  decisions: "",
  action_items: "",
  parking_lot: "",
};

function responseText(response: ToolResponse): string {
  const structured = response.structuredContent as { response_text?: unknown } | undefined;
  const contentText = response.content?.find((item) => item.type === "text")?.text;
  return String(contentText || structured?.response_text || "Meeting workspace updated.");
}

function sectionDraftsFor(state: MeetingState | null): SectionDrafts {
  if (!state) {
    return EMPTY_SECTION_DRAFTS;
  }
  return {
    agenda: [...state.agenda],
    decisions: [...state.decisions],
    action_items: [...state.action_items],
    parking_lot: [...state.parking_lot],
  };
}

export function MeetingWorkspacePanel({ sessionId, workspaceId, onArtifactSaved }: MeetingWorkspacePanelProps) {
  const [meeting, setMeeting] = useState<MeetingState | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [startTitleDraft, setStartTitleDraft] = useState("");
  const [sectionDrafts, setSectionDrafts] = useState<SectionDrafts>(EMPTY_SECTION_DRAFTS);
  const [addDrafts, setAddDrafts] = useState<AddDrafts>(EMPTY_ADD_DRAFTS);
  const [deterministicArtifactId, setDeterministicArtifactId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const meetingArgs = useMemo(() => ({ workspace_id: workspaceId, session_id: sessionId }), [sessionId, workspaceId]);

  function applyMeetingResponse(response: ToolResponse) {
    const nextMeeting = meetingStateFromStructuredContent(response.structuredContent);
    setMeeting(nextMeeting);
    setTitleDraft(nextMeeting?.title || "");
    setSectionDrafts(sectionDraftsFor(nextMeeting));
    return nextMeeting;
  }

  async function loadMeeting() {
    if (!sessionId || !workspaceId) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await callTool("office.meeting_state_show", meetingArgs);
      applyMeetingResponse(response);
      setNotice(responseText(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load meeting state.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadMeeting();
  }, [sessionId, workspaceId]);

  async function startMeeting() {
    setSaving("start");
    setError("");
    try {
      const response = await callTool("office.meeting_state_start", {
        ...meetingArgs,
        title: startTitleDraft,
      });
      applyMeetingResponse(response);
      setStartTitleDraft("");
      setNotice(responseText(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start meeting.");
    } finally {
      setSaving("");
    }
  }

  async function updateTitle() {
    setSaving("title");
    setError("");
    try {
      const response = await callTool("office.meeting_state_update_title", {
        ...meetingArgs,
        title: titleDraft,
      });
      applyMeetingResponse(response);
      setNotice(responseText(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update meeting title.");
    } finally {
      setSaving("");
    }
  }

  async function addItem(section: MeetingSectionKey) {
    const config = MEETING_SECTION_CONFIG.find((item) => item.key === section);
    const item = addDrafts[section].trim();
    if (!config || !item) {
      return;
    }
    setSaving(`add-${section}`);
    setError("");
    try {
      const response = await callTool(config.addTool, {
        ...meetingArgs,
        item,
      });
      applyMeetingResponse(response);
      setAddDrafts((current) => ({ ...current, [section]: "" }));
      setNotice(responseText(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add meeting item.");
    } finally {
      setSaving("");
    }
  }

  async function updateItem(section: MeetingSectionKey, index: number) {
    const item = sectionDrafts[section]?.[index]?.trim() || "";
    if (!item) {
      return;
    }
    setSaving(`update-${section}-${index}`);
    setError("");
    try {
      const response = await callTool("office.meeting_state_update_item", {
        ...meetingArgs,
        section,
        index,
        item,
      });
      applyMeetingResponse(response);
      setNotice(responseText(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update meeting item.");
    } finally {
      setSaving("");
    }
  }

  async function deleteItem(section: MeetingSectionKey, index: number) {
    setSaving(`delete-${section}-${index}`);
    setError("");
    try {
      const response = await callTool("office.meeting_state_delete_item", {
        ...meetingArgs,
        section,
        index,
      });
      applyMeetingResponse(response);
      setNotice(responseText(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete meeting item.");
    } finally {
      setSaving("");
    }
  }

  async function saveBrief(mode: "deterministic" | "polished") {
    setSaving(mode);
    setError("");
    try {
      const response = await callTool("office.meeting_brief_save", {
        ...meetingArgs,
        mode,
        source_artifact_id: mode === "polished" ? deterministicArtifactId : undefined,
      });
      const artifactId = meetingBriefArtifactId(response.structuredContent);
      if (mode === "deterministic") {
        setDeterministicArtifactId(artifactId);
      }
      setNotice(responseText(response));
      onArtifactSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to save ${mode} meeting brief.`);
    } finally {
      setSaving("");
    }
  }

  return (
    <div className="dropdown-panel meeting-workspace-panel">
      <div className="dropdown-group">
        <div className="dropdown-group-title">Meeting Workspace</div>
        <div className="toolbar-row">
          <button type="button" className="secondary toolbar-button" onClick={() => void loadMeeting()} disabled={loading}>
            {loading ? "Refreshing" : "Refresh"}
          </button>
          <button type="button" className="primary toolbar-button" onClick={() => void saveBrief("deterministic")} disabled={!meeting || saving === "deterministic"}>
            {saving === "deterministic" ? "Saving" : "Save Brief"}
          </button>
          <button type="button" className="secondary toolbar-button" onClick={() => void saveBrief("polished")} disabled={!meeting || saving === "polished"}>
            {saving === "polished" ? "Polishing" : "AI Polish"}
          </button>
        </div>
        {notice ? <div className="muted">{notice}</div> : null}
        {error ? <div className="error">{error}</div> : null}
      </div>

      {!meeting ? (
        <div className="dropdown-group">
          <div className="dropdown-group-title">Start Meeting</div>
          <div className="meeting-inline-edit">
            <input value={startTitleDraft} onChange={(event) => setStartTitleDraft(event.target.value)} placeholder="Meeting title" />
            <button type="button" className="primary" onClick={() => void startMeeting()} disabled={saving === "start"}>
              {saving === "start" ? "Starting" : "Start"}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="dropdown-group">
            <div className="dropdown-group-title">Title</div>
            <div className="meeting-inline-edit">
              <input value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} placeholder="Meeting title" />
              <button type="button" className="secondary" onClick={() => void updateTitle()} disabled={!titleDraft.trim() || saving === "title"}>
                Save
              </button>
            </div>
            <div className="muted">Meeting ID: {meeting.meeting_id}</div>
          </div>

          {MEETING_SECTION_CONFIG.map((section) => (
            <div key={section.key} className="dropdown-group">
              <div className="dropdown-group-title">{section.label}</div>
              <div className="meeting-item-list">
                {meeting[section.key].length ? (
                  meeting[section.key].map((item, index) => (
                    <div key={`${section.key}-${index}-${item}`} className="meeting-item-row">
                      <input
                        value={sectionDrafts[section.key]?.[index] || ""}
                        onChange={(event) =>
                          setSectionDrafts((current) => {
                            const next = [...(current[section.key] || [])];
                            next[index] = event.target.value;
                            return { ...current, [section.key]: next };
                          })
                        }
                      />
                      <button
                        type="button"
                        className="secondary meeting-compact-button"
                        onClick={() => void updateItem(section.key, index)}
                        disabled={saving === `update-${section.key}-${index}`}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="danger meeting-compact-button"
                        onClick={() => void deleteItem(section.key, index)}
                        disabled={saving === `delete-${section.key}-${index}`}
                      >
                        Delete
                      </button>
                    </div>
                  ))
                ) : (
                  <div className="muted">No items yet.</div>
                )}
              </div>
              <div className="meeting-inline-edit">
                <input
                  value={addDrafts[section.key]}
                  onChange={(event) => setAddDrafts((current) => ({ ...current, [section.key]: event.target.value }))}
                  placeholder={`Add ${section.label.toLowerCase()}`}
                />
                <button
                  type="button"
                  className="primary"
                  onClick={() => void addItem(section.key)}
                  disabled={!addDrafts[section.key].trim() || saving === `add-${section.key}`}
                >
                  Add
                </button>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
