# AI module contract

Backend imports only:

```python
from disasterlens_ai import analyze_report, find_duplicate, score_urgency
```

- `analyze_report(text: str, image: bytes | None = None) -> ReportAnalysis`
- `find_duplicate(new: ReportAnalysis, existing: list[IncidentRef]) -> IncidentMatch`
- `score_urgency(analysis: ReportAnalysis, duplicate_count: int = 1) -> int  # 0-100`

Models are defined in `ai/disasterlens_ai/schemas.py` (source of truth).
Set `DISASTERLENS_STUB=1` to get canned output with no API key. Set it to
`0` and restart the backend to use the configured live model for new reports;
previously saved reports are not automatically reanalyzed.
Install the backend API dependencies with `pip install -r backend/requirements.txt`;
the multipart parser is required for `/reports/upload`.

## Backend/frontend report contract

- `POST /reports` accepts JSON with `description`, `latitude`, and
  `longitude` for clients that do not upload an image.
- `POST /reports/upload` accepts multipart form fields `description`,
  `latitude`, `longitude`, and an optional `image` (JPEG, PNG, or WebP, up to
  5 MB). Image bytes are stored with the report and included in AI analysis.
- Reports with images return `has_image: true` and an `image_url`; retrieve the
  image with `GET /reports/{report_id}/image`.
- `GET /reports` and `GET /incidents` return report coordinates plus
  `location_text`, `confidence`, `urgency_score`, `duplicate`, `duplicate_of`,
  `duplicate_similarity`, `duplicate_reason`, `supporting_reports`,
  `people_affected`, `injuries_reported`, `vulnerable_groups`, `hazards`,
  `needs`, `flags`, `needs_review`, lifecycle metadata, `has_image`, and
  `image_url` for the dashboard.
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
- `injuries_reported` is null unless an injury count was stated. `hazards` is a
  list of explicitly reported immediate hazards; the model must not invent
  either field.

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
- Lifecycle values advance in order: `new` → `under_review` → `verified` →
  `response_in_progress` → `resolved`. Update with
  `PATCH /reports/{report_id}/status` and JSON fields `status` plus optional
  `changed_by`. Out-of-order changes return HTTP 409. Changes and actor
  attribution are recorded in `GET /reports/{report_id}/status-history`.
  Updating a report updates every report in its detected duplicate group so
  the incident has one consistent lifecycle.
  There is no authentication/user-account system yet; `changed_by` is an
  operator-supplied label, not verified identity.
