# Live Evaluation Baseline (full set, 66 samples)

**Run provenance**
- Mode: live (DISASTERLENS_STUB=0)
- Model: google/gemma-4-31b-it
- Provider: https://openrouter.ai/api/v1 (OpenRouter)
- Workers: 2
- Timestamp: 2026-10-10T06:50:11+00:00
- Samples evaluated: 66 (full data/sample_reports.json)

---

## Metric Table

| Metric                              | Rate       | Detail |
|-------------------------------------|------------|--------|
| incident_type accuracy              |  83.3%     | 55/66  |
| severity in range                   |  84.8%     | 56/66  |
| people_trapped accuracy             |  65.2%     | 43/66  |
| road_blocked accuracy               |  89.4%     | 59/66  |
| needs recall                        |  86.1%     | 31/36  |
| language accuracy                   |  90.9%     | 60/66  |
| valid output (conf > 0.1)           |  98.5%     | 65/66  |
| duplicate precision                 |  36.8%     | 14/38  |
| duplicate recall                    | 100.0%     | 14/14  |
| precision (no coords)               |   0.0%     | 0/8    |
| recall (no coords)                  |   0.0%     | 0/14   |

### Safety Metrics

| Metric                      | Rate       | Detail |
|-----------------------------|------------|--------|
| trapped recall              | 100.0%     | 10/10  |
| trapped false alarms        | 4          | s02, s11, s30, s36 |
| severity under-triage       | 8          | s25, s26, s53, s54, s57, s58, s59, s60 |
| severity over-triage        | 2          | s35, s36 |

---

## Known limitations of this evaluation

1. Duplicate precision is measured against current labels; several false-positive pairs involve reports at identical or near-identical coordinates describing the same place and event but assigned to different or no duplicate group (for example s25 and s55 share coordinates), so labels are under audit and precision is likely understated.
2. No-coordinates duplicate scores are 0 by design because the geo-near judge requires coordinates.
3. Causes of severity under-triage and trapped false alarms are not yet diagnosed.