# Developer Workflow & Module Playbook

This guide explains how requests move through Tools API and how to extend the platform with new micro-tools. Use it as the single source of truth when shipping capabilities for n8n, Zapier, or any HTTP-driven orchestration layer.

---

## System Architecture

1. **Entry point – FastAPI router (`app/routers/`)**
   - Defines request/response contracts with Pydantic models.
   - Performs lightweight validation and hands off to services.
2. **Service layer (`app/services/`)**
   - Holds pure, testable functions that wrap external libraries or business logic.
   - Should be free of FastAPI-specific dependencies wherever possible.
3. **Runtime extensions (`app/runtime/`, `app/extensions/`)**
   - Background workers, queue adapters, and documentation helpers.
4. **Delivery surfaces**
   - REST endpoints exposed through FastAPI (`/docs` for OpenAPI UI).
   - Queue endpoints that enqueue jobs for RQ/Redis workers.

```
Client → Router → Service → (Queue/Worker)* → Response
```
`*` Optional for async workloads.

### Directory Map

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI application setup and router registration. |
| `app/routers/` | HTTP route definitions and request/response models. |
| `app/services/` | Core business logic and integrations with third-party libraries. |
| `app/runtime/` | CLI helpers, background workers, documentation printer. |
| `docs/service_catalog.yaml` | Source of truth for the human-readable API catalog printed on startup. |
| `tests/` | Pytest-based coverage for services and routers. |

---

## Adding a New Tool or Service

Follow these steps to introduce a new capability that feels native to Tools API and remains maintainable long term.

### 1. Scope the capability
- Document the problem statement, inputs, and expected outputs.
- Decide if the tool should run synchronously (HTTP request/response) or asynchronously (enqueue + worker).
- If the integration depends on an external library, note the minimum supported version.

### 2. Model the contract
- Create request/response models with Pydantic in your router module.
- Use descriptive field names; align with n8n conventions when possible.
- Provide default values or enums to make validation errors actionable.

### 3. Implement the service layer
- Add a new file in `app/services/` (e.g., `my_tool_service.py`).
- Keep functions stateless and deterministic so they are easy to test.
- Wrap third-party exceptions and raise meaningful Python exceptions for routers to catch.
- If the tool can run in the background, expose both async and sync helpers (`async def run_async(...)` and `def run_sync(...)`).

### 4. Wire up the router
- Create a router module in `app/routers/` (e.g., `my_tool.py`).
- Define endpoints with clear tags, descriptions, and response models.
- Import your router in `app/main.py` and register it with `app.include_router(...)`.
- For queue-backed endpoints, enqueue via `app.services.queue.enqueue` or the appropriate adapter.

### 5. Extend the documentation surfaces
- **OpenAPI** – Ensure docstrings, `response_model`, and `description` fields are populated so `/docs` renders useful schemas.
- **Service catalog** – Update `docs/service_catalog.yaml` so operators running the stack locally can see the new API in the startup banner and CLI output.
  - Use the following skeleton:

    ```yaml
    - name: "My Tool"
      summary: "One-line explanation of the capability."
      docs_url: "http://localhost:8000/docs#/tag-name"
      endpoints:
        - method: "POST"
          path: "/my-tool/run"
          description: "What the endpoint does."
          request:
            content_type: "application/json"
            model: "MyToolRequest"
            fields:
              payload: "string – Required input."
            example:
              payload: "example"
          response:
            content_type: "application/json"
            model: "MyToolResponse"
            fields:
              result: "string – Summary of the outcome."
    ```
- Run `python run_all.py` (or `uvicorn app.main:app --reload`) and confirm the startup banner lists the new endpoints.

### 6. Update dependencies & configuration
- Add new libraries to `requirements.txt` and pin versions if the upstream API changes often.
- Surface new environment variables in `app/config.py` with sensible defaults.
- Document setup steps in the project `README.md` if users must configure credentials.

### 7. Test thoroughly
- Add unit tests in `tests/` to cover the service and router behaviours.
- For async queues, add integration-style tests that assert enqueued jobs resolve correctly (see `tests/test_local_queue.py`).
- Run `pytest` locally and ensure the suite passes before opening a PR.

### 8. Operational readiness checklist
- Confirm logging uses `app.utils.logger` for consistent formatting.
- Provide retries or graceful error messaging for network-dependent code.
- If the tool produces files, document storage expectations (local disk vs. object store) in the README or service catalog notes.
- Ensure the API contract is backward compatible when modifying existing endpoints.

---

## Queue & Worker Guidance

- Local development uses the in-process queue provided by `app.extensions.local_queue_extension`.
- Production deployments should wire in Redis + RQ (`redis://` URLs). Update environment variables accordingly.
- Background workers live in `app/runtime/worker.py`; add handlers there if your tool produces jobs consumed outside FastAPI.

---

## Google Docs Rich Text Reference

- HTML and Markdown conversion helpers live in `app/services/parser_service.py`.
- The output format is a list of Google Docs `batchUpdate` requests. See `rich_text_guide.md` for styling capabilities.
- When extending formatting support, update both the service tests and the documentation catalog examples so downstream users know what to expect.

---

## Contributor Tips

- Keep pull requests focused—new tool + documentation + tests.
- Mention any follow-up tasks or limitations in the PR description so future maintainers can triage improvements quickly.
- If you touch shared infrastructure (queues, runtime, documentation printer), add regression tests to prevent accidental breakage.

