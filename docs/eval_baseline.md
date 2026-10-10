# Live Evaluation Baseline (full set, 66 samples)

**Run provenance**
- Mode: live (DISASTERLENS_STUB=0)
- Model: google/gemma-4-31b-it
- Provider: https://openrouter.ai/api/v1 (OpenRouter)
- Workers: 2
- Timestamp: 2026-10-10T06:32:25+00:00
- Samples evaluated: 66 (full data/sample_reports.json)

---

## Metric Table

| Metric                              | Rate       | Detail |
|-------------------------------------|------------|--------|
| incident_type accuracy              |  81.8%     | 54/66  |
| severity in range                   |  84.8%     | 56/66  |
| people_trapped accuracy             |  66.7%     | 44/66  |
| road_blocked accuracy               |  89.4%     | 59/66  |
| needs recall                        |  83.3%     | 30/36  |
| language accuracy                   |  90.9%     | 60/66  |
| valid output (conf > 0.1)           | 100.0%     | 66/66  |
| duplicate precision                 |   0.0%     | 0/6    |
| duplicate recall                    |   0.0%     | 0/14   |
| precision (no coords)               |   n/a      | 0/0    |
| recall (no coords)                  |   0.0%     | 0/14   |

### Safety Metrics

| Metric                      | Rate       | Detail |
|-----------------------------|------------|--------|
| trapped recall              | 100.0%     | 10/10  |
| trapped false alarms        | 5          | s02, s11, s23, s30, s36 |
| severity under-triage       | 8          | s25, s26, s53, s54, s57, s58, s59, s60 |
| severity over-triage        | 2          | s35, s36 |

---

## Interpretation

On the full 66-sample set, incident type accuracy is 81.8%, severity in-range is 84.8%, road-blocked accuracy is 89.4%, and needs recall is 83.3%. All 66 samples produced valid high-confidence output. Trapped recall is 100% (10/10), with 5 trapped false alarms. There are 8 severity under-triage cases and 2 severity over-triage cases. Duplicate detection found 0 true positives out of 14 expected pairs and 6 false positives.

The previous live3 run (12-sample subset, before the needs-vocabulary prompt change) showed higher incident type accuracy (91.7%), perfect severity in-range (100%), and lower needs recall (20%). The two runs are not directly comparable beyond the shared 12 samples because the prompt and normalization logic changed and the sample sizes differ substantially.