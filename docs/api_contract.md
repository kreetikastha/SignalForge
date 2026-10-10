# AI module contract

Backend imports only:

```python
from disasterlens_ai import (
    analyze_report, assess_legitimacy, find_duplicate, group_report, score_urgency,
)
```

- `analyze_report(text: str, image: bytes | None = None) -> ReportAnalysis`
- `group_report(text: str) -> GroupingAnalysis`
- `find_duplicate(new: ReportAnalysis | GroupingAnalysis, existing: list[IncidentRef]) -> IncidentMatch`
- `assess_legitimacy(text: str) -> LegitimacyAnalysis`
- `score_urgency(analysis: ReportAnalysis, duplicate_count: int = 1) -> int  # 0-100`

Models are defined in `ai/disasterlens_ai/schemas.py` (source of truth).
Set `DISASTERLENS_STUB=1` to get canned output with no API key. Set it to
`0` and restart the backend to use the configured live model for new reports;
previously saved reports are not automatically reanalyzed.
`LLM_MODEL` is used for full incident triage. `GROUPING_MODEL` and `LEGIT_MODEL`
select the pre-analysis grouping and credibility stages independently; each
defaults to `LLM_MODEL`. All three use the OpenAI-compatible endpoint in
`LLM_BASE_URL`. Use the hosted endpoint and model names in the Render service's
environment; `localhost:11434` refers only to Ollama on the developer's own
machine and is not reachable from Render.
Install the backend API dependencies with `pip install -r backend/requirements.txt`;
the multipart parser is required for `/reports/upload`.

## Backend/frontend report contract

- `POST /reports` accepts JSON with `description`, `latitude`, and
  `longitude` for clients that do not upload an image, plus optional opaque
  `reporter_id`.
- `POST /reports/upload` accepts multipart form fields `description`,
  `latitude`, `longitude`, optional `reporter_id`, and an optional `image`
  (JPEG, PNG, or WebP, up to 5 MB). Image bytes are stored with the report and
  included in AI analysis.
- Reports with images return `has_image: true` and an `image_url`; retrieve the
  image with `GET /reports/{report_id}/image`.
- `GET /reports` and `GET /incidents` return report coordinates plus
  `location_text`, `confidence`, `urgency_score`, `duplicate`, `duplicate_of`,
  `duplicate_similarity`, `duplicate_reason`, `supporting_reports`,
  `people_affected`, `people_trapped_count`, `injuries_reported`,
  `vulnerable_groups`, `hazards`,
  `needs`, `flags`, `needs_review`, `legitimacy_label`,
  `legitimacy_confidence`, `legitimacy_reason`, `incident_group_id`,
  `repeat_reporter`, `reporter_repeat_count`, lifecycle metadata, `has_image`,
  and `image_url` for the dashboard.
- `duplicate` is `false` for a report without a detected duplicate; duplicate
  reports point to their canonical report with `duplicate_of`. Similarity is a
  heuristic match score, not a probability. The dashboard groups matching
  reports while retaining each submitted report and its description.
- The dashboard's queue count represents submitted reports. Its open, urgent,
  sidebar, and loaded-incident counts represent unique duplicate groups.
- `received_at` values are returned in UTC with an explicit timezone offset.
- `urgency_score` is a 0–100 triage score based on severity and reported needs;
  it is not a probability. `confidence` is the model's self-reported estimate
  and is not calibrated; the UI omits confidence for mock/fallback analyses.
- `analysis_status: "mock"` means no completed live model result was recorded.
  Such assessments must be manually verified.
- `people_trapped_count` is null unless a trapped-person count was explicitly
  stated; it is not inferred from the separate total `people_affected`.
  `injuries_reported` is null unless an injury count was stated. `hazards` is a
  list of explicitly reported immediate hazards; the model must not invent
  either field.
- Reporter IDs are generated as random browser-local identifiers. The backend
  stores only their SHA-256 hash, never returns that hash, and marks a report
  as repeated when the same identifier has an earlier report in the preceding
  168 hours. This is a device/browser-level signal, not a verified person
  identity; it can be reset and must not be treated as evidence of fraud.

## Incident command features

- The dashboard filters the report queue and map by incident type, severity,
  and lifecycle status. Map markers open the matching incident details.
- `GET /situation` returns report and distinct-incident counts, critical/high
  totals, type/status counts, and nearby hotspots. Hotspots group distinct
  incidents whose representative coordinates are within 3 km; they are
  proximity summaries, not confirmed geographic boundaries.
- `POST /situation/briefing` asks the configured model to summarize up to 30
  distinct incidents. The briefing is based only on stored report evidence;
  unavailable model output returns HTTP 503 instead of a fabricated success.
- New submissions run the `GROUPING_MODEL` extraction and duplicate match
  before full triage, then still run full triage so each report can contribute
  additional hazards, trapped-person details, and needs to its group.
- Lifecycle values advance in order: `new` → `under_review` → `verified` →
  `response_in_progress` → `resolved`. Update with
  `PATCH /reports/{report_id}/status` and JSON fields `status` plus optional
  `changed_by`. Out-of-order changes return HTTP 409. Changes and actor
  attribution are recorded in `GET /reports/{report_id}/status-history`.
  Updating a report updates every report in its detected duplicate group so
  the incident has one consistent lifecycle.
  There is no authentication/user-account system yet; `changed_by` is an
  operator-supplied label, not verified identity.

## Credibility and repeat-reporter signals

- `LEGIT_MODEL` returns `genuine`, `uncertain`, `prank`, or `spam` with a short
  reason and model confidence. Results below `LEGIT_CONFIDENCE_THRESHOLD`
  (default `0.65`) are exposed as `uncertain`; provider or parsing failures
  are exposed as `unassessed` and logged. The model's confidence is
  self-reported and uncalibrated.
- Credibility is an advisory signal only. Reports are saved regardless of the
  result, and credibility/repeat flags never reduce triage urgency or change
  rescue-operation state. Operators should verify a suspicious assessment
  against evidence.
- The dashboard shows the credibility signal, repeat-reporter marker, and
  incident group alongside the report. Repeat counts use the configurable
  `REPEAT_REPORTER_WINDOW_HOURS` (default 168 hours).

## Local Gemma 4 evaluation

With Ollama running and `gemma4:e4b` pulled, run in PowerShell from `ai/`:

```powershell
$env:LLM_BASE_URL = "http://localhost:11434/v1"
$env:LLM_API_KEY = "ollama-local"
$env:LLM_MODEL = "gemma4:e4b"
$env:GROUPING_MODEL = "gemma4:e4b"
$env:LEGIT_MODEL = "gemma4:e4b"
$env:DISASTERLENS_STUB = "0"
..\backend\.venv\Scripts\python.exe .\scripts\eval.py --workers 2 --out .\e4b-results.json
```

The eval records each stage's model, scores pairwise duplicate precision/recall
using the pre-analysis grouping output, and scores the labeled genuine, prank,
and spam cases plus the repeat-reporter rule. Treat the small trust-label set
as a development check, not a validated moderation benchmark.

## Rescue operation features

- Rescue progress is independent from both `analysis_status` and the
  human-review `status`. New incidents start at `operation_status: "reported"`;
  AI completion never advances that state.
- The operation workflow is `reported` → `verified` → `dispatched` →
  `rescue_active` → `completed`. Operators can instead record terminal
  outcomes `false_alarm`, `no_rescue_required`, or `unable_to_access` where
  allowed by the transition rules. Dispatch and active rescue require an
  assigned team. Completing a rescue requires an explicitly confirmed positive
  `people_rescued` count.
- `GET /incidents/{incident_id}/operation` returns the canonical incident's
  `operation_status`, `assigned_team`, `dispatched_at`, `last_updated`,
  `rescue_outcome`, and `people_rescued` fields, incident evidence, and audit
  history.
- `PATCH /incidents/{incident_id}/operation` accepts `operation_status`,
  optional `assigned_team`, optional `people_rescued` (required for completion),
  and optional `changed_by`. Invalid transitions return HTTP 409; missing
  dispatch assignment or completion count returns HTTP 422. A terminal outcome
  cannot be overwritten.
- Duplicate reports share one operation state. Updates through any report ID
  apply to all reports in the duplicate group; the canonical incident holds
  the operation audit events.
- `GET /situation` includes `rescue_operations` summary counts, calculated
  from canonical incidents and explicit operator/report data. "People reported
  trapped" uses only explicit `people_trapped_count` values. Within a possible
  duplicate group it uses the largest stated count, rather than summing
  repeated reports of the same people; unquantified incidents are separately
  counted.
  Confirmed rescues count only explicitly recorded `people_rescued` values.
- The dashboard refreshes incident and operation data every 30 seconds. The
  map shows incident locations only; no responder GPS tracking is available.
- As with incident lifecycle attribution, `changed_by` is an operator-entered
  label and is not authenticated.
