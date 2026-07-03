# Nancy Cleanup Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the current Nancy compose/contact-card work by refreshing stale docs and reducing backend cleanup friction without changing behavior.

**Architecture:** Keep the user-facing flow intact. The cleanup work is split into one docs slice that realigns the handoff state with the current repo and one backend slice that removes duplicated Nancy email state handling around `/request` while preserving the existing compose/cancel/send behavior.

**Tech Stack:** Markdown docs, Python/FastAPI, Next.js/TypeScript, unittest, Vitest

---

### Task 1: Refresh stale Veridex docs

**Files:**
- Modify: `TODO.md`
- Modify: `VERIDEX_THREAD_HANDOFF.md`

- [ ] **Step 1: Update the live checkpoint text**

Update the current-focus and handoff sections so they describe the current Nancy compose/contact-card work instead of older routing-only language. Call out that the active branch now has pending-email compose state, contact-card email entry, and the latest validation baseline.

- [ ] **Step 2: Remove stale cleanup notes**

Trim or rewrite any TODO entries that still describe the current Nancy/email work as future cleanup. Keep only the remaining real follow-up items, and make sure the branch/checkpoint references match the current repository state.

- [ ] **Step 3: Verify the docs diff**

Run:

```powershell
git diff --check
```

Expected: no whitespace or patch-format errors.

- [ ] **Step 4: Review the updated handoff**

Open the edited docs and confirm they now point the next worker at the correct current state, with no obsolete checkpoint or branch wording left behind.

### Task 2: Simplify Nancy email state handling in the backend

**Files:**
- Modify: `office_app/server/app.py`
- Modify: `office_app/server/request_pipeline.py`
- Modify: `office_app/server/handlers/integration_handlers.py`
- Modify tests in: `office_app/server/test_natural_language_routing.py`

- [ ] **Step 1: Tighten the test coverage around pending Nancy email state**

Add or adjust unit coverage so the backend proves these cases still work after cleanup:

- starting a Nancy email draft from a contact card still seeds subject collection
- pending Nancy email state clears on cancel
- direct send confirmation still clears pending state after a Gmail send route

- [ ] **Step 2: Collapse the duplicated pending-state plumbing**

Refactor the Nancy email pending-state write path so clarify/tool responses use one helper path, and keep the pending state payload shape consistent across the contact-resolution, recipient prompt, subject prompt, and send-confirmation branches.

- [ ] **Step 3: Remove the rough edges in the compose router**

Clean up the `route_nancy_email_compose_request` flow so the pending-state branch reads clearly and the direct-email branches do not repeat the same state-shaping logic. Preserve the current behavior for guided compose, direct compose, reply follow-ups, and cancel handling.

- [ ] **Step 4: Run backend validation**

Run:

```powershell
python -m unittest discover -s office_app/server -p "test_*.py"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1
```

Expected: all backend tests pass, and the smoke test still reports the backend and frontend as healthy.

**Assumptions:**
- Keep the current Nancy compose behavior and contact-card UX unchanged.
- Do not expand this into a broader chat refactor.
- Recommended model: `5.5 high`
