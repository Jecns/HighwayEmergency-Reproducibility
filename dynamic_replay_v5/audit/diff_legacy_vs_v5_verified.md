# 版本差异：legacy v4 → v5 verified

- 原文件：`scripts/run_dynamic_benchmark_v4.py`（**只读，未修改**，759 行）
- v1 修复版：`run_dynamic_benchmark_v4_fixed.py`（保留不动）
- 本版本：`run_dynamic_benchmark_v5_verified.py`（923 行）
- VARIANT = `fixed_v2_full_diagnostics`；精确替换 15 处，每处断言唯一匹配
- 五臂策略、触发器、资源过滤、目标函数、扰动分布与原文件一致；行为差异仅限需求集构造与诊断记录

## 三项新增诊断

1. `event_triggered_degradation`（deg_arm，对该臂自己的 carried plan） / `event_triggered_threshold` / `event_triggered_reopt`
2. 按臂 `<arm>_solve_attempted|_solve_completed|_solve_exception|_solve_runtime_s` + 事件级 `solve_attempted|solve_completed|solve_exception|solve_runtime_s|n_solve_*`；`SolverCallError` 携带诊断出栈，驱动落盘到 errors.jsonl
3. `n_demands_active|n_unique_task_ids|n_duplicate_task_ids|n_new_demands|assignment_count|mapping_count` + 按臂 `*_assignment_count|*_mapping_count`；每次事件后硬断言四等式，**允许的例外集合为空**

## 替换清单

1. `import csv`
2. `PERIOD = 2`
3. `default=ROOT / "experiments" / "outputs" / "E9_dynamic_replay_v4")`
4. `registry = EventRegistry(base)`
5. `unusable = registry.unusable_resource_ids()`
6. `row: dict[str, Any] = {`
7. `demands=list(keep_arm["problem"].demands) + new_demands,`
8. `demands=list(a["problem"].demands) + new_demands,`
9. `if arm == "keep":`
10. `new_complete = assignment_to_complete_mapping(new_problem, applied)`
11. `row[f"{arm}_fulfillment"] = round(applied_metrics["demand_fulfillment_rate"], `
12. `event_rows.append(row)`
13. `"strategy": strategy,`
14. `"experiment": "E9_dynamic_replay_v4",`
15. `"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),`

## Unified diff

```diff
--- scripts/run_dynamic_benchmark_v4.py (LEGACY, frozen)
+++ audit_demand_integrity/run_dynamic_benchmark_v5_verified.py
@@ -53,4 +53,5 @@
 import argparse
 import csv
+import hashlib
 import json
 import math
@@ -88,4 +89,88 @@
 #: fixed_period re-optimises on steps where (step % PERIOD == 0) after the first.
 PERIOD = 2
+
+# =========================================================================== #
+# VERIFIED VARIANT (2026-11-12) -- independent copy, legacy script untouched
+# =========================================================================== #
+VARIANT = "fixed_v2_full_diagnostics"
+
+
+class SolverCallError(RuntimeError):
+    """A solver invocation failed; carries its own diagnostics to the driver."""
+
+    def __init__(self, diagnostics):
+        super().__init__(diagnostics.get("exception", "solver call failed"))
+        self.diagnostics = dict(diagnostics)
+
+
+def install_network_import_shim():
+    """Allow the OSM arm to run on interpreters without geopandas.
+
+    ``src/road_network/__init__.py`` imports ``route_matcher`` (which imports
+    geopandas at module top level), but the NET-E9 replay uses ONLY
+    ``NetworkMatrixProvider`` -- a precomputed parquet lookup that never calls
+    geopandas.  Register an empty module object so that unrelated top-level
+    import succeeds.  Returns True when a shim was installed.
+
+    This is PROCESS-LOCAL and recorded in the experiment manifest.  It does
+    not modify any source file and does not alter any distance value.
+    """
+    import sys
+    import types
+    try:
+        import geopandas  # noqa: F401
+        return False
+    except ImportError:
+        sys.modules.setdefault("geopandas", types.ModuleType("geopandas"))
+        return True
+
+
+def canonical_active_demands(initial, added_cumulative):
+    """D_t = D_0 UNION D_added,t, keyed by task_id (first occurrence wins).
+
+    EventRegistry.extra_demands is append-only and demands_added() returns
+    the CUMULATIVE full set.  There is no demand revocation / expiry /
+    cancellation in the current implementation, so a plain union is correct.
+    """
+    out, seen = [], set()
+    for d in list(initial) + list(added_cumulative):
+        if d.task_id in seen:
+            continue
+        seen.add(d.task_id)
+        out.append(d)
+    return out
+
+
+def assert_demand_integrity(*, scenario_id, step, kind_name, payload,
+                            d0, added_cumulative, active,
+                            prev_active_ids, prev_cumulative):
+    """Six runtime assertions (A1-A6).  Any violation aborts the run."""
+    ids = [d.task_id for d in active]
+    assert len(d0) == len({d.task_id for d in d0}), (
+        f"A1 {scenario_id}/{step}: initial demand ids are not unique")
+    assert len(added_cumulative) >= prev_cumulative, (
+        f"A2 {scenario_id}/{step}: demands_added() is not cumulative")
+    expected = canonical_active_demands(d0, added_cumulative)
+    assert ids == [d.task_id for d in expected], (
+        f"A3 {scenario_id}/{step}: active demand set differs from canonical D_t")
+    assert len(ids) == len(set(ids)), (
+        f"A4 {scenario_id}/{step}: duplicate task ids in active demand set")
+    n_payload_new = len(payload.get("demands") or [])
+    delta_unique = len(set(ids)) - len(set(prev_active_ids))
+    delta_raw = len(active) - len(prev_active_ids)
+    if kind_name == "demand_surge":
+        assert delta_unique == n_payload_new and delta_raw == n_payload_new, (
+            f"A6 {scenario_id}/{step}: surge added "
+            f"({delta_unique} unique / {delta_raw} raw), expected "
+            f"{n_payload_new}")
+        assert len(added_cumulative) - prev_cumulative == n_payload_new, (
+            f"A6 {scenario_id}/{step}: registry increment mismatch")
+    else:
+        assert delta_unique == 0 and delta_raw == 0, (
+            f"A6 {scenario_id}/{step}: non-surge event added demands")
+        assert len(added_cumulative) == prev_cumulative, (
+            f"A6 {scenario_id}/{step}: registry grew on a non-surge event")
+# =========================================================================== #
+
 
 
@@ -318,4 +403,7 @@
     registry = EventRegistry(base)
     event_rows: list[dict[str, Any]] = []
+    # canonical active-demand-set state, independent of any arm's carried plan
+    prev_active_ids: list[str] = [d.task_id for d in init_problem.demands]
+    prev_cumulative = 0
 
     for step, (kind_name, payload) in enumerate(payloads, start=1):
@@ -327,5 +415,18 @@
 
         unusable = registry.unusable_resource_ids()
-        new_demands = list(init_problem.demands) + registry.demands_added()
+        # FIX: v4 appended the FULL current demand set to the FULL previous set
+        # at every event.  Maintain one canonical active set instead.
+        active_demands = canonical_active_demands(
+            init_problem.demands, registry.demands_added())
+        assert_demand_integrity(
+            scenario_id=scenario_id, step=step, kind_name=kind_name,
+            payload=payload, d0=init_problem.demands,
+            added_cumulative=registry.demands_added(),
+            active=active_demands, prev_active_ids=prev_active_ids,
+            prev_cumulative=prev_cumulative)
+        _new_ids_this_event = [d.task_id for d in active_demands
+                              if d.task_id not in set(prev_active_ids)]
+        prev_active_ids = [d.task_id for d in active_demands]
+        prev_cumulative = len(registry.demands_added())
 
         # Per-event re-dispatch configuration (dispatchers are built per arm
@@ -346,4 +447,16 @@
             "step": step,
         }
+        # --- group 1: event-triggered's OWN degradation -------------------- #
+        row["event_triggered_degradation"] = ""   # filled in that arm's branch
+        row["event_triggered_threshold"] = threshold
+        # --- group 3: demand integrity --------------------------------------- #
+        _aid = [d.task_id for d in active_demands]
+        row["n_demands_active"] = len(active_demands)
+        row["n_unique_task_ids"] = len(set(_aid))
+        row["n_duplicate_task_ids"] = len(active_demands) - len(set(_aid))
+        row["n_new_demands"] = len(_new_ids_this_event)
+        row["new_demand_ids_this_event"] = ";".join(_new_ids_this_event)
+        row["demand_ids_digest"] = hashlib.sha256(
+            "|".join(_aid).encode()).hexdigest()[:16]
 
         # Reference degradation for the descriptive trigger table: how much the
@@ -354,5 +467,5 @@
                        if r.resource_id not in unusable
                        and r.status is ResourceStatus.AVAILABLE],
-            demands=list(keep_arm["problem"].demands) + new_demands,
+            demands=list(active_demands),  # FIX: canonical active set
             event_latitude=keep_arm["problem"].event_latitude,
             event_longitude=keep_arm["problem"].event_longitude,
@@ -375,5 +488,5 @@
                            if r.resource_id not in unusable
                            and r.status is ResourceStatus.AVAILABLE],
-                demands=list(a["problem"].demands) + new_demands,
+                demands=list(active_demands),  # FIX: canonical active set
                 event_latitude=a["problem"].event_latitude,
                 event_longitude=a["problem"].event_longitude,
@@ -385,59 +498,57 @@
             # Dispatchers are built per arm inside the loop because each arm's
             # carried plan (and therefore its warm-start seed) differs.
+            # ---- group 2: one decision point, one recorded solver call ---- #
+            sd = {"attempted": False, "completed": False, "exception": "",
+                  "runtime_s": 0.0}
             if arm == "keep":
-                applied = list(carried)
-                rt = 0.0
-                reopt = False
+                should_solve, seed_assignments = False, None
             elif arm == "warm":
+                should_solve, seed_assignments = True, [carried]
+            elif arm == "cold":
+                should_solve, seed_assignments = True, None
+            elif arm == "fixed_period":
+                should_solve = (step % period == 0)
+                seed_assignments = None
+            else:  # event_triggered: degradation of THIS arm's carried plan
+                deg_arm = _degradation(
+                    a["metrics"], evaluate(new_problem, carried).to_dict())
+                row["event_triggered_degradation"] = round(deg_arm, 6)
+                row["event_triggered_threshold"] = threshold
+                should_solve = deg_arm > threshold
+                seed_assignments = [carried]
+
+            reopt = bool(should_solve)
+            rt = 0.0
+            if should_solve:
                 t0 = time.perf_counter()
-                applied = NSGA2Dispatcher(
-                    proposed=(strategy == "proposed_nsga2"),
-                    seed=cfg.seed, population_size=population, generations=generations,
-                    seed_assignments=[carried],
-                ).solve(new_problem)
-                rt = time.perf_counter() - t0
-                reopt = True
-            elif arm == "cold":
-                t0 = time.perf_counter()
-                applied = NSGA2Dispatcher(
-                    proposed=(strategy == "proposed_nsga2"),
-                    seed=cfg.seed, population_size=population, generations=generations,
-                    seed_assignments=None,
-                ).solve(new_problem)
-                rt = time.perf_counter() - t0
-                reopt = True
-            elif arm == "fixed_period":
-                if step % period == 0:
-                    t0 = time.perf_counter()
+                sd["attempted"] = True
+                try:
                     applied = NSGA2Dispatcher(
                         proposed=(strategy == "proposed_nsga2"),
-                        seed=cfg.seed, population_size=population, generations=generations,
-                        seed_assignments=None,
+                        seed=cfg.seed, population_size=population,
+                        generations=generations,
+                        seed_assignments=seed_assignments,
                     ).solve(new_problem)
-                    rt = time.perf_counter() - t0
-                    reopt = True
-                else:
-                    applied = list(carried)
-                    rt = 0.0
-                    reopt = False
-            else:  # event_triggered
-                deg_arm = _degradation(a["metrics"], evaluate(new_problem, carried).to_dict())
-                if deg_arm > threshold:
-                    t0 = time.perf_counter()
-                    applied = NSGA2Dispatcher(
-                        proposed=(strategy == "proposed_nsga2"),
-                        seed=cfg.seed, population_size=population, generations=generations,
-                        seed_assignments=[carried],
-                    ).solve(new_problem)
-                    rt = time.perf_counter() - t0
-                    reopt = True
-                else:
-                    applied = list(carried)
-                    rt = 0.0
-                    reopt = False
+                    sd["completed"] = True
+                except Exception as exc:  # keep diagnostics, then fail loudly
+                    sd["exception"] = f"{type(exc).__name__}: {exc}"
+                    raise SolverCallError(sd) from exc
+                finally:
+                    sd["runtime_s"] = time.perf_counter() - t0
+                    rt = sd["runtime_s"]
+            else:
+                applied = list(carried)
 
             applied_metrics = evaluate(new_problem, applied).to_dict()
             prev_complete = a["prev_complete"]
             new_complete = assignment_to_complete_mapping(new_problem, applied)
+            # group 3: no silent overwrite of duplicate task IDs is allowed
+            assert len(applied) == len(new_problem.demands), (
+                f"A4b {scenario_id}/{step}/{arm}: assignment length "
+                f"{len(applied)} != n_demands {len(new_problem.demands)}")
+            assert len(new_complete) == len(new_problem.demands), (
+                f"A4c {scenario_id}/{step}/{arm}: complete mapping has "
+                f"{len(new_complete)} keys for {len(new_problem.demands)} "
+                f"demands -> duplicate task ids were overwritten")
             stability = solution_stability(prev_complete, new_complete)
             # reassignment fraction vs the carried plan (this event)
@@ -454,4 +565,17 @@
             row[f"{arm}_runtime_s"] = round(rt, 6)
             row[f"{arm}_reopt"] = bool(reopt)
+            # --- group 2: per-arm solver bookkeeping ----------------------- #
+            row[f"{arm}_solve_attempted"] = sd["attempted"]
+            row[f"{arm}_solve_completed"] = sd["completed"]
+            row[f"{arm}_solve_exception"] = sd["exception"]
+            row[f"{arm}_solve_runtime_s"] = round(sd["runtime_s"], 6)
+            row[f"{arm}_solve_invocations"] = 1 if sd["attempted"] else 0
+            # --- group 3: per-arm demand / mapping integrity --------------- #
+            row[f"{arm}_n_demands"] = len(new_problem.demands)
+            row[f"{arm}_assignment_count"] = len(applied)
+            row[f"{arm}_mapping_count"] = len(new_complete)
+            row[f"{arm}_demand_ids_digest"] = hashlib.sha256(
+                "|".join(d.task_id for d in new_problem.demands).encode()
+            ).hexdigest()[:16]
             row[f"{arm}_reassign_frac"] = round(reassign, 6)
 
@@ -462,4 +586,34 @@
             a["prev_complete"] = new_complete
 
+        # --- event-level group 2 / 3 aggregates and hard assertion --------- #
+        row["assignment_count"] = row["warm_assignment_count"]
+        row["mapping_count"] = row["warm_mapping_count"]
+        row["n_solve_attempted"] = sum(
+            1 for a in ARMS if row[f"{a}_solve_attempted"])
+        row["n_solve_completed"] = sum(
+            1 for a in ARMS if row[f"{a}_solve_completed"])
+        row["n_solve_exceptions"] = sum(
+            1 for a in ARMS if row[f"{a}_solve_exception"])
+        row["solve_attempted"] = row["n_solve_attempted"] > 0
+        row["solve_completed"] = (
+            row["n_solve_completed"] == row["n_solve_attempted"])
+        row["solve_exception"] = ";".join(
+            row[f"{a}_solve_exception"] for a in ARMS
+            if row[f"{a}_solve_exception"])
+        row["solve_runtime_s"] = round(sum(
+            row[f"{a}_solve_runtime_s"] for a in ARMS), 6)
+        _digests = {row[f"{a}_demand_ids_digest"] for a in ARMS}
+        assert len(_digests) == 1, (
+            f"A5 {scenario_id}/{step}: five arms disagree on demand set")
+        assert (row["n_demands_active"] == row["n_unique_task_ids"]
+                == row["assignment_count"] == row["mapping_count"]), (
+            f"A7 {scenario_id}/{step}: N_demands={row['n_demands_active']}, "
+            f"N_unique={row['n_unique_task_ids']}, "
+            f"N_assignments={row['assignment_count']}, "
+            f"N_mapping={row['mapping_count']} -> allowed-exception set is EMPTY")
+        assert all(row[f"{a}_assignment_count"] == row["n_demands_active"]
+                   and row[f"{a}_mapping_count"] == row["n_demands_active"]
+                   for a in ARMS), (
+            f"A7 {scenario_id}/{step}: per-arm count mismatch")
         event_rows.append(row)
 
@@ -470,4 +624,5 @@
         "strategy": strategy,
         "distance_provider": provider,
+        "variant": VARIANT,
         "n_events": len(event_rows),
         "scarcity_ratio": ratio,
@@ -543,5 +698,5 @@
     parser.add_argument("--profiles", type=str, default=",".join(PROFILES))
     parser.add_argument("--out", type=Path,
-                        default=ROOT / "experiments" / "outputs" / "E9_dynamic_replay_v4")
+                        default=ROOT / "experiments" / "outputs" / "_v5_staging_unused")
     parser.add_argument("--shard-index", type=int, default=0)
     parser.add_argument("--shards", type=int, default=6)
@@ -680,8 +835,17 @@
 
     summary = {
-        "experiment": "E9_dynamic_replay_v4",
+        "experiment": "E9_dynamic_replay_v5_verified",
         "status": "complete" if all(_completed_keys(_shard_file(out, s))
                                     for s in range(args.shards)) else "partial",
         "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
+        "variant": VARIANT,
+        "demand_integrity": {
+            "rule": "D_t = D_0 UNION D_added,t, keyed by task_id",
+            "four_count_identity": "N_demands == N_unique == N_assignments == N_mapping",
+            "allowed_exceptions": [],
+            "six_runtime_assertions": True,
+            "solver_diagnostics": True,
+            "event_triggered_own_degradation": True,
+        },
         "config": {
             "replicates_per_scenario_profile": args.replicates,
```
