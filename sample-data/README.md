# sample-data

Fictional manufacturing plant, fully synthetic. No real company data.

| File | Rows | Notes |
|---|---|---|
| `csv/production_lines.csv` | 6 | `L01`–`L06` across Assembly, Machining, Packaging |
| `csv/equipment.csv` | 24 | 4 units per line |
| `csv/downtime_reasons.csv` | 7 | `IsPlanned` separates changeovers/maintenance from failures |
| `csv/production_records.csv` | 12,960 | one row per line per UTC hour, 2026-08-13 → 2026-11-10 |
| `csv/downtime_events.csv` | 1,339 | minute-aligned, never overlapping per line |
| `csv/quality_incidents.csv` | 130 | |
| `csv/maintenance_events.csv` | 471 | linked to the downtime event they resolved |
| `golden/expected_metrics.json` | 29 cases | expected tool outputs from the oracle |

```bash
python sample-data/generate.py                      # regenerate CSVs (byte-for-byte identical)
python sample-data/reference_metrics.py --check     # verify golden values
python -m unittest discover -s tests/data -t .      # run tests
```

- `generate.py` — deterministic generator (stdlib only, fixed seed, pinned end date `2026-11-11T00:00:00Z`).
- `reference_metrics.py` — independent implementation of
  [`docs/architecture/metric-definitions.md`](../docs/architecture/metric-definitions.md),
  used to check the API (parity tests) and the agent (numeric accuracy evaluation).

Seeded scenarios: recurring spindle overtemperature (E104) on Line 04 in the last 21 days;
a 6-hour electrical outage on Line 02 on 2026-11-10; elevated seal-integrity defects on Line 03
in the last 30 days.
