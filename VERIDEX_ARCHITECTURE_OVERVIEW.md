# Veridex — Architecture Overview

This document defines the canonical architecture and operational model of the Veridex system.

Veridex is not a traditional chatbot. It is designed as a **structured AI operating environment** where specialized contexts ("rooms") execute tasks inside persistent workspaces under a governance layer.

This document explains the core entities, execution flow, and design principles that govern the system.

---

# System Concept

Veridex operates as a digital workspace environment.

Instead of a single conversational context, the system organizes work into **rooms** that represent specialized operational areas (similar to departments in an office).

Each workspace maintains the current state of the system while rooms execute tasks based on that state.

Key characteristics:

- workspace-centered architecture
- stateless room execution
- message-based internal coordination
- governance oversight through Navigator
- administrative coordination through Nancy
- strict architectural layering

---
# Interpretation Rules

This document defines the conceptual architecture of Veridex.

The descriptions here represent **design intent**, not necessarily the exact current implementation.

When reasoning about Veridex:

- Treat this document as the **authoritative description of system structure and principles**.
- Do not assume every module described here already exists in code.
- Do not infer hidden behavior not described in this document.
- If an implementation detail conflicts with this document, treat it as **implementation drift** rather than architectural truth.

The architecture defined here should guide reasoning about future development, system refactors, and design decisions.
# Core Entities

## Workspace

A workspace is the **primary container for system activity**.

All persistent state belongs to the workspace.

Examples of workspace state include:

- active room
- active persona
- conversation transcript
- task queue
- artifact references
- overlay participants
- workspace metadata

The workspace kernel is responsible for loading, updating, and persisting this state.

---

## Rooms

Rooms are **specialized execution environments** responsible for handling domain-specific work.

Examples may include:

- lobby
- conference room
- marketing room
- legal room
- stock room
- creative studio

Rooms function as **stateless processors**.

A room reads workspace state, performs domain-specific reasoning, and produces an output response.

Rooms must **never store persistent state internally**.

All durable information must be written back to the workspace runtime.

---

## Personas

Rooms may operate through personas representing specialized roles.

Examples include:

- receptionist
- marketing director
- legal counsel
- financial analyst
- creative director

Only **one room persona may be active at a time**.

This constraint helps prevent context drift and maintains clarity of role during execution.

---

## Navigator

Navigator is the **governance and control layer**.

Responsibilities include:

- enforcing architectural rules
- preventing invalid operations
- maintaining scope boundaries
- detecting conflicts
- ensuring system discipline

Navigator oversees the system but normally does not perform operational work.

Navigator intervenes only when rules must be enforced or conflicts arise.

---

## Nancy

Nancy is the **administrative coordination layer**.

Responsibilities include:

- coordinating cross-room tasks
- retrieving artifacts
- preparing communications
- organizing operational workflows
- assisting with scheduling and reminders

Nancy may initiate coordination between rooms when necessary.

Nancy cannot modify governance rules or canonical system artifacts.

---

# Messaging Model

Veridex uses an internal **memo-based communication system**.

Components communicate by sending memos through the mailroom routing layer rather than calling each other directly.

This design:

- preserves isolation between modules
- prevents circular dependencies
- allows flexible coordination across services

Typical memo uses include:

- requesting artifacts
- coordinating tasks
- notifying system components
- cross-room collaboration

---

# State Ownership

Persistent state is owned only by system runtime components.

State owners include:

- workspace kernel
- transcript log
- memo store
- artifact archive

Rooms themselves do **not own persistent state**.

Rooms execute logic and return results, but long-term data must be stored by the workspace runtime.

---

# Architectural Layers

The Veridex server follows a strict layered architecture.

Dependencies must flow downward only.
