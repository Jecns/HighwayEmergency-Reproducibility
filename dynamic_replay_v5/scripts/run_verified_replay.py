# -*- coding: utf-8 -*-
"""
run_verified_replay.py
======================
Driver for the B-lite full re-run.  Two INDEPENDENT experiment configs,
resumable shards, per-shard persistence, full provenance manifest.

Usage
-----
  # pre-check: 28 scenarios x 4 profiles x 1 seed = 112 runs per config
  python run_verified_replay.py --config A --phase precheck --shards 4 --shard-index 0
  ... (shard-index 1..3, then --merge)

  # full: 28 x 4 x 20 = 2240 runs per config
  python run_verified_replay.py --config B --phase full --shards 28 --shard-index 0
  ... then --merge

Outputs (per config+phase, in a DEDICATED directory)
  _shards/shard_XX.jsonl    one full run record per line (resumable)
  errors.jsonl               failed runs, incl. SolverCallError diagnostics
  manifest.json              config / seeds / source SHA-256 / environment
  event_level_results.csv    (after --merge)
  run_level_results.csv      (after --merge)
  summary.json               (after --merge)
  analysis.json              (after --merge) descriptive, per-config ONLY

NEVER merges config A and config B.  The two differ in distance metric,
resource pool AND coordinate basis; they are independent experiments.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import run_dynamic_benchmark_v5_verified as V5   # noqa: E402

CFG_PATH = HERE / "experiment_configs.json"
ARMS = V5.ARMS

SHA_TARGETS = [
    "scripts/run_dynamic_benchmark_v4.py",
    "audit_demand_integrity/run_dynamic_benchmark_v4_fixed.py",
    "audit_demand_integrity/run_dynamic_benchmark_v5_verified.py",
    "audit_demand_integrity/build_verified_variant.py",
    "audit_demand_integrity/experiment_configs.json",
    "audit_demand_integrity/audit_demand_integrity.py",
    "audit_demand_integrity/run_verified_replay.py",
    "src/pipeline/event_registry.py",
    "src/dispatch/problem.py",
    "src/dispatch/redispatch.py",
    "src/dispatch/nsga2.py",
    "src/dispatch/objectives.py",
    "src/dispatch/constraints.py",
    "src/road_network/router.py",
    "scripts/run_experiments.py",
    "scripts/run_net_experiments.py",
    "config/scenario_matrix.yaml",
    "config/demand_rules.yaml",
    "data/spatial/resource_event_route_matrix.parquet",
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_cfg():
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def out_dir(phase: str, conf: dict) -> Path:
    return ROOT / f"{conf['out_root']}_{phase}"


def shard_path(out: Path, i: int) -> Path:
    return out / "_shards" / f"shard_{i:02d}.jsonl"


def completed_keys(path: Path):
    if not path.exists():
        return set()
    keys = set()
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            # A forced shutdown (e.g. power off) may leave a truncated last
            # line on disk.  Skip it: the run will be re-executed and appended
            # as a clean record on resume, so no data is lost and no key is
            # double-counted (we key on scenario/seed/profile).
            bad += 1
            continue
        keys.add((r["scenario_id"], r["seed"], r["profile"]))
    if bad:
        print(f"  [resume] skipped {bad} malformed line(s) in "
              f"{path.name} (will be re-run)", flush=True)
    return keys


def assign_scenarios(scenarios, shards, index):
    n = len(scenarios)
    base, rem = divmod(n, shards)
    chunks, i = [], 0
    for s in range(shards):
        size = base + (1 if s < rem else 0)
        chunks.append(scenarios[i:i + size])
        i += size
    return chunks[index % shards]


def build_manifest(args, cfg, conf, shim_installed):
    common = cfg["common"]
    phase = cfg["phases"][args.phase]
    hashes = {}
    for rel in SHA_TARGETS:
        p = ROOT / rel
        hashes[rel] = sha256(p) if p.exists() else "MISSING"
    deps = {}
    for m in ["numpy", "scipy", "pandas", "networkx", "yaml", "rdflib"]:
        try:
            mod = __import__(m)
            deps[m] = getattr(mod, "__version__", "unknown")
        except Exception:
            deps[m] = "MISSING"
    return {
        "manifest_version": "1.0",
        "created_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config_id": args.config,
        "config": conf,
        "phase": args.phase,
        "phase_spec": phase,
        "common": common,
        "critical_note": cfg["critical_note"],
        "frozen": cfg["frozen"],
        "go_nogo": cfg["go_nogo"],
        "variant": V5.VARIANT,
        "python": {"executable": sys.executable,
                   "version": platform.python_version(),
                   "platform": platform.platform()},
        "dependencies": deps,
        "network_import_shim_installed": bool(shim_installed),
        "network_import_shim_note": conf.get("runtime_note", ""),
        "argparse": {
            "seed_start": args.seed_start,
            "shards": args.shards,
            "replicates": phase["replicates"],
            "population": common["population"],
            "generations": common["generations"],
            "threshold": common["threshold"],
            "period": common["period"],
            "strategy": common["strategy"],
            "provider": conf["provider"],
        },
        "source_sha256": hashes,
        "source_sha256_of_manifest_inputs": sha256(CFG_PATH),
        "outputs": ["_shards/shard_*.jsonl", "errors.jsonl",
                    "event_level_results.csv", "run_level_results.csv",
                    "summary.json", "analysis.json"],
    }


def run_shard(args, cfg, conf, out, shim_installed):
    common = cfg["common"]
    phase = cfg["phases"][args.phase]
    seeds = [args.seed_start + i for i in range(phase["replicates"])]
    scenarios = V5.load_scenarios()
    mine = assign_scenarios(scenarios, args.shards, args.shard_index)
    sp = shard_path(out, args.shard_index)
    sp.parent.mkdir(parents=True, exist_ok=True)
    errp = out / "errors.jsonl"
    done = completed_keys(sp)
    jobs = [(s["scenario_id"], seed, profile)
            for s in mine for profile in common["profiles"] for seed in seeds]
    jobs = [j for j in jobs if j not in done]
    print(f"config={args.config} phase={args.phase} shard={args.shard_index}/"
          f"{args.shards} scenarios={len(mine)} jobs={len(jobs)} "
          f"(done={len(done)}) shim={shim_installed} -> {out}", flush=True)

    t0 = time.perf_counter()
    n_ok = n_fail = 0
    with sp.open("a", encoding="utf-8") as fh, \
            errp.open("a", encoding="utf-8") as efh:
        for k, (sid, seed, profile) in enumerate(jobs, start=1):
            try:
                rec = V5.run_one(
                    sid, seed, profile,
                    strategy=common["strategy"],
                    population=common["population"],
                    generations=common["generations"],
                    threshold=common["threshold"],
                    period=common["period"],
                    provider=conf["provider"],
                )
                rec["_config"] = args.config
                rec["_phase"] = args.phase
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n_ok += 1
            except Exception as exc:  # noqa: BLE001
                diag = getattr(exc, "diagnostics", None)
                efh.write(json.dumps({
                    "config": args.config, "phase": args.phase,
                    "scenario_id": sid, "seed": seed, "profile": profile,
                    "error": f"{type(exc).__name__}: {exc}",
                    "solver_diagnostics": diag,
                    "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, ensure_ascii=False) + "\n")
                efh.flush()
                n_fail += 1
                print(f"  FAIL {sid}/{seed}/{profile}: "
                      f"{type(exc).__name__}: {exc}", flush=True)
            if k % 10 == 0 or k == len(jobs):
                print(f"  progress {k}/{len(jobs)} ok={n_ok} fail={n_fail} "
                      f"elapsed={time.perf_counter()-t0:.1f}s", flush=True)
    print(f"shard done: ok={n_ok} fail={n_fail} "
          f"elapsed={time.perf_counter()-t0:.1f}s", flush=True)
    return 0 if n_fail == 0 else 2


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def merge(args, cfg, conf, out, shim_installed):
    runs = []
    for i in range(args.shards):
        p = shard_path(out, i)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                # Defensive: ignore a truncated trailing line left by a forced
                # shutdown.  By the time merge runs, such a line has already
                # been re-run and appended as a clean record during resume.
                print(f"  [merge] skip malformed line in {p.name}",
                      flush=True)
                continue
    if not runs:
        print("no runs to merge")
        return 1

    event_rows, run_rows = [], []
    for r in runs:
        rows = r.pop("events")
        event_rows.extend(rows)
        rec = {
            "config": args.config, "phase": args.phase,
            "scenario_id": r["scenario_id"], "seed": r["seed"],
            "profile": r["profile"], "n_events": r["n_events"],
            "scarcity_ratio": r["scarcity_ratio"],
            "n_demands": r["n_demands"], "n_resources": r["n_resources"],
            "init_fulfillment": r["init_fulfillment"],
            "init_distance_km": r["init_distance_km"],
            "variant": r.get("variant", V5.VARIANT),
        }
        for arm in ARMS:
            f = [x[f"{arm}_fulfillment"] for x in rows]
            d = [x[f"{arm}_distance_km"] for x in rows]
            u = [x[f"{arm}_unmet"] for x in rows]
            st = [x[f"{arm}_stability"] for x in rows]
            rt = [x[f"{arm}_runtime_s"] for x in rows]
            att = [1 if x[f"{arm}_solve_attempted"] else 0 for x in rows]
            comp = [1 if x[f"{arm}_solve_completed"] else 0 for x in rows]
            exc = [1 if x[f"{arm}_solve_exception"] else 0 for x in rows]
            rec[f"{arm}_fulfillment_mean"] = round(sum(f)/len(f), 6)
            rec[f"{arm}_distance_km_mean"] = round(sum(d)/len(d), 4)
            rec[f"{arm}_unmet_mean"] = round(sum(u)/len(u), 6)
            rec[f"{arm}_stability_mean"] = round(sum(st)/len(st), 6)
            rec[f"{arm}_runtime_s_total"] = round(sum(rt), 6)
            rec[f"{arm}_n_solve_attempted"] = sum(att)
            rec[f"{arm}_n_solve_completed"] = sum(comp)
            rec[f"{arm}_n_solve_exceptions"] = sum(exc)
            rec[f"{arm}_worst_fulfillment"] = round(min(f), 6)
        rec["n_triggered_keep"] = sum(1 for x in rows if x["triggered_keep"])
        rec["n_demand_anomalies"] = sum(
            1 for x in rows if not (x["n_demands_active"]
                                    == x["n_unique_task_ids"]
                                    == x["assignment_count"]
                                    == x["mapping_count"]))
        run_rows.append(rec)

    write_csv(out / "event_level_results.csv", event_rows)
    write_csv(out / "run_level_results.csv", run_rows)

    # ---- descriptive analysis (per config ONLY) -------------------------- #
    deg = [x["event_triggered_degradation"] for x in event_rows
           if x["event_triggered_degradation"] != ""]
    deg_sorted = sorted(deg)
    def q(p):
        return round(deg_sorted[min(len(deg_sorted)-1,
                                   int(p*(len(deg_sorted)-1)))], 6) \
            if deg_sorted else None
    tau_grid = {}
    for tau in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        tau_grid[str(tau)] = {
            "n_above": sum(1 for v in deg if v > tau),
            "share": round(sum(1 for v in deg if v > tau)/len(deg), 6)
            if deg else None,
        }
    ident_cols = [f"{a}_{m}" for a in ARMS for m in
                  ["fulfillment", "distance_km", "unmet", "stability", "reopt"]]
    n_identical = sum(
        1 for x in event_rows
        if all(abs(float(x[f"warm_{m}"]) - float(x[f"event_triggered_{m}"])) < 1e-9
               for m in ["fulfillment", "distance_km", "unmet", "stability"])
        and bool(x["warm_reopt"]) == bool(x["event_triggered_reopt"]))
    analysis = {
        "config": args.config, "phase": args.phase,
        "provider": conf["provider"],
        "independent_experiment": True,
        "never_pool_with_other_config": True,
        "note": ("Descriptive only. Events are NESTED inside runs and are NOT "
                 "independent samples. Inferential statistics live in "
                 "analyze_verified_replay.py (run-level paired, "
                 "scenario-clustered bootstrap, 28 clusters)."),
        "n_runs": len(run_rows), "n_event_rows": len(event_rows),
        "event_triggered_degradation": {
            "n": len(deg), "min": q(0), "p25": q(.25), "median": q(.5),
            "p75": q(.75), "p95": q(.95), "max": q(1),
            "distinct": len(set(deg)),
            "tau_grid_descriptive": tau_grid,
        },
        "warm_vs_event_triggered": {
            "identical_rows": n_identical,
            "total_rows": len(event_rows),
            "share": round(n_identical/len(event_rows), 6) if event_rows else 0,
            "fields_compared": ident_cols,
        },
        "solver_calls": {
            arm: {
                "attempted": sum(r[f"{arm}_n_solve_attempted"] for r in run_rows),
                "completed": sum(r[f"{arm}_n_solve_completed"] for r in run_rows),
                "exceptions": sum(r[f"{arm}_n_solve_exceptions"] for r in run_rows),
            } for arm in ARMS
        },
        "demand_integrity": {
            "runs_with_anomaly": sum(1 for r in run_rows if r["n_demand_anomalies"]),
            "four_count_identity_violations": sum(
                1 for x in event_rows
                if not (x["n_demands_active"] == x["n_unique_task_ids"]
                        == x["assignment_count"] == x["mapping_count"])),
            "max_n_demands_active": max(
                (x["n_demands_active"] for x in event_rows), default=0),
        },
    }
    (out / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "experiment": f"{conf['name']} / {args.phase}",
        "config_id": args.config,
        "variant": V5.VARIANT,
        "status": "complete",
        "provider": conf["provider"],
        "independent_experiment": True,
        "critical_note": cfg["critical_note"],
        "phase": args.phase,
        "n_runs": len(run_rows), "n_event_rows": len(event_rows),
        "n_scenarios": len({r["scenario_id"] for r in run_rows}),
        "seeds": sorted({r["seed"] for r in run_rows}),
        "scenario_ids": sorted({r["scenario_id"] for r in run_rows}),
        "profiles": sorted({r["profile"] for r in run_rows}),
        "arms": list(ARMS),
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "network_import_shim_installed": bool(shim_installed),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    mf = out / "manifest.json"
    man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() \
        else build_manifest(args, cfg, conf, shim_installed)
    man["merged_at_local"] = time.strftime("%Y-%m-%d %H:%M:%S")
    man["merge_result"] = {"n_runs": len(run_rows),
                           "n_event_rows": len(event_rows),
                           "outputs_sha256": {
                               f: sha256(out / f) for f in
                               ["event_level_results.csv",
                                "run_level_results.csv", "summary.json",
                                "analysis.json"]}}
    mf.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"merged config={args.config} phase={args.phase} "
          f"runs={len(run_rows)} events={len(event_rows)} -> {out}")
    print("  deg_arm distinct:", analysis["event_triggered_degradation"]["distinct"],
          " min/median/max:",
          analysis["event_triggered_degradation"]["min"],
          analysis["event_triggered_degradation"]["median"],
          analysis["event_triggered_degradation"]["max"])
    print("  warm == event_triggered rows:", n_identical, "/", len(event_rows))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", choices=("A", "B"), required=True)
    ap.add_argument("--phase", choices=("precheck", "full"), default="precheck")
    ap.add_argument("--seed-start", type=int, default=100)
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--shard-index", type=int, default=0)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg()
    conf = cfg["configs"][args.config]
    out = out_dir(args.phase, conf)
    out.mkdir(parents=True, exist_ok=True)

    # process-local shim BEFORE any road_network import happens.
    # Only the network config needs it; config A must record False so the
    # manifest states precisely which configuration used the shim.
    shim = (V5.install_network_import_shim()
            if conf["provider"] == "network" else False)

    mf = out / "manifest.json"
    if not mf.exists() or args.merge:
        mf.write_text(json.dumps(
            build_manifest(args, cfg, conf, shim),
            ensure_ascii=False, indent=2), encoding="utf-8")

    if args.status:
        for i in range(args.shards):
            print(f"  shard {i:02d}: {len(completed_keys(shard_path(out, i)))} runs")
        e = out / "errors.jsonl"
        print("  errors:", sum(1 for _ in e.open(encoding="utf-8")) if e.exists() else 0)
        return 0
    if args.merge:
        return merge(args, cfg, conf, out, shim)
    return run_shard(args, cfg, conf, out, shim)


if __name__ == "__main__":
    raise SystemExit(main())
