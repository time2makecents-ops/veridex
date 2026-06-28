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
   - Move search result synthesis out of `app.py`.
   - Keep `/request` focused on request lifecycle and transcript recording.
   - Keep routing decisions in one testable layer.

3. Frontend chat cleanup follow-up
   - Initial `chat/page.tsx` split is complete as of `322c6b2`.
   - Keep future cleanup narrow and behavior-preserving.
   - Remaining work is optional refinement of workspace/session controller logic, not a blocker for the current checkpoint.

4. Runtime/Git hygiene
   - Remove generated runtime state from tracked source control in a careful patch. (In progress: `office_app/runtime/` removed from Git index without deleting local data.)
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

3. Add targeted frontend tests around extracted chat pieces
   - Cover `visibleMessagesForScope`, transcript rendering, confirmation buttons, and file panel empty states.
   - Keep tests close to the extracted helper/component boundaries.
   - Avoid broad browser automation until the chat behavior is stable.

4. Continue optional `page.tsx` controller cleanup only if needed
   - Best next target: workspace/session lifecycle logic.
   - Move one workflow at a time into a hook only when the inputs/outputs are clear.
   - Run `npm.cmd run build` and the smoke test after each slice.

5. Revisit backend request orchestration
   - Confirm search synthesis is no longer coupled to `app.py`.
   - Keep routing, transcript recording, and model response shaping testable in separate layers.
   - Run backend unit tests for any backend contract changes.

6. Lock down runtime/Git hygiene
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
