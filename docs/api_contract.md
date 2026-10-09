# AI module contract

Backend imports only:

```python
from disasterlens_ai import analyze_report, find_duplicate, score_urgency
```

- `analyze_report(text: str, image: bytes | None = None) -> ReportAnalysis`
- `find_duplicate(new: ReportAnalysis, existing: list[IncidentRef]) -> IncidentMatch`
- `score_urgency(analysis: ReportAnalysis, duplicate_count: int = 1) -> int  # 0-100`

Models are defined in `ai/disasterlens_ai/schemas.py` (source of truth).
Set `DISASTERLENS_STUB=1` to get canned output with no API key.
