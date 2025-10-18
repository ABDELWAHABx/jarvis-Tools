# Project guidance for AI contributors

Welcome to the **Jarvis Tools API** workspace. This file explains how the repository is organised and captures the expectations for future automated contributions.

## Repository layout

- `tools-api/`
  - `app/`
    - `main.py`: FastAPI application entry point, router registration, and Jinja/Static configuration.
    - `routers/`: Individual FastAPI routers for parser, DOCX, media, JS bridges, etc. Keep endpoint logic self-contained per router.
    - `services/`: Supporting service layers (Cobalt gateway, shortcut registry, etc.). Prefer calling into these from routers instead of duplicating logic.
    - `templates/`
      - `layouts/`: Base HTML shells (Bootstrap 5). Extend these for any new pages.
      - `modules/`: Reusable Jinja partials representing tool panels or widgets. Compose pages from these blocks.
      - `pages/`: Concrete Studio pages such as `home.html`, `documents.html`, and `media.html`. Each should extend `layouts/base.html` and include the required modules.
    - `static/`
      - `css/`: Stylesheets for the Studio UI. `studio.css` contains the bulk of customisations on top of Bootstrap.
      - `js/`: Front-end scripts (`studio.js`) controlling sidebar toggles, async form submissions, etc.
  - `README.md`: High-level product overview, setup guide, and workflow documentation.
  - `requirements.txt`: Python dependencies. Update when introducing new runtime libraries.
  - `Dockerfile` / `docker-compose.yml`: Containerised deployment helpers.
- `js_tools/`: JavaScript helper projects invoked by the API (panorama splitter, Cobalt bridge). Run `npm install` within each subdirectory the first time you touch them.
- `tests/`: Pytest-based coverage of core endpoints and utilities.
- `scripts/`, `docs/`, `code_flow.md`, etc.: Operational helpers and supplemental documentation.

## Coding guidelines

- Target **Python 3.11+** and **FastAPI** idioms. Use type hints everywhere and prefer pydantic models for request/response shapes.
- Keep routers lean. Push heavy lifting into `services/` or utility modules so multiple endpoints can share behaviour.
- Maintain consistent logging via `app.utils.logger`. Log user-triggered actions at `info` and detailed traces at `debug`.
- When touching Jinja templates:
  - Extend `layouts/base.html` and populate `block` sections instead of duplicating layout markup.
  - Place shared UI into `templates/modules/` partials, then `include` or `import` them from pages.
  - Respect Bootstrap 5 class conventions and existing responsive grid structure.
- For CSS updates, scope rules beneath descriptive class names (e.g., `.studio-hero`) to avoid leaking styles. Keep custom properties near the top of `studio.css`.
- JavaScript belongs in `static/js/studio.js`. Use vanilla JS modules; do not introduce new global libraries without updating the bundling story.

## Testing & QA expectations

- Always run the automated suite before committing: `pytest` from the `tools-api/` directory.
- If you modify front-end behaviour, smoke-test the Studio pages (`/`, `/documents`, `/media`) under both desktop and mobile breakpoints. Capture regressions in CSS/JS.
- When adding dependencies or new workflows, update `README.md` (and any relevant docs in `docs/`) so humans and agents understand how to use them.

## Documentation expectations

- Mirror any new endpoint or tool behaviour in the README's “Service walkthrough” section.
- For UI additions, document the new modules/pages in the “Studio UI guide”.
- Keep instructions explicit—include example curl commands, environment variables, and prerequisites where applicable.

## Development workflow checklist

1. Create or update tests alongside code changes when practical.
2. Ensure `pytest` passes.
3. For back-end changes, verify OpenAPI docs (`/docs`) still load.
4. For front-end changes, test the Studio pages using the FastAPI dev server (`uvicorn app.main:app --reload`).
5. Keep commits scoped and descriptive; prefer conventional tone (e.g., `Add before/after promo presets`).

Following this playbook keeps the codebase approachable for future automations and humans alike. When in doubt, add clarifying comments or documentation.
