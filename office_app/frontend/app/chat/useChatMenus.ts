import { useState } from "react";

import type { AttachmentMode } from "./types";

export function useChatMenus() {
  const [roomMenuOpen, setRoomMenuOpen] = useState(false);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [saveMenuOpen, setSaveMenuOpen] = useState(false);
  const [loadMenuOpen, setLoadMenuOpen] = useState(false);
  const [meetingMenuOpen, setMeetingMenuOpen] = useState(false);
  const [memoMenuOpen, setMemoMenuOpen] = useState(false);
  const [attachmentOpen, setAttachmentOpen] = useState(false);
  const [attachmentMode, setAttachmentMode] = useState<AttachmentMode>("download");

  function closeHeaderMenus(except?: "workspace" | "room" | "session" | "save" | "load" | "meeting" | "memo" | "attachment") {
    if (except !== "workspace") {
      setWorkspaceMenuOpen(false);
    }
    if (except !== "room") {
      setRoomMenuOpen(false);
    }
    if (except !== "session") {
      setSessionMenuOpen(false);
    }
    if (except !== "save") {
      setSaveMenuOpen(false);
    }
    if (except !== "load") {
      setLoadMenuOpen(false);
    }
    if (except !== "meeting") {
      setMeetingMenuOpen(false);
    }
    if (except !== "memo") {
      setMemoMenuOpen(false);
    }
    if (except !== "attachment") {
      setAttachmentOpen(false);
    }
  }

  function closeAllMenus() {
    setWorkspaceMenuOpen(false);
    setRoomMenuOpen(false);
    setSessionMenuOpen(false);
    setSaveMenuOpen(false);
    setLoadMenuOpen(false);
    setMeetingMenuOpen(false);
    setMemoMenuOpen(false);
    setAttachmentOpen(false);
  }

  function toggleWorkspaceMenu() {
    closeHeaderMenus("workspace");
    setWorkspaceMenuOpen((current) => !current);
  }

  function toggleRoomMenu() {
    closeHeaderMenus("room");
    setRoomMenuOpen((current) => !current);
  }

  function toggleSessionMenu() {
    closeHeaderMenus("session");
    setSessionMenuOpen((current) => !current);
  }

  function toggleSaveMenu() {
    closeHeaderMenus("save");
    setSaveMenuOpen((current) => !current);
  }

  function toggleLoadMenu() {
    closeHeaderMenus("load");
    setLoadMenuOpen((current) => !current);
  }

  function toggleMeetingMenu() {
    closeHeaderMenus("meeting");
    setMeetingMenuOpen((current) => !current);
  }

  function toggleMemoMenu() {
    closeHeaderMenus("memo");
    setMemoMenuOpen((current) => !current);
  }

  function toggleAttachmentPanel() {
    closeHeaderMenus("attachment");
    setAttachmentMode("download");
    setAttachmentOpen((current) => !current);
  }

  return {
    attachmentMode,
    attachmentOpen,
    loadMenuOpen,
    meetingMenuOpen,
    memoMenuOpen,
    roomMenuOpen,
    saveMenuOpen,
    sessionMenuOpen,
    workspaceMenuOpen,
    setAttachmentMode,
    setLoadMenuOpen,
    setMeetingMenuOpen,
    setMemoMenuOpen,
    setRoomMenuOpen,
    setSaveMenuOpen,
    setSessionMenuOpen,
    setWorkspaceMenuOpen,
    closeAllMenus,
    toggleAttachmentPanel,
    toggleLoadMenu,
    toggleMeetingMenu,
    toggleMemoMenu,
    toggleRoomMenu,
    toggleSaveMenu,
    toggleSessionMenu,
    toggleWorkspaceMenu,
  };
}
