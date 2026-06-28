import { roomById } from "./helpers";

type ChatToolbarProps = {
  activeRoom: string;
  loadMenuOpen: boolean;
  recentRooms: string[];
  roomMenuOpen: boolean;
  saveMenuOpen: boolean;
  sessionMenuOpen: boolean;
  onLoadMenuToggle: () => void;
  onRoomMenuToggle: () => void;
  onRoomSelect: (roomId: string) => void;
  onSaveMenuToggle: () => void;
  onSessionMenuToggle: () => void;
};

export function ChatToolbar({
  activeRoom,
  loadMenuOpen,
  recentRooms,
  roomMenuOpen,
  saveMenuOpen,
  sessionMenuOpen,
  onLoadMenuToggle,
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
