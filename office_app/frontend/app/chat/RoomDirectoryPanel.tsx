import { ROOM_GROUPS, ROOMS } from "@/lib/rooms";

type RoomDirectoryPanelProps = {
  activeRoom: string;
  onRoomSelect: (roomId: string) => void;
};

export function RoomDirectoryPanel({ activeRoom, onRoomSelect }: RoomDirectoryPanelProps) {
  return (
    <div className="dropdown-panel">
      {ROOM_GROUPS.map((group) => (
        <div key={group} className="dropdown-group">
          <div className="dropdown-group-title">{group}</div>
          <div className="dropdown-grid">
            {ROOMS.filter((room) => room.group === group).map((room) => (
              <button
                key={room.id}
                type="button"
                className={`ghost room-option ${room.id === activeRoom ? "toolbar-button-active" : ""}`}
                onClick={() => onRoomSelect(room.id)}
              >
                <span>{room.title}</span>
                <span className="room-option-persona">{room.persona}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
