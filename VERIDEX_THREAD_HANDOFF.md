# VERIDEX THREAD HANDOFF
Project: Veridex (formerly Office-App)
Developer: JR
Environment: FastAPI backend
Purpose: Preserve system intent, architecture, and implementation state so development can continue in a new thread without design drift.

---

# 1. SYSTEM PURPOSE

Veridex is an **operating environment accessed through conversational interaction**.

Instead of interacting with a traditional application UI, the user operates inside a **structured office environment** composed of rooms, assistants, and departments.

The system combines:

• conversational interface  
• structured office model  
• modular backend services  

The goal is to create a **persistent work environment** where projects, artifacts, assistants, and commands coexist in a structured system rather than disconnected chat threads.

Veridex should behave more like an **operating system for workspaces** than a chatbot.

---

# 2. INTERACTION MODEL

The office metaphor is **structural**, not cosmetic.

Users interact with the system through:

### Rooms
Rooms represent functional areas.

Examples:
- Lobby
- My Office
- Marketing Department
- Engineering Lab
- Records Archive

Rules:

• only one room is active at a time  
• entering a new room closes the previous room  
• rooms expose specialized capabilities  

---

### Personas

Rooms contain personas responsible for tasks.

Examples:

Receptionist  
Nancy (executive assistant)  
Archivist  
Engineer  

Rules:

• persona behavior belongs to the room  
• personas should not overlap responsibilities  
• personas represent system authority for their domain  

---

### Nancy

Nancy is the **Executive Assistant persona**.

Rules:

• Nancy resides in **My Office**
• Nancy can be accessed globally
• Nancy assists with coordination, retrieval, and organization

Nancy does NOT replace the command router or system authority.

---

### Artifacts

Artifacts are structured outputs produced by the system.

Examples:

reports  
design documents  
exports  
audit files  

Artifacts must be storable in the Records Archive.

---

# 3. COMMAND MODEL

Commands are routed through a **Command Router**.

Commands are intentionally simple and conversational.

Examples:

go to marketing department  
list commands  
show audit  
save that  

Rules:

• commands route through router authority  
• commands should require minimal syntax  
• commands should feel conversational  

---

# 4. SAVE BEHAVIOR

Save is a **system-level command**.

User phrase:

save that

Behavior:

1. system captures the last produced artifact
2. router calls archive_service
3. artifact stored in Records Archive
4. Archivist confirms storage

Save should require **no additional confirmation unless ambiguity exists**.

---

# 5. CORE ARCHITECTURE

Current backend structure:

office_app/
server/

app.py  
command_router.py  
request_pipeline.py  
workspace_kernel.py  
workspace_store.py  
memo_service.py  
archive_service.py  
nancy_service.py  
tools_registry.py  
errors.py  

---

# 6. KEY COMPONENTS

### FastAPI Server

File: app.py

Responsibilities:

• HTTP endpoints  
• tool discovery  
• command execution  

---

### Command Router

File: command_router.py

Responsibilities:

• register commands  
• route commands to handlers  

Example registration:

router.register("office.workspaces_list", handler)

The router replaces conditional routing previously located in app.py.

---

### Tools Registry

File: tools_registry.py

Responsibilities:

• command registration  
• command discovery  
• /tools endpoint  

---

### Workspace Kernel

File: workspace_kernel.py

Responsibilities:

• active workspace state  
• workspace lifecycle control  

---

### Workspace Store

File: workspace_store.py

Responsibilities:

• workspace persistence  
• workspace lookup  
• workspace listing  

---

### Request Pipeline

File: request_pipeline.py

Responsibilities:

• normalize responses  
• enforce consistent response structure  

---

### Archive Service

File: archive_service.py

Responsibilities:

• artifact storage  
• artifact retrieval  

Supports the **Records Archive** concept.

---

### Nancy Service

File: nancy_service.py

Responsibilities:

• assistant coordination  
• document retrieval  
• task assistance  

Nancy is accessible globally but conceptually resides in **My Office**.

---

### Memo Service

File: memo_service.py

Responsibilities:

• inter-room communication  
• internal message routing  

Implements the **mailroom concept**.

---

### Error System

File: errors.py

Responsibilities:

• structured error responses  
• consistent error codes  

---

# 7. WORK COMPLETED IN THIS THREAD

Major architectural work completed:

• command router implemented  
• router separated from app.py  
• workspace kernel separated from persistence  
• tools registry centralized  
• archive service modularized  
• Nancy service modularized  
• request pipeline standardized  

Documentation created:

SOURCES.md  
VERIDEX_ARCHITECTURE_OVERVIEW.md  
V1_VS_CURRENT_ARCHITECTURE_AUDIT.md  
BEHAVIORAL_CONTRACT.md  

This thread also produced:

VERIDEX_THREAD_HANDOFF.md

---

# 8. ISSUES ENCOUNTERED AND RESOLVED

Router registration error:

NameError: router not defined

Cause:
command registration occurred before router initialization.

Resolution:
router initialization corrected.

---

Import path error:

ModuleNotFoundError: office_app

Cause:
running uvicorn from wrong working directory.

Resolution:
run uvicorn from project root.

---

# 9. CURRENT SYSTEM STATUS

Architecture: stable  
Router: operational  
Workspace system: functional  
Command discovery: functional  

Project state: **ready for feature expansion**

---

# 10. KNOWN DESIGN RULES

Important system behavior rules established in this thread:

• router is central command authority  
• commands should be conversational  
• rooms define capability scope  
• artifacts must be archivable  
• save that → automatic archive  

---

# 11. NEXT DEVELOPMENT TARGETS

Recommended next steps:

### Artifact System

Track artifacts produced by commands.

---

### Archive Integration

Connect artifact capture to:

save that

---

### Room Model

Implement formal room state management.

---

### Persona Layer

Explicit persona definitions and authority mapping.

---

### System Map

Create visual architecture documentation.

---

# 12. GUIDING PRINCIPLE

Veridex is **not a chatbot wrapper**.

It is a **workspace operating environment with conversational access**.

Architecture decisions must preserve:

• command router authority  
• modular services  
• artifact archive  
• room-based interaction model