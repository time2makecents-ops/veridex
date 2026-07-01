export type RoomInfo = {
  id: string;
  title: string;
  persona: string;
  capability: string;
  group: "Core" | "Departments" | "Special";
};

export const ROOMS: RoomInfo[] = [
  { id: "lobby", title: "Lobby", persona: "Receptionist", capability: "Intake, routing, and onboarding.", group: "Core" },
  { id: "conference_room", title: "Conference Room", persona: "Facilitator", capability: "Agenda planning, meeting prep, and cross-department coordination.", group: "Core" },
  { id: "control_room", title: "Control Room", persona: "Navigator", capability: "Governance checks, routing diagnostics, and policy review.", group: "Core" },
  { id: "my_office", title: "My Office", persona: "Nancy", capability: "Executive support, scheduling, and final admin handoff.", group: "Core" },
  { id: "records_archive", title: "Records Archive", persona: "Archivist", capability: "Durable storage, retrieval, and version-tracked records.", group: "Core" },
  { id: "infrastructure_room", title: "Infrastructure Room", persona: "Infrastructure Manager", capability: "Runtime operations, deployment follow-up, and diagnostics.", group: "Departments" },
  { id: "sales_department", title: "Sales Department", persona: "Sales Director", capability: "Lead research, demographics, outreach strategy, and deal planning.", group: "Departments" },
  { id: "marketing_room", title: "Marketing & Advertising", persona: "Marketing Director", capability: "Campaign strategy, market research, and content planning.", group: "Departments" },
  { id: "hr_department", title: "HR Department", persona: "HR Manager", capability: "Personnel policy, hiring support, and internal process drafting.", group: "Departments" },
  { id: "it_department", title: "IT Department", persona: "IT Administrator", capability: "Technical support, networking, and implementation guidance.", group: "Departments" },
  { id: "art_department", title: "Art Department", persona: "Creative Director", capability: "Visual design, image generation, and brand assets.", group: "Departments" },
  { id: "law_office", title: "Law Office", persona: "Legal Counsel", capability: "Legal-risk review, contracts, and regulatory awareness.", group: "Departments" },
  { id: "finance_department", title: "Finance Department", persona: "Finance Director", capability: "Budgeting, pricing, accounting, and financial tracking.", group: "Departments" },
  { id: "rnd_room", title: "R&D", persona: "R&D Director", capability: "Invention, technical research, and prototyping.", group: "Departments" },
  { id: "security_room", title: "Security Room", persona: "Security Chief", capability: "Threat modeling, security review, and drills.", group: "Departments" },
  { id: "vr_room", title: "VR Room", persona: "Simulation Guide", capability: "Simulation, sandboxing, and rule experiments.", group: "Special" },
  { id: "break_room", title: "Break Room", persona: "Break Room Host", capability: "Casual conversation and low-stakes breaks.", group: "Special" },
];

export const ROOM_GROUPS: RoomInfo["group"][] = ["Core", "Departments", "Special"];
