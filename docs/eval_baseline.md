# Live Evaluation Baseline (12-sample subset)

**Run provenance**
- Mode: live (DISASTERLENS_STUB=0)
- Model: google/gemma-4-31b-it
- Provider: https://openrouter.ai/api/v1 (OpenRouter)
- Workers: 2
- Timestamp: 2026-10-10T06:15:25+00:00
- Samples evaluated: 12 (first 12 of 66 in data/sample_reports.json)

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

Incident type classification (91.7%), severity calibration (100% in-range), road-blocked detection (91.7%), and language identification (100%) are strong on this subset. All 12 samples produced valid high-confidence output (confidence 0.9–0.95), with zero severity under- or over-triage cases.

Trapped recall is based on a single positive sample (s12), so it is not informative. Duplicate metrics are n/a because this subset contains no duplicate pairs. Needs recall is 20% (2/10), and trapped false alarms occur on s02 and s11; the causes of these gaps have not yet been diagnosed.