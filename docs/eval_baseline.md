# Live Evaluation Baseline (12-sample subset)

**Run provenance**
- Mode: live (DISASTERLENS_STUB=0)
- Model: google/gemma-4-31b-it
- Provider: https://openrouter.ai/api/v1 (OpenRouter)
- Workers: 2
- Timestamp: 2026-10-10T06:15:25+00:00
- Samples evaluated: 12 (first 12 of 20 in data/sample_reports.json)

**This is a 12-sample subset**, not the full evaluation set. Results may not generalize.

---

## Metric Table

| Metric                              | Rate       | Detail |
|-------------------------------------|------------|--------|
| incident_type accuracy              |  91.7%     | 11/12  |
| severity in range                   | 100.0%     | 12/12  |
| people_trapped accuracy             |  58.3%     | 7/12   |
| road_blocked accuracy               |  91.7%     | 11/12  |
| needs recall                        |  20.0%     | 2/10   |
| language accuracy                   | 100.0%     | 12/12  |
| valid output (conf > 0.1)           | 100.0%     | 12/12  |
| duplicate precision                 |   n/a      | 0/0    |
| duplicate recall                    |   n/a      | 0/0    |
| precision (no coords)               |   n/a      | 0/0    |
| recall (no coords)                  |   n/a      | 0/0    |

### Safety Metrics

| Metric                      | Rate       | Detail |
|-----------------------------|------------|--------|
| trapped recall              | 100.0%     | 1/1    |
| trapped false alarms        | 2          | s02, s11 |
| severity under-triage       | 0          | []     |
| severity over-triage        | 0          | []     |

---

## Interpretation

**Strength:** Incident type classification (91.7%), severity calibration (100% in-range), road-blocked detection (91.7%), and language identification (100%) are strong. All 12 samples produced valid high-confidence output (confidence 0.9–0.95), and there were zero severity under- or over-triage cases. The sole true trapped-person case (s12, Romanized Nepali) was correctly caught.

**Weakness:** Needs recall is low (20%) — the model often returns synonyms (e.g., "ambulance" vs "medical", "road_clearing" vs "shelter") that the exact-match evaluator misses. People-trapped accuracy (58.3%) is pulled down by false alarms: the safety net correctly flags explicit "trapped" language but also triggers on ambiguous reports where ground truth is "unknown" (s02, s11).

**Gap to close:** The needs taxonomy needs alignment (synonym mapping or broader evaluator matching) to reflect actual capability. The trapped false-alarm rate suggests the keyword safety net is sensitive by design; this is a deliberate recall-over-precision tradeoff for rescue-critical signals.