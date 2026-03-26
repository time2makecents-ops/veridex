# Veridex Behavioral Contract
Version: 1.0
Purpose: Define the behavioral rules of the Veridex system so implementation cannot drift from the intended operating model.

This document governs UX behavior, command expectations, and architectural intent.

---

# 1. Core System Model

Veridex operates as an **office simulation interface over a structured backend system**.

Users interact with:

• Rooms  
• Personas  
• Artifacts  
• Commands  

The system routes requests internally through a command router and service layer.

The office metaphor is **not cosmetic**. It defines interaction rules.

---

# 2. Room System

The system operates using rooms.

Examples:

Lobby  
My Office  
Marketing Department  
Archive  
Engineering Lab  

Rules:

• Only one room is active at a time  
• Moving to a new room closes the previous room  
• The receptionist controls room entry from Lobby  
• Rooms can expose specialized commands

Command example:

go to marketing department

Behavior:

system → closes current room  
system → activates marketing room

---

# 3. Personas

Rooms contain personas responsible for tasks.

Examples:

Receptionist  
Nancy (assistant)  
Archivist  
Engineer  

Rules:

• Persona behavior belongs to the room
• Persona responses must reflect role authority
• Personas should not overlap responsibilities

---

# 4. Nancy

Nancy is the **Executive Assistant persona**.

Rules:

• Nancy lives in **My Office**
• Nancy can be accessed globally
• Nancy helps coordinate tasks, retrieve documents, and organize work

Nancy does NOT:

• replace the command router
• replace room authority

Nancy assists — she does not control the system.

---

# 5. Command System

Commands are routed through the **Command Router**.

Commands are short natural phrases.

Examples:

save that  
show audit  
list commands  
go to archive  

Rules:

• Commands should require minimal syntax
• Commands should feel conversational
• Commands must route through the router layer

---

# 6. Save Behavior

Save is a **system-level command**.

User phrase:

save that

Behavior:

1. System captures the last produced artifact
2. Router calls archive_service
3. Artifact is stored in Records Archive
4. Archivist confirms the save

Save must require **no additional confirmation** unless ambiguity exists.

---

# 7. Records Archive

The archive stores artifacts.

Examples:

documents  
audit reports  
design files  
exports

Archive responsibilities:

• artifact storage
• artifact retrieval
• indexing

Archive responses come from the **Archivist persona**.

---

# 8. Artifact Definition

An artifact is any structured output produced by the system.

Examples:

audit documents  
design specs  
exports  
reports  

Artifacts must be archivable.

---

# 9. Command Discovery

Users must be able to discover commands.

Example commands:

list commands  
help  

These commands query the **tools registry**.

---

# 10. System Authority

Authority layers:

User  
→ Room Persona  
→ Command Router  
→ Services  
→ Data Store

The router is the **central traffic controller**.

Personas do not bypass the router.

---

# 11. Architecture Guardrails

Implementation must respect:

• modular services
• command router authority
• room-based UX
• artifact archive

No feature should bypass these structures.

---

# 12. Design Principle

Veridex is an **operating environment**, not a chatbot.

The experience should resemble interacting with a structured office system rather than issuing technical commands.
