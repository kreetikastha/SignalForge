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
  `supporting_reports`, `has_image`, and `image_url` for the dashboard.
- `duplicate` is `false` for a report without a detected duplicate; duplicate
  reports point to their canonical report with `duplicate_of`.
- The dashboard's queue count represents submitted reports. Its open, urgent,
  sidebar, and loaded-incident counts represent unique duplicate groups.
- `received_at` values are returned in UTC with an explicit timezone offset.
- `urgency_score` is a 0–100 triage score based on severity and reported needs;
  it is not a probability. `confidence` is the model's self-reported estimate
  and is not calibrated; the UI omits confidence for mock/fallback analyses.
- `analysis_status: "mock"` means no completed live model result was recorded.
  Such assessments must be manually verified.
