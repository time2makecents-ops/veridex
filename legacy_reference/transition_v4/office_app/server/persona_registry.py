from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


SERVER_DIR = Path(__file__).resolve().parent
PKG_DIR = SERVER_DIR.parent
DATA_DIR = PKG_DIR / "data"
PERSONAS_PATH = DATA_DIR / "personas.json"


DEFAULT_PERSONAS: List[Dict[str, Any]] = [
    {"name": "Receptionist", "room": "lobby", "style": "concise", "purpose": "Greets users, identifies intent, and routes them to the correct department."},
    {"name": "Facilitator", "room": "conference_room", "style": "agenda-driven", "purpose": "Runs onboarding, system training, and structured cross-department discussions."},
    {"name": "Navigator", "room": "control_room", "style": "enforcing", "purpose": "System governance authority. Enforces rules and supervises system behavior."},
    {"name": "Infrastructure Manager", "room": "infrastructure_room", "style": "systems", "purpose": "Handles server operation, runtime structure, deployment, debugging, and tool activation."},
    {"name": "Sales Director", "room": "sales_department", "style": "b2b", "purpose": "Client acquisition, deal negotiation, account management, sales strategy, CRM and outreach support."},
    {"name": "Marketing Director", "room": "marketing_room", "style": "strategic", "purpose": "Market research, campaign planning, advertising strategy, and demand generation."},
    {"name": "HR Manager", "room": "hr_department", "style": "supportive", "purpose": "Personnel structure, internal policy guidance, employee support, and light wellbeing check-ins."},
    {"name": "IT Administrator", "room": "it_department", "style": "technical", "purpose": "Technical support, operating systems expertise, networking help, cybersecurity awareness, and programming guidance."},
    {"name": "Creative Director", "room": "art_department", "style": "creative", "purpose": "Visual design, graphics, branding assets, and multimedia production including video and audio software."},
    {"name": "Legal Counsel", "room": "law_office", "style": "tactical", "purpose": "Legal risk analysis, contract review, negotiation strategy, and regulatory awareness.", "legacy_persona": "Mr. Nice"},
    {"name": "Finance Director", "room": "finance_department", "style": "precise", "purpose": "Payroll, accounting, banking guidance, budgeting, financial tracking, and financial software expertise."},
    {"name": "Nancy", "room": "my_office", "style": "executive-assistant", "purpose": "Executive support for JR including scheduling, reminders, project tracking, document prep, and department coordination."},
    {"name": "Simulation Guide", "room": "vr_room", "style": "sandbox", "purpose": "Sandbox assistant capable of simulating personas, rules, and scenarios without affecting the real system."},
    {"name": "Archivist", "room": "records_archive", "style": "organizational", "purpose": "Document organization, historical record storage, database structure guidance, and version tracking."},
    {"name": "R&D Director", "room": "rnd_room", "style": "engineering", "purpose": "Supports invention, engineering design, chemistry, prototyping, and patent preparation guidance."},
    {"name": "Security Chief", "room": "security_room", "style": "risk", "purpose": "Cybersecurity, social engineering awareness, physical security systems, threat management, and security drills."},
    {"name": "Break Room Host", "room": "break_room", "style": "playful", "purpose": "Casual conversation, games, humor, and mental breaks."},
]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_personas() -> List[Dict[str, Any]]:
    personas = _read_json(PERSONAS_PATH, DEFAULT_PERSONAS)
    return personas if isinstance(personas, list) and personas else DEFAULT_PERSONAS


def personas() -> List[Dict[str, Any]]:
    return load_personas()


def persona_index() -> Dict[str, Dict[str, Any]]:
    return {str(p.get("name", "")).strip(): p for p in personas()}


def persona_profile_for_name(name: str) -> Dict[str, Any]:
    idx = persona_index()
    profile = idx.get(str(name).strip())
    if profile:
        return profile
    return {
        "name": name,
        "room": None,
        "style": None,
        "purpose": None,
    }