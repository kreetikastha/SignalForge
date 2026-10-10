# DisasterLens — AI Emergency Intelligence 🚨

DisasterLens is an AI-powered emergency coordination platform that uses Gemma 4 to analyze disaster reports, extract critical information, prioritize urgent incidents, and visualize affected locations on an interactive map all through a unified dashboard designed to support faster, more informed disaster response.

## Why DisasterLens

**The problem:** In fast-moving emergencies, responders drown in unstructured reports — social media posts, phone calls, SMS — with no consistent way to extract location, severity, or trapped-person signals. Duplicate reports fragment situational awareness and delay triage.

**What already works:**

- Structured extraction: incident type, severity (1–5), location text, people trapped, road blocked, hazards, vulnerable groups, needs — returned as typed JSON
- Nepali / English support: Devanagari, Romanized Nepali, and English reports analyzed with language detection
- Duplicate grouping: heuristic Jaccard similarity on text + location, with optional LLM judge; incidents share one lifecycle
- Urgency scoring with safety net: 0–100 triage score from severity, casualties, vulnerable groups, trapped people, road blockages, corroborating reports; clause-aware keyword overrides for "trapped" in Nepali and English
- Lifecycle tracking: `new → under_review → verified → response_in_progress → resolved` with actor-attributed history; status updates apply to entire duplicate group
- Situation briefing: LLM-generated summary from up to 30 distinct incidents, evidence-only, fails safely (HTTP 503) if model unavailable

### Hackathon tracks

**Best Use of Gemma 4:**
- Gemma 4 drives the full analysis pipeline: classification, extraction, severity assessment, and the situation briefing
- Multilingual prompt handles Devanagari and Romanized Nepali without separate models

**Best Use of Open-Source AI for Real-World Impact:**
- Runs locally with a stub mode (`DISASTERLENS_STUB=1`) for development without API costs
- Open-weight model endpoint (NVIDIA-hosted Gemma 4) keeps inference accessible; backend is pure Python/FastAPI/SQLite

### Limitations

- No authentication or user accounts; `changed_by` is a free-text operator label, not verified identity
- Duplicate detection is heuristic (Jaccard on tokens + haversine distance), not embedding-based; LLM judge is optional and off by default
- Mock/fallback analyses are marked `analysis_status: "mock"` and must be manually verified before dispatch

## Run locally

Install the backend and AI module dependencies from the repository root:

```sh
pip install -r backend/requirements.txt
pip install ./ai
```

Start the API and website together on Windows PowerShell:

```powershell
cd backend
$env:DISASTERLENS_STUB = "1"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

On macOS or Linux:

```sh
cd backend
DISASTERLENS_STUB=1 .venv/bin/python -m uvicorn main:app --reload --port 8001
```

Open `http://127.0.0.1:8001`. The default database is local SQLite.

## Deploy a shared website and backend

The backend serves the website and API from the same URL. Reports are stored
in the database configured by `DATABASE_URL`, so all visitors use one shared
database instead of their own computer's `127.0.0.1`.

1. Create a hosted PostgreSQL database (for example, in Supabase) and copy its
   server-side connection string. Never put this credential in frontend code
   or commit it to Git.
2. In Render, create a Blueprint from this repository using `render.yaml`.
   Enter the PostgreSQL connection string as the `DATABASE_URL` secret.
3. Open and share the deployed Render URL. All visitors will then use the same
   backend and database.

`DISASTERLENS_STUB=1` allows report submission without an AI provider; its
analysis is marked as mock and must be verified manually. To enable live
analysis, set the provider variables described in `ai/.env.example` in the
Render service environment and set `DISASTERLENS_STUB=0`.

### Demo preflight

Run the staged-pipeline sanity check from `ai/`:
```sh
uv run python scripts/check_api.py
```
It times `group_report`, `analyze_report`, and `assess_legitimacy` twice (cold + warm).
- **PASS** — every stage succeeded and warm total <= 20s
- **WARN** — every stage succeeded but warm total > 20s (investigate latency)
- **FAIL** — any stage raised an exception

If `DISASTERLENS_STUB=1` is set, the script prints that stub mode is on and exits 0
without calling any API. Never prints API keys.

### Going live checklist

- [ ] In Render dashboard, set secrets: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (sync: false)
- [ ] Confirm `/health` returns `{"status": "healthy"}`
- [ ] Submit a test report; verify `analysis_status` is `"completed"` (not `"mock"`)