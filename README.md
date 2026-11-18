# Reproducibility bundle

`per_seed_json_reports/` holds the raw per-seed JSON reports from which every aggregate statistic in the manuscript is recomputed.
`float_manifest.csv` binds every figure and table to its source file, image, label and citation count.
`dynamic_replay_v5/` holds the frozen E9 v5 dynamic-replay materials (two settings, run- and event-level records, statistical reports, generator scripts and the audit trail).

Software: CPython 3.10.8, NumPy 2.2.6, SciPy 1.15.3, NetworkX 3.4.2, IfcOpenShell 0.8.5.
Seeds: E1 {0..19}, E2/E3 {0..9}, case study 42.
Switches: GEOMETRY_MODE in {synthetic, none}, --traffic-teams in {0, 6}.

## Dynamic replay (E9 v5 verified rerun, 2026-11-13)

`dynamic_replay_v5/` holds the verified dynamic-replay materials that
produce every dynamic number in the paper (Sections 4.2/4.3, Tables 14-16,
Figs. 26-27). Two separately configured settings, never pooled:

- `E9_v5_legacy_full/` — Setting A: Haversine great-circle distances over
  synthetic coordinates, full official 47-crew pool. 2240 runs / 3820
  disturbance events.
- `NET_E9_v5_full/` — Setting B: OSM road-network shortest-path distances,
  screened 39-crew pool. 2240 runs / 3820 disturbance events.

Each directory contains `run_level_results.csv` (one row per run) and
`event_level_results.csv` (one row per disturbance event, nested in runs),
`manifest.json` (SHA-256 of the generator script and input provenance),
`statistical_report.json/.md` (run-level paired mean differences with
scenario-clustered percentile bootstrap 95% CI, 28 clusters / 20000
resamples), `summary.json` and `analysis.json`. `errors.jsonl` is empty
(0 errors). The intermediate `_shards/` files are omitted here for size;
they are archived in the V5 experiment-materials zip and in the project
source tree (`HighwayEmergency_A/experiments/outputs/<setting>/_shards/`).

`scripts/` contains the exact generators (frozen `run_verified_replay.py`,
sha256 4b559f3e...; `run_dynamic_benchmark_v5_verified.py` with the
demand-integrity fix `D_t = D0 u D_added,t` and three diagnostics +
four-equation hard assertions; the idempotent 56-shard driver
`run_full_all.py`; the aggregation `analyze_verified_replay.py`; the
finaliser `finalize_full_experiment.py`; the precheck gate). `audit/`
contains the demand-integrity audit trail (root cause of the superseded
v4 rerun, the v4->v5 comparison, the field-comparison note and the
20/20 provenance hash verification). Nothing in these directories was
regenerated for packaging; they are read-only copies of the frozen
2026-11-13 state (`FULL EXPERIMENT COMPLETE`).
