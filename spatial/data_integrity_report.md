# Phase 0 Data Integrity Report

Source inputs (read-only, never overwritten):
- `data/real/emergency_teams.json` (sha256 `b1df71b90c5706c1…`)
- `data/provenance/extraction_report.json`
- `config/scenario_matrix.yaml`

## 47 official teams (附件4)
- With numeric latitude & longitude: **45**
- Missing coordinate (no float found): **2** -> seq [3, 23]
- Lat/lon swap verified against source PDF: **2** -> seq [5, 24]
- Coordinate semantics: **organisation-location proxy**, not verified vehicle staging depot.
- Datum: **unknown** (no declaration in source); do NOT auto-apply GCJ-02/BD-09.
- Primary-candidate count is NOT 45: 2 records have no coordinate and 2 print
  latitude/longitude in reverse order relative to the source table header
  (verified on source-PDF pp. 42 and 45; see coordinate_swap_verification.md).
  These four are excluded because the datum is undeclared and the values are
  organisation-location proxies, not verified depots. Four further records
  fail road-access QA, leaving the 39-crew primary pool used in the route
  matrix (39 x 28 = 1092 pairs).

## 28 incident scenarios
- All `observation_provenance = synthetic`.
- Chainage source: 1 official case description (S07 K350+600),
  27 synthetic linear references (chainage = 100 + i*17 km).
- Route distribution (by normalised route_id): {'G3011': 7, 'G6': 5, 'G109': 6, 'G215': 5, 'S101': 5}
- `route_match_status` and `location_method` are placeholders until P1/P3.

## 6 synthetic traffic-control teams (RES-SYN-TC-00x)
- Hashed synthetic coordinates; **excluded from primary road-network analysis**.
- Enter only `co_located_proxy` / `corridor_balanced_proxy` sensitivity (P3).

## Constraint reminder
- No fabricated field observations. Unmatched / unresolved -> explicit status.
- Original input files are untouched; only `data/spatial/*.csv` (+ this report) created.
