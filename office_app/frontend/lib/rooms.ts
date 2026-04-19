export type RoomInfo = {
  id: string;
  title: string;
  persona: string;
  group: "Core" | "Departments" | "Special";
};

export const ROOMS: RoomInfo[] = [
  { id: "lobby", title: "Lobby", persona: "Receptionist", group: "Core" },
  { id: "conference_room", title: "Conference Room", persona: "Facilitator", group: "Core" },
  { id: "control_room", title: "Control Room", persona: "Navigator", group: "Core" },
  { id: "my_office", title: "My Office", persona: "Nancy", group: "Core" },
  { id: "records_archive", title: "Records Archive", persona: "Archivist", group: "Core" },
  { id: "infrastructure_room", title: "Infrastructure Room", persona: "Infrastructure Manager", group: "Departments" },
  { id: "sales_department", title: "Sales Department", persona: "Sales Director", group: "Departments" },
  { id: "marketing_room", title: "Marketing & Advertising", persona: "Marketing Director", group: "Departments" },
  { id: "hr_department", title: "HR Department", persona: "HR Manager", group: "Departments" },
  { id: "it_department", title: "IT Department", persona: "IT Administrator", group: "Departments" },
  { id: "art_department", title: "Art Department", persona: "Creative Director", group: "Departments" },
  { id: "law_office", title: "Law Office", persona: "Legal Counsel", group: "Departments" },
  { id: "finance_department", title: "Finance Department", persona: "Finance Director", group: "Departments" },
  { id: "rnd_room", title: "R&D", persona: "R&D Director", group: "Departments" },
  { id: "security_room", title: "Security Room", persona: "Security Chief", group: "Departments" },
  { id: "vr_room", title: "VR Room", persona: "Simulation Guide", group: "Special" },
  { id: "break_room", title: "Break Room", persona: "Break Room Host", group: "Special" },
];

export const ROOM_GROUPS: RoomInfo["group"][] = ["Core", "Departments", "Special"];
