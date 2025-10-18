# Tools API

Tools API is a FastAPI application that bundles document conversion, media helpers, and JavaScript-backed utilities behind a single REST API. It was built so non-developers can upload files or paste URLs, while automations and AI agents receive clean, well-documented responses.

## What you get out of the box
- **Rich text parsers** that turn HTML or Markdown into Google Docs `batchUpdate` requests.
- **Google Docs + DOCX extraction** for pulling plain text, links, and metadata out of exported files.
- **Image tooling** for halation glows and before/after promos with optional MP4 output.
- **JavaScript bridges** to the bundled panorama splitter and Cobalt-powered media downloads.
- **yt-dlp orchestration** with progress streaming, persistent download links, and subtitle helpers.
- **Studio web UI** at `/` for running every tool without writing curl commands—now root-path aware so it works when the API is mounted behind `/tools` or similar prefixes.

## Prerequisites
| Requirement | Why it is needed |
| --- | --- |
| Python 3.11+ | Runs the FastAPI application and worker. |
| pip | Installs Python dependencies from `requirements.txt`. |
| Node.js 18+ & npm | Required the first time you call the JavaScript panorama splitter or Cobalt bridge (Tools API auto-runs `npm install`). |
| Optional: `imageio-ffmpeg` or system FFmpeg | Enables MP4 output for the before/after animation tool. |
| Optional: Redis | Needed only if you wire Tools API into an external Redis-backed queue. The bundled `run_all.py` script uses the in-process queue by default. |

## Quick start (no prior backend experience required)
1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-org>/jarvis-Tools.git
   cd jarvis-Tools/tools-api
   ```
2. **Create a virtual environment** (keeps packages isolated)
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. **(Optional) Prepare JavaScript helpers** – Install Node.js 18+ and npm. Tools API will run `npm install` the first time the panorama splitter or Cobalt bridge is used, but you can also prime it manually:
   ```bash
   cd js_tools/panosplitter
   npm install
   cd ../..
   ```
5. **Run the API**
   - Fastest way: `uvicorn app.main:app --reload`
   - One-command bundle (API + local worker + documentation banner): `python run_all.py`
6. **Open the Studio** – Visit `http://localhost:8000/` for the drag-and-drop dashboard or `http://localhost:8000/docs` for Swagger UI.

> **Tip:** The Studio now reads the OpenAPI URL to determine the correct base path, so the buttons keep working even when Tools API sits behind a reverse proxy at `/tools` or similar.

## Studio UI guide
The Studio has been rebuilt as a multi-page experience powered by Bootstrap 5. Each page assembles Jinja partials from `app/templates/modules`, so you can reuse or swap individual tool panels without touching the navigation chrome.

### Navigation
- **Top navbar:** A sticky Bootstrap navbar provides quick links to the Overview, Document, and Media workspaces. The API docs button and FastAPI version badge remain visible at every breakpoint.
- **Responsive layout:** Cards and panels wrap automatically on small screens, while forms and result panes stay side-by-side on desktops.
- **Modular templates:** Every toolkit lives in its own partial (for example `parser.html`, `docx.html`, `media.html`). Include the partials you need when composing new pages.

### Overview page
- **Hero summary:** Highlights the docs URLs, OpenAPI path, and Cobalt gateway status at a glance.
- **Power checklist:** Lists the biggest wins for using the Studio with visual checkmarks.
- **Live endpoint catalogue:** Still backed by the OpenAPI spec—filter by name or tag before diving into Swagger.

### Document workflows page
- **Parser module:** HTML and Markdown forms (plus synchronous Docs builders) render in a two-column layout with response history on the right.
- **DOCX module:** Drag in a `.docx` file and review cleaned text plus metadata in the adjacent result pane.

### Media workflows page
- **Image tools:** Apply halation glows or build before/after promos with slider controls.
- **JavaScript tools:** Panosplit panoramas or orchestrate the Cobalt downloader with presets, advanced overrides, and shortcut buttons.
- **Media toolkit:** Manage FFmpeg conversions and yt-dlp downloads, complete with modal-based quality selection and streaming progress indicators.

Each module remembers the most recent response, making it easy to compare payloads after tweaking options. Result columns scroll independently so data never overflows.

## Service walkthrough
Each section below includes an example call you can paste into a terminal. Replace placeholder values as needed.

### 1. Rich text parsers
Convert HTML or Markdown to Google Docs operations.
```bash
curl -X POST http://localhost:8000/parse/html \
  -H "Content-Type: application/json" \
  -d '{"html": "<h1>Launch Plan</h1><p>Automate everything.</p>"}'
```
- Use `/parse/docs/html` or `/parse/docs/markdown` for synchronous conversions that skip the queue.
- Offload heavy conversions with `/parse/queue/html` (or `/parse/queue/markdown`) and poll `/parse/job/<job_id>` until `status` becomes `finished`.
- Feed the returned `requests` array directly into the Google Docs `documents.batchUpdate` API.

### 2. Google Docs JSON parser
Extract plain text, hyperlinks, and image references from a Docs JSON export.
```bash
curl -X POST http://localhost:8000/parse/gdocs/json \
  -H "Content-Type: application/json" \
  -d '{"content": {/* paste the Google Docs JSON export here */}}'
```
To upload a `.json` file you exported from Google Docs:
```bash
curl -X POST http://localhost:8000/parse/gdocs/file \
  -F "file=@MyDoc.json"
```

### 3. DOCX toolkit
Stream a DOCX file and receive clean text plus metadata.
```bash
curl -X POST http://localhost:8000/docx/parse \
  -H "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document" \
  --data-binary @proposal.docx
```

### 4. Image effects
Generate halation glows or before/after promos.
```bash
# Halations glow (JSON response with base64 JPEG)
curl -X POST "http://localhost:8000/image-tools/halations?response_format=json" \
  -F "image=@portrait.jpg"

# Before/after animation (binary MP4 download)
curl -X POST "http://localhost:8000/image-tools/before-after?response_format=binary" \
  -F "before_image=@old.png" \
  -F "after_image=@new.png" \
  -o promo.mp4
```
If FFmpeg (via `imageio-ffmpeg`) is installed, the before/after tool returns MP4; otherwise it falls back to GIF.

### 5. JavaScript tool bridge
Split panoramas or proxy Cobalt downloads through Python-friendly endpoints.
```bash
# Panorama splitter (zip archive response)
curl -X POST "http://localhost:8000/js-tools/panosplitter" \
  -F "image=@wide-shot.jpg" \
  -F "high_res=false" \
  -o panosplitter.zip

# Cobalt proxy (JSON response)
curl -X POST http://localhost:8000/js-tools/cobalt \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```
Cobalt shortcuts (`/js-tools/cobalt/shortcuts/{slug}`) let you trigger presets such as `youtube-audio` or `metadata-only` with the same request body. Configure the gateway with:
```bash
export COBALT_API_BASE_URL="https://your-cobalt-instance.example"
# Optional auth
export COBALT_API_AUTH_SCHEME="Api-Key"
export COBALT_API_AUTH_TOKEN="your-token"
```
If the environment variables are missing, Tools API falls back to the public `https://co.wuk.sh/api/json` endpoint and/or the local yt-dlp helper.

### 6. Media toolkit (yt-dlp)
Fetch metadata, stream downloads, and monitor progress.
```bash
# Request metadata and available formats
curl -X POST http://localhost:8000/media/yt-dlp \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "response_format": "json"
      }'

# Trigger a download with progress streaming
JOB_ID="download-$(date +%s)"
curl -X POST http://localhost:8000/media/yt-dlp \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "response_format": "binary",
        "job_id": "'"$JOB_ID"'",
        "mode": "video"
      }' \
  -o video.bin

# Watch live progress events
curl -N http://localhost:8000/media/yt-dlp/progress/$JOB_ID
```
When `response_format` is `binary`, the response headers include:
- `Content-Disposition` – suggested filename.
- `X-YtDlp-Metadata` – base64 JSON that mirrors the metadata payload.

The JSON response also contains a `download` descriptor. You can re-fetch the stored asset later:
```bash
curl -o saved.mp4 http://localhost:8000/media/yt-dlp/files/<file_id>
```

## Configuration reference
Most behaviour is driven by environment variables. The most common ones are listed below.

| Variable | Purpose | Default |
| --- | --- | --- |
| `TOOLS_API_HOST` / `TOOLS_API_PORT` | Host and port used by `python run_all.py`. | `127.0.0.1` / `8000` |
| `COBALT_API_BASE_URL` | Remote Cobalt instance URL. Set to `disabled` to turn the integration off. | Public fallback (`https://co.wuk.sh/api/json`) |
| `COBALT_API_AUTH_SCHEME` / `COBALT_API_AUTH_TOKEN` | Optional auth forwarded to your Cobalt deployment. | unset |
| `COBALT_API_TIMEOUT` | Seconds before Cobalt requests time out. | `90` |
| `MEDIA_DOWNLOAD_DIR` | Directory for yt-dlp download cache. | `app/downloads/` |

A full natural-language catalogue of every endpoint lives in [`docs/service_catalog.yaml`](docs/service_catalog.yaml). The documentation printer (`python run_all.py`) and CLI both read from this file, so keep it updated when you add new services.

## Testing and linting
```bash
pytest
```
All tests pass without external services; network calls are mocked.

## Troubleshooting
- **Studio buttons submit but nothing happens** – ensure Node.js is installed for JavaScript-backed tools and refresh. The Studio now auto-detects the API base path, so reverse proxies no longer break form submissions.
- **Panorama splitter errors about Node/npm** – confirm `node` and `npm` are on your `PATH`, then re-run the request. The API installs dependencies automatically the first time.
- **Before/after returns GIF instead of MP4** – install `imageio-ffmpeg` (`pip install imageio-ffmpeg`) or make sure FFmpeg is available on the system.
- **yt-dlp download fails** – check the server logs for the detailed error message and ensure the URL is accessible from the host machine.

## Want to extend Tools API?
Read [`code_flow.md`](code_flow.md) for the architectural overview, then update:
1. `app/services/` – add your pure Python logic.
2. `app/routers/` – expose HTTP endpoints with clear request/response models.
3. `docs/service_catalog.yaml` – document the workflow so operators know how to use it.
4. `tests/` – add or update tests and run `pytest`.

Happy building! Tools API is designed to keep content workflows approachable for both automation engineers and non-developers.
