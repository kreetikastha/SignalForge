# Live Evaluation Baseline (12-sample subset)

**Run provenance**
- Mode: live (DISASTERLENS_STUB=0)
- Model: google/gemma-4-31b-it
- Provider: https://integrate.api.nvidia.com/v1
- Workers: 2
- Timestamp: 2026-10-10T05:55:31+00:00
- Samples evaluated: 12 (first 12 of 20 in data/sample_reports.json)

**This is a 12-sample subset**, not the full evaluation set. Results may not generalize.

---

## Metric Table

| Metric                              | Rate       | Detail |
|-------------------------------------|------------|--------|
| incident_type accuracy              |   0.0%     | 0/12   |
| severity in range                   |  91.7%     | 11/12  |
| people_trapped accuracy             |  50.0%     | 6/12   |
| road_blocked accuracy               |  25.0%     | 3/12   |
| needs recall                        |   0.0%     | 0/10   |
| language accuracy                   |  83.3%     | 10/12  |
| valid output (conf > 0.1)           |   0.0%     | 0/12   |
| duplicate precision                 |   n/a      | 0/0    |
| duplicate recall                    |   n/a      | 0/0    |
| precision (no coords)               |   n/a      | 0/0    |
| recall (no coords)                  |   n/a      | 0/0    |

### Safety Metrics

| Metric                      | Rate       | Detail |
|-----------------------------|------------|--------|
| trapped recall              | 100.0%     | 1/1    |
| trapped false alarms        | 1          | s02    |
| severity under-triage       | 0          | []     |
| severity over-triage        | 1          | s06    |

---

## Interpretation

**Strength:** Severity estimation is surprisingly strong at 91.7% in-range, and the single true trapped case (s12) was correctly caught with 100% trapped recall. The model never under-triaged severity.

**Weakness:** The model collapsed every incident type to "other" (0% accuracy), producing confidence clamped at 0.1 — suggesting it may be refusing or failing to follow the structured output schema. Consequently, road_blocked (25%), needs recall (0%), and valid output rate (0%) are all near-zero.

**Critical gap:** The 100% trapped recall comes with a false alarm (s02 flagged trapped when ground truth was unknown), and Romanized Nepali samples (s11, s12) were misclassified as English. The prompt/schema contract appears not to be honored by this model endpoint; further prompt engineering or a different provider/model is needed before live deployment.