# DisasterLens — AI Emergency Intelligence 🚨

DisasterLens is an AI-powered emergency coordination platform that uses Gemma 4 to analyze disaster reports, extract critical information, prioritize urgent incidents, and visualize affected locations on an interactive map all through a unified dashboard designed to support faster, more informed disaster response.

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

### Going live checklist

- [ ] In Render dashboard, set secrets: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (sync: false)
- [ ] Confirm `/health` returns `{"status": "healthy"}`
- [ ] Submit a test report; verify `analysis_status` is `"completed"` (not `"mock"`)