# Repository Guidelines

## Project Structure & Module Organization

Veridex is a local FastAPI and Next.js application. Backend code lives in
`office_app/server`: `app.py` exposes HTTP endpoints, `handlers/` implements
tool actions, and services such as `workspace_kernel.py`, `user_service.py`,
and `workspace_file_service.py` own persistence and domain behavior. Backend
tests are colocated as `office_app/server/test_*.py`.

The frontend is in `office_app/frontend`. Next.js pages and API proxy routes
are under `app/`; browser-facing helpers are under `lib/`. Architecture and
behavior contracts at the repository root and in `01_Architecture/` are
reference material, not runtime source. Do not edit `legacy_reference/` when
changing the active application.

## Build, Test, and Development Commands

Run backend tests from the repository root:

```powershell
python -m unittest discover -s office_app/server -p "test_*.py"
python -m unittest office_app.server.test_ocr_service
```

Run frontend commands from `office_app/frontend`:

```powershell
npm.cmd run dev        # Next.js development server
npm.cmd run dev:https  # HTTPS development server via server.cjs
npm.cmd run build      # production build and TypeScript validation
```

Use focused tests while iterating, then run the relevant broader suite before
hand-off. The root `veridex.ps1` and `start_veridex_*.ps1` scripts are the
project startup helpers when the full local stack is needed.

## Model And Token Workflow

Use the smallest model that can safely handle the current slice.

- `gpt-5.4-mini` is the default for docs, Git status, narrow cleanup, and
  mechanical edits from a clear plan.
- `gpt-5.5` is the better choice for planning, architecture, broad refactors,
  backend routing, ambiguous debugging, search/model-provider behavior, or any
  risky cross-module change.
- If a stronger model is recommended, pause and switch before continuing the
  slice. During unattended automation, keep the current model and do not stop
  for a manual switch.
- When implementation is complete and the next step is validation, stop before
  running backend tests, frontend tests/builds, smoke tests, or live browser
  automation. Prompt the user to switch to `gpt-5.4-mini`, then continue with
  validation after the user resumes. Lightweight non-test checks such as
  `git status`, `git diff`, and targeted file inspection may still run before
  the model switch.
- Before long runs, check `/status` and `/usage`, and compact the thread when
  the context starts to grow.
- Prefer small reviewable slices and summarize tool output instead of dumping
  it.

## Coding Style & Naming Conventions

Use four spaces, type annotations, and `snake_case` names in Python. Keep
FastAPI route validation and authorization explicit; place tool behavior in
the appropriate handler/service rather than expanding `app.py`. Use
PascalCase React component names, camelCase TypeScript variables and helpers,
and follow existing CSS naming patterns. Make narrow changes; preserve
workspace, session, file, and admin boundaries.

## Testing Guidelines

Name tests `test_<behavior>` and cover both success and failure paths. Add a
backend test for every route, handler, or lifecycle change. Run `npm.cmd run
build` whenever frontend TypeScript or routes change. Tests should use
temporary runtime directories and must not append repository logs or audit
files.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects, for example `Fix OCR MIME fallback`
or `Add admin workspace detail inspection`. Keep commits scoped to one
behavioral change. In pull requests, describe user-visible behavior, list
tests run, link the issue when applicable, and include screenshots for UI
changes. Never commit `.env.local`, API keys, runtime databases, logs, or PID
files; use `.env.example` for configuration keys.
