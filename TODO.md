# Veridex TODO

Last updated: 2026-06-28

## Current Focus

- Stabilize core behavior before feature expansion.
- Keep Veridex as the source of truth for workspace, session, room, file, artifact, and transcript state.
- Preserve the current stripped-down UI until backend behavior is reliable.
- Make normal chat feel conversational while keeping explicit system commands deterministic.
- Keep startup and smoke testing simple enough to diagnose without guessing.

## Immediate Priorities

1. Conversational intent layer
   - Normal chat should be the default.
   - Explicit commands should still route deterministically.
   - Ambiguous requests should ask a clarifying question.
   - Recent chat context should only be used for clear follow-ups, not broad room/capability questions.

2. Request orchestration cleanup
   - Search/tool execution flow is now extracted from `app.py` into a focused helper module.
   - Keep `/request` focused on request lifecycle and transcript recording.
   - Keep routing decisions in one testable layer.

3. Frontend chat cleanup follow-up
   - Initial `chat/page.tsx` split is complete as of `322c6b2`.
   - Keep future cleanup narrow and behavior-preserving.
   - Workspace/session lifecycle logic has now been split into focused hooks; keep any further cleanup narrow and behavior-preserving.

4. Runtime/Git hygiene
   - Remove generated runtime state from tracked source control in a careful patch. (`office_app/runtime/` is already out of the Git index, and `office_app/backend/incident_log.csv` is now ignored and removed from the index without deleting the local file.)
   - Do not delete local user data.
   - Keep `.env.local`, local certs, storage, logs, and runtime databases ignored.

5. Documentation alignment
   - `README.md` and `VERIDEX_THREAD_HANDOFF.md` have been updated for the `322c6b2` chat cleanup checkpoint.
   - Treat older architecture docs as design intent unless recently updated.
   - Update handoff docs after major stabilization milestones.

## Suggested Future Steps

1. Open a review PR for `fix/stabilization-setup`
   - Use the pushed `322c6b2` checkpoint as the review base.
   - Keep the PR focused on stabilization and frontend chat cleanup.
   - Include build and smoke-test results in the PR body.

2. Run a deeper behavior pass before more refactors
   - Exercise session switching, workspace switching, room switching, file upload/download, document reader, and integration confirmation.
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
   - Conference Room now supports agenda artifact creation plus create/update/cancel calendar preparation from explicit requests.
   - The in-app helper for collaboration shortcuts and room examples is in place on the chat status surface.
   - The room directory and room status surface now show short capability summaries so room selection is easier to scan.
   - Sales and Marketing now route explicit research requests for demographics, trends, audiences, and competitors to governed web search without requiring the phrase `search the web`.
   - Memo hardening now routes `show recent memos`, `memo inbox`, and `read memo <memo_id>` to the memo tools.
   - Memo list output now includes compact reply status, reply persona/room, and refusal metadata.
   - Collaboration routing now covers common phrasing for Marketing, Art Department, Finance, and Law Office while keeping Break Room non-operational.
   - Memo replies are sanitized so model text cannot claim external side effects such as sent email or scheduled calendar events.
   - Optional next meeting workflow: tighter meeting-state persistence if the current chat-first flow proves insufficient.
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
