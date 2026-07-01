import { roomById } from "./helpers";
import { shouldShowMeetingWorkspace } from "./meetingWorkspace";

type ChatToolbarProps = {
  activeRoom: string;
  loadMenuOpen: boolean;
  meetingMenuOpen: boolean;
  recentRooms: string[];
  roomMenuOpen: boolean;
  saveMenuOpen: boolean;
  sessionMenuOpen: boolean;
  onLoadMenuToggle: () => void;
  onMeetingMenuToggle: () => void;
  onRoomMenuToggle: () => void;
  onRoomSelect: (roomId: string) => void;
  onSaveMenuToggle: () => void;
  onSessionMenuToggle: () => void;
};

export function ChatToolbar({
  activeRoom,
  loadMenuOpen,
  meetingMenuOpen,
  recentRooms,
  roomMenuOpen,
  saveMenuOpen,
  sessionMenuOpen,
  onLoadMenuToggle,
  onMeetingMenuToggle,
  onRoomMenuToggle,
  onRoomSelect,
  onSaveMenuToggle,
  onSessionMenuToggle,
}: ChatToolbarProps) {
  return (
    <div className="toolbar-row">
      <button
        type="button"
        className={`ghost toolbar-button ${roomMenuOpen ? "toolbar-button-active" : ""}`}
        onClick={onRoomMenuToggle}
      >
        Directory
      </button>
      <button
        type="button"
        className={`ghost toolbar-button ${sessionMenuOpen ? "toolbar-button-active" : ""}`}
        onClick={onSessionMenuToggle}
      >
        Sessions
      </button>
      {recentRooms.map((roomId) => {
        const room = roomById(roomId);
        return (
          <button
            key={roomId}
            type="button"
            className={`ghost toolbar-button ${roomId === activeRoom ? "toolbar-button-active" : ""}`}
            onClick={() => onRoomSelect(roomId)}
          >
            {room?.title || roomId}
          </button>
        );
      })}
      {shouldShowMeetingWorkspace(activeRoom) ? (
        <button
          type="button"
          className={`ghost toolbar-button ${meetingMenuOpen ? "toolbar-button-active" : ""}`}
          onClick={onMeetingMenuToggle}
        >
          Meeting
        </button>
      ) : null}
      <button
        type="button"
        className={`ghost toolbar-button ${saveMenuOpen ? "toolbar-button-active" : ""}`}
        onClick={onSaveMenuToggle}
      >
        Save
      </button>
      <button
        type="button"
        className={`ghost toolbar-button ${loadMenuOpen ? "toolbar-button-active" : ""}`}
        onClick={onLoadMenuToggle}
      >
        Load
      </button>
    </div>
  );
}
