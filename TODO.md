# Veridex TODO

Last updated: 2026-07-07

## Current Focus

- Stabilize core behavior before feature expansion.
- Keep Veridex as the source of truth for workspace, session, room, file, artifact, and transcript state.
- Preserve the current stripped-down UI until backend behavior is reliable.
- Make normal chat feel conversational while keeping explicit system commands deterministic.
- Keep startup and smoke testing simple enough to diagnose without guessing.
- Current branch: `feat/routing-followup-reliability`.
- Current active slice: Navigator read-only diagnostics. Navigator can now report Veridex health, recent incidents/log tails, safe config readiness, active room/persona state, and explain common error categories without arbitrary shell access.

## Immediate Priorities

1. Conversational intent layer
   - Normal chat should be the default.
   - Explicit commands should still route deterministically.
   - Ambiguous requests should ask a clarifying question.
   - Recent chat context should only be used for clear follow-ups, not broad room/capability questions.
   - Routing follow-up reliability is in place for ambiguous short choice follow-ups after unverified/no-info entity answers while anchored option-list follow-ups still rewrite safely.
   - Ambiguous and reflective follow-ups after unverified/no-info entity answers now fail closed with clarification instead of falling through to normal model chat.

2. Request orchestration cleanup
   - Search/tool execution flow is now extracted from `app.py` into a focused helper module.
   - Keep `/request` focused on request lifecycle and transcript recording.
   - Keep routing decisions in one testable layer.
   - Full validation should be re-run after the next backend cleanup slice.

3. Frontend chat cleanup follow-up
   - Initial `chat/page.tsx` split and workspace/session hook extraction are complete as of `f1919ed`.
   - Keep future cleanup narrow and behavior-preserving.
   - Workspace/session lifecycle logic has now been split into focused hooks; keep any further cleanup narrow and behavior-preserving.
   - Nancy now has guided pending-email compose state in chat and a contact-card Email action entry point.
   - Chat now shows an active-work strip backed by durable workspace work context. It hydrates from `office.state_get`, refreshes after relevant chat/tool actions, and updates immediately on room/session/workspace navigation responses.

4. Runtime/Git hygiene
   - Remove generated runtime state from tracked source control in a careful patch. (`office_app/runtime/` is already out of the Git index, and `office_app/backend/incident_log.csv` is now ignored and removed from the index without deleting the local file.)
   - Do not delete local user data.
   - Keep `.env.local`, local certs, storage, logs, and runtime databases ignored.

5. Documentation alignment
   - `VERIDEX_THREAD_HANDOFF.md` now tracks branch `feat/routing-followup-reliability`, the durable cross-room work context slice, and the latest validation baseline.
   - Treat older architecture docs as design intent unless recently updated.
   - Update handoff docs after major stabilization milestones.

6. Navigator diagnostics
   - `office.navigator_status_report`, `office.navigator_recent_errors`, and `office.navigator_explain_error` are read-only governed tools.
   - Navigator diagnostics are available through the shared navigation capability group so they can be used from normal rooms.
   - Future Navigator expansion should stay allowlisted: add safe test execution before any proactive or self-healing behavior.

## Suggested Future Steps

1. Review the durable work-context continuity checkpoint
   - Review `WorkContextService`, `office.work_context_*` tools, active-work routing, Nancy email context capture, memo context capture, and the chat active-work strip together.
   - Confirm active work survives reloads, room switches, session switches, workspace switches, and app restarts.
   - Confirm replacing the current manual work focus does not accumulate stale active items; `set current work to ...` should replace the singular current focus while `track active work: ...` can still append.
   - Confirm Nancy Gmail send confirmations remain actionable after reload and room/session/workspace navigation, not just visible as passive reminders.
   - Confirm pending Nancy compose state itself reappears after reload and navigation with the correct next-step guidance, including off-office routing hints when Nancy mode is required.
   - Confirm replacement-session naming prompts survive reload and session/workspace navigation when the backend still has a pending session-name request.
   - Confirm pending session-rename prompts survive reload and session/workspace navigation, and reuse the session-name modal in explicit rename mode instead of relying on remembered conversational context.
   - Confirm pending session-list confirmations survive reload and room/session/workspace navigation with explicit `List Sessions` / `Not Now` recovery actions instead of relying on remembered yes/no context.
   - Confirm pending workspace-switch confirmations survive reload and navigation with explicit `Switch Now` / `Stay Here` recovery actions instead of relying on the user remembering a yes/no follow-up.
   - Confirm pending room-navigation confirmations survive reload and navigation with explicit `Move Now` / `Stay Here` recovery actions instead of relying on remembered yes/no context.
   - Confirm cancel/negative responses clear pending continuity UI immediately in the active chat surface, not only after a later reload or hydration pass.
   - Confirm non-Gmail integration confirmations, especially calendar create/update/cancel, stay actionable after reload and navigation instead of surviving only in the integration pending-action store.
   - Connected-account live audits now prove Gmail-send and Calendar-create confirmations can be created without executing the external action, persist into active work context, survive state reads and room switching, and be explicitly dismissed for cleanup.
   - Keep the branch focused on continuity stabilization before adding broader task/project management behavior.
   - Decide whether to keep this as a single stabilization review checkpoint or split it before opening review.

2. Run a deeper behavior pass before more refactors
   - Exercise session switching, workspace switching, room switching, file upload/download, document reader, and integration confirmation.
   - Run `office_app\work_context_smoke.ps1` after continuity changes to verify active work survives state hydration, room switching, session activation, workspace activation, and completion.
   - Run `office_app\work_context_smoke.ps1 -RestartBackend` when persistence changes to verify active work survives a managed restart.
   - Capture any regressions as focused issues before editing more code.
   - Prefer fixing observed behavior over speculative cleanup.

3. Finish live integration smoke checks
   - Reconnect Canva so brand-kit access includes `brandkit:read`.
   - Connect Google from Profile, then run `office_app\integration_smoke.ps1` with the active Veridex `session_id`.
   - Keep the pass count-only unless deeper private-data testing is explicitly approved.

4. Add targeted frontend tests around extracted chat pieces
   - Minimal `vitest` coverage now exists for extracted pure chat helpers.
   - Cover `visibleMessagesForScope`, transcript rendering, confirmation buttons, and file panel empty states.
   - Keep tests close to the extracted helper/component boundaries.
   - Avoid broad browser automation until the chat behavior is stable.

5. Finish Art Department image generation provider setup
   - Add Gemini image-generation quota or switch `GEMINI_IMAGE_MODEL`/provider to a key with image access.
   - Re-run `office_app\image_generation_smoke.ps1` when quota or provider access changes.
   - Verify the generated image appears as a room-scoped workspace file with `kind=generated_image`.

6. Finish the free-first Bing image workflow
   - Manual workflow is now documented in `README.md`.
   - Use Microsoft Designer/Bing Image Creator manually for no-cost generations.
   - Keep the upload target as a room-scoped Art Department file after the user downloads the selected image.
   - Optional future improvement: add an in-app hint or helper note near Art Department image requests.

7. Continue optional `page.tsx` controller cleanup only if needed
   - Best next target: workspace/session lifecycle logic.
   - Move one workflow at a time into a hook only when the inputs/outputs are clear.
   - Run `npm.cmd run build` and the smoke test after each slice.

8. Extend department workflow coverage
   - Durable work context now persists active cross-room work in `work_context.json` per workspace and exposes `office.work_context_save`, `office.work_context_list`, and `office.work_context_complete`.
   - Active work context is included in `office.state_get`, `office.room_set`, `office.session_activate`, and `office.workspace_activate` so room/session/workspace transitions carry the same continuity state.
   - Nancy email compose/send-confirmation state and memo dispatch now record work context so ongoing cross-room work remains visible until completed.
   - AI generation receives active work context as model context so room assistants can stay aware of durable work without relying only on recent chat.
   - Conference Room now supports agenda artifact creation plus create/update/cancel calendar preparation from explicit requests.
   - Conference Room now persists internal meeting state through `MeetingStateStore` for start meeting, agenda items, decisions, action items, parking-lot items, and show meeting state without implying Google Calendar writes.
   - Conference Room now has an in-app Meeting panel for editing the active meeting title and ordered meeting items, deleting items, saving deterministic meeting brief artifacts, and saving optional AI-polished brief artifacts separately.
   - The in-app helper for collaboration shortcuts and room examples is in place on the chat status surface.
   - The room directory and room status surface now show short capability summaries so room selection is easier to scan.
   - Sales and Marketing now route explicit research requests for demographics, trends, audiences, and competitors to governed web search without requiring the phrase `search the web`.
   - Memo hardening now routes `show recent memos`, `memo inbox`, and `read memo <memo_id>` to the memo tools.
   - Memo list output now includes compact reply status, reply persona/room, and refusal metadata.
   - Collaboration routing now covers common phrasing for Marketing, Art Department, Finance, and Law Office while keeping Break Room non-operational.
   - Memo replies are sanitized so model text cannot claim external side effects such as sent email or scheduled calendar events.
   - `/call` now forwards the `X-Session-Id` header into tool arguments so room switches persist into subsequent `/request` calls for the active session.
   - Keep routing additions narrow and covered by backend tests.

9. Lock down runtime/Git hygiene
   - Confirm generated runtime files stay ignored.
   - Verify `.env.local`, local certs, logs, runtime databases, and user data are not staged.
   - Do not delete local runtime data while cleaning Git tracking.

## Search

Current provider order:

1. SerpAPI
2. Google Custom Search
3. DuckDuckGo fallback

Notes:

- SerpAPI is the preferred general web search path.
- Google Programmable Search whole-web mode is deprecated for new engines, so it should not be relied on as the main whole-web provider.
- DuckDuckGo remains useful as a no-key fallback.
- Search answers should be synthesized conversationally by the model instead of dumping raw result text.

## Model Providers

Current intended provider behavior:

- Gemini remains the primary conversation provider when configured.
- Groq remains a fallback when configured.
- OpenRouter remains optional and should only be used when enabled.

Keep provider configuration in `.env.local`, not in committed files.

## Startup / Operations

Preferred app restart:

```powershell
cd C:\Office-App
.\veridex.cmd restart
```

Backend manual start:

```cmd
cd /d C:\Office-App
run_server.cmd
```

Frontend manual start:

```cmd
cd /d C:\Office-App\office_app\frontend
node server.cjs
```

Smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1
```

Deep smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1 -Deep
```

Work context continuity smoke:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\work_context_smoke.ps1
```

Managed-restart persistence smoke:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\work_context_smoke.ps1 -RestartBackend
```

## Deferred UI Work

- Visual polish.
- Room interior graphics.
- Draggable/movable page elements.
- Overlay selection tools.
- Richer room navigation.
- Dedicated admin/control panel.

Do not resume these until core chat, search, session, file, and startup behavior remain stable through repeated smoke tests.

## Do Not Do Yet

- Do not add another agent framework as a source of truth.
- Do not let browser/search tools own Veridex memory.
- Do not create separate durable room memory.
- Do not expand the UI before the split chat surface remains stable through repeated smoke tests.
- Do not replace the router with model-only behavior; explicit commands still need backend authority.
