"""E9 v4 - independent-strategy-trajectory dynamic re-dispatch replay.

Why v4 (audit of v3, 2026-11-05)
-------------------------------
``run_dynamic_benchmark_v3.py`` compared three plans (keep / warm / cold) at
*each* disturbance event, but only the **warm** arm was carried forward as the
applied state; keep and cold were evaluated as point counter-factuals against
the warm-driven state. That makes the comparison a *per-event counter-factual*
rather than a fair contest between complete strategies, and the
``triggered`` flag was computed but never used to gate anything.

v4 changes the **experimental unit to a full strategy trajectory**: each arm
maintains and carries forward *its own* plan state across the disturbance
sequence, so:

* ``keep``           - never re-optimises; the carried plan is applied as-is;
* ``warm``           - warm-started re-optimisation every event (system policy);
* ``cold``           - cold-started re-optimisation every event;
* ``fixed_period``   - re-optimises every ``period`` events, keeps otherwise;
* ``event_triggered`` - re-optimises **only when** the carried plan's
                        degradation exceeds the threshold (uses ``triggered``).

All five arms see the *same* exogenous disturbance sequence (same resource
failures / road closures / demand surges), so they are compared pairwise *within*
the same run - the run (scenario x seed x profile) remains the statistical unit
and events stay nested inside it. Each arm also reports trajectory-level
evidence the revised roadmap asks for: number of re-optimisations, total
decision latency, cumulative unmet demand, worst-in-trajectory fulfilment, and
the share of events that required a reassignment.

Provenance is unchanged and explicit: event sequences are synthetic replays,
road-closure impacts are supplied as declared inputs because no road-network
topology is used in this replay (it runs on the default haversine geometry to
keep the comparison basis identical to the static benchmarks), and coordinates
keep their ``synthetic`` tag. Nothing here is an observed field incident.

Resumable sharding
------------------
The driver splits the 28 scenarios into ``--shards`` contiguous chunks and each
chunk writes its own JSONL of completed runs. A re-invocation of the same
``--shard-index`` skips any (scenario, seed, profile) already present, so an
interrupted full run can be resumed. ``--merge`` concatenates the shards into
the canonical ``event_level_results.csv`` / ``run_level_results.csv`` /
``summary.json`` consumed by ``analyze_dynamic_benchmark.py`` (extended for 5
arms + trajectory metrics).

Example:
  PYTHONPATH=. python scripts/run_dynamic_benchmark_v4.py --shard-index 0 --shards 6
  PYTHONPATH=. python scripts/run_dynamic_benchmark_v4.py --merge
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

PROFILES = ("resource_failure", "road_closure", "demand_surge", "compound")

#: Event kinds that make up the compound profile, in replay order.
_COMPOUND_ORDER = (
    "resource_failure",
    "road_closure",
    "demand_surge",
    "resource_failure",
)

#: Profile step name -> the dynamic event kind it registers.
_KIND_BY_PROFILE = {
    "resource_failure": "ResourceFailureEvent",
    "road_closure": "RoadClosureEvent",
    "demand_surge": "NewIncidentEvent",
}

#: The five comparison arms.
ARMS = ("keep", "warm", "cold", "fixed_period", "event_triggered")

#: fixed_period re-optimises on steps where (step % PERIOD == 0) after the first.
PERIOD = 2

# =========================================================================== #
# VERIFIED VARIANT (2026-11-12) -- independent copy, legacy script untouched
# =========================================================================== #
VARIANT = "fixed_v2_full_diagnostics"


class SolverCallError(RuntimeError):
    """A solver invocation failed; carries its own diagnostics to the driver."""

    def __init__(self, diagnostics):
        super().__init__(diagnostics.get("exception", "solver call failed"))
        self.diagnostics = dict(diagnostics)


def install_network_import_shim():
    """Allow the OSM arm to run on interpreters without geopandas.

    ``src/road_network/__init__.py`` imports ``route_matcher`` (which imports
    geopandas at module top level), but the NET-E9 replay uses ONLY
    ``NetworkMatrixProvider`` -- a precomputed parquet lookup that never calls
    geopandas.  Register an empty module object so that unrelated top-level
    import succeeds.  Returns True when a shim was installed.

    This is PROCESS-LOCAL and recorded in the experiment manifest.  It does
    not modify any source file and does not alter any distance value.
    """
    import sys
    import types
    try:
        import geopandas  # noqa: F401
        return False
    except ImportError:
        sys.modules.setdefault("geopandas", types.ModuleType("geopandas"))
        return True


def canonical_active_demands(initial, added_cumulative):
    """D_t = D_0 UNION D_added,t, keyed by task_id (first occurrence wins).

    EventRegistry.extra_demands is append-only and demands_added() returns
    the CUMULATIVE full set.  There is no demand revocation / expiry /
    cancellation in the current implementation, so a plain union is correct.
    """
    out, seen = [], set()
    for d in list(initial) + list(added_cumulative):
        if d.task_id in seen:
            continue
        seen.add(d.task_id)
        out.append(d)
    return out


def assert_demand_integrity(*, scenario_id, step, kind_name, payload,
                            d0, added_cumulative, active,
                            prev_active_ids, prev_cumulative):
    """Six runtime assertions (A1-A6).  Any violation aborts the run."""
    ids = [d.task_id for d in active]
    assert len(d0) == len({d.task_id for d in d0}), (
        f"A1 {scenario_id}/{step}: initial demand ids are not unique")
    assert len(added_cumulative) >= prev_cumulative, (
        f"A2 {scenario_id}/{step}: demands_added() is not cumulative")
    expected = canonical_active_demands(d0, added_cumulative)
    assert ids == [d.task_id for d in expected], (
        f"A3 {scenario_id}/{step}: active demand set differs from canonical D_t")
    assert len(ids) == len(set(ids)), (
        f"A4 {scenario_id}/{step}: duplicate task ids in active demand set")
    n_payload_new = len(payload.get("demands") or [])
    delta_unique = len(set(ids)) - len(set(prev_active_ids))
    delta_raw = len(active) - len(prev_active_ids)
    if kind_name == "demand_surge":
        assert delta_unique == n_payload_new and delta_raw == n_payload_new, (
            f"A6 {scenario_id}/{step}: surge added "
            f"({delta_unique} unique / {delta_raw} raw), expected "
            f"{n_payload_new}")
        assert len(added_cumulative) - prev_cumulative == n_payload_new, (
            f"A6 {scenario_id}/{step}: registry increment mismatch")
    else:
        assert delta_unique == 0 and delta_raw == 0, (
            f"A6 {scenario_id}/{step}: non-surge event added demands")
        assert len(added_cumulative) == prev_cumulative, (
            f"A6 {scenario_id}/{step}: registry grew on a non-surge event")
# =========================================================================== #



# --------------------------------------------------------------------------- #
# scenario matrix access
# --------------------------------------------------------------------------- #
def load_scenarios() -> list[dict[str, Any]]:
    """Read the scenario matrix rows (28 by default)."""
    import yaml

    matrix = yaml.safe_load(
        (ROOT / "config" / "scenario_matrix.yaml").read_text(encoding="utf-8")
    )
    return list(matrix["scenarios"])


def scenario_seed(scenario_id: str, seed: int) -> int:
    """Deterministic per-(scenario, seed) RNG seed (hash based, stable)."""
    h = int.from_bytes(scenario_id.encode("utf-8"), "big") & 0xFFFFFFFF
    return (h ^ (seed & 0xFFFFFFFF)) & 0xFFFFFFFF


# --------------------------------------------------------------------------- #
# one scenario instance
# --------------------------------------------------------------------------- #
def build_instance(scenario_id: str, seed: int, provider: str = "haversine"):
    """Build (event, tasks, problem, resource_base) for one matrix row.

    ``provider="haversine"`` (default) mirrors ``run_experiments.build_problem_for``
    exactly, so the legacy dynamic arm and the static benchmark (E1/E2/E3) see
    the same instances.

    Matrix-backed providers (``network`` / ``haversine_matrix``) instead mirror
    ``run_net_experiments.run_net_benchmark`` (the NET-E1b construction): the
    39-crew primary network pool with audited unit-coordinate proxies, the
    scenario network proxy endpoint, scarcity sampled with the same
    ``scenario_seed`` rule, and matrix lookups by ``(resource_seq, scenario_id)``.
    The resource pool therefore differs between the two bases by design and is
    recorded per run; the two bases are never pooled into one comparison.
    """
    from run_experiments import _event_for, _scenario_meta

    event = _event_for(scenario_id)
    tasks, ratio, _loc = _scenario_meta(scenario_id)

    if provider == "haversine":
        from run_experiments import build_problem_for

        _none, problem = build_problem_for(scenario_id, seed)
    else:
        from run_net_experiments import (
            load_official_teams_primary_network,
            load_scenario_proxy_coords,
        )
        from src.dispatch.problem import DispatchProblem, demands_from_tasks

        avail = list(load_official_teams_primary_network())
        if 0.0 < ratio < 1.0:
            rng = random.Random(scenario_seed(scenario_id, seed))
            k = max(1, int(round(len(avail) * ratio)))
            avail = rng.sample(avail, k)
        ev_lat, ev_lon = load_scenario_proxy_coords()[scenario_id]
        problem = DispatchProblem(
            resources=avail,
            demands=demands_from_tasks(tasks),
            event_latitude=ev_lat,
            event_longitude=ev_lon,
            distance_provider=provider,
            scenario_id=scenario_id,
        )

    from src.resource_engine import build_resource_base

    base = build_resource_base(include_simulated=True)
    return event, tasks, problem, base, ratio


def _degradation(before: dict[str, Any], after: dict[str, Any]) -> float:
    """Relative degradation of the carried-over plan (same rule as spec §73)."""
    from src.dispatch.redispatch import degradation

    return degradation(before, after)


def _make_payloads(
    profile: str,
    scenario_id: str,
    seed: int,
    assigned_ids: list[str],
    rng: random.Random,
) -> list[tuple[str, dict[str, Any]]]:
    """Build the concrete event payloads for a profile.

    ``assigned_ids`` are the crews used by the *initial* plan; the disturbance
    draws from them so the failure/closure actually degrades that plan.
    """
    payloads: list[tuple[str, dict[str, Any]]] = []

    if not assigned_ids:
        return payloads

    order = list(assigned_ids)
    rng.shuffle(order)

    victim = order[0]
    closure_targets = order[1 : 1 + min(2, max(1, len(order) - 1))]

    if profile in ("resource_failure", "compound"):
        payloads.append(
            ("resource_failure", {"resource_id": victim, "reason": "车辆故障（合成扰动）"})
        )
    if profile in ("road_closure", "compound"):
        # No road-network topology is used in this replay, so the impacted crews
        # are declared explicitly. This is a synthetic scenario assumption, not
        # a route inference.
        payloads.append(
            (
                "road_closure",
                {
                    "blocked_reference": "G3011-K352+000",
                    "affected_resource_ids": closure_targets,
                },
            )
        )
    if profile in ("demand_surge", "compound"):
        payloads.append(
            (
                "demand_surge",
                {
                    "demands": [
                        {
                            "task_id": "E9-NEW-T1",
                            "resource_type": "RESCUE_TEAM",
                            "quantity": 1,
                        },
                        {
                            "task_id": "E9-NEW-T2",
                            "resource_type": "MEDICAL_TEAM",
                            "quantity": 1,
                        },
                    ]
                },
            )
        )
    if profile == "compound":
        spare = [r for r in order if r != victim and r not in closure_targets]
        if spare:
            payloads.append(
                (
                    "resource_failure",
                    {"resource_id": spare[0], "reason": "二次故障（合成扰动）"},
                )
            )
    return payloads


# --------------------------------------------------------------------------- #
# one run - five independent strategy trajectories
# --------------------------------------------------------------------------- #
def run_one(
    scenario_id: str,
    seed: int,
    profile: str,
    *,
    strategy: str,
    population: int,
    generations: int,
    threshold: float,
    period: int = PERIOD,
    provider: str = "haversine",
) -> dict[str, Any]:
    """Replay one scenario x seed x profile as five independent trajectories."""
    from src.common.enums import ResourceStatus
    from src.dispatch.nsga2 import NSGA2Dispatcher
    from src.dispatch.objectives import evaluate
    from src.dispatch.problem import DispatchProblem, demands_from_tasks
    from src.dispatch.redispatch import (
        ReDispatchConfig,
        assignment_to_complete_mapping,
        map_assignment,
        solution_stability,
    )
    from src.pipeline.event_registry import DynamicEventKind, EventRegistry

    event, tasks, problem, base, ratio = build_instance(scenario_id, seed, provider)
    demands = demands_from_tasks(tasks)

    # ---- initial (pre-disturbance) plan ---------------------------------- #
    available = [r for r in problem.resources if r.status is ResourceStatus.AVAILABLE]
    init_problem = DispatchProblem(
        resources=available,
        demands=demands,
        event_latitude=problem.event_latitude,
        event_longitude=problem.event_longitude,
        distance_provider=provider,
        scenario_id=scenario_id,
    )
    dispatcher = NSGA2Dispatcher(
        proposed=(strategy == "proposed_nsga2"),
        seed=scenario_seed(scenario_id, seed),
        population_size=population,
        generations=generations,
    )
    init_assignment = dispatcher.solve(init_problem)
    init_metrics = evaluate(init_problem, init_assignment).to_dict()
    assigned_ids = sorted(
        {
            init_problem.resources[j].resource_id
            for j in init_assignment
            if 0 <= j < len(init_problem.resources)
        }
    )

    # ---- per-arm mutable state ------------------------------------------- #
    state: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        state[arm] = {
            "problem": init_problem,
            "assignment": list(init_assignment),
            "metrics": dict(init_metrics),
            "prev_complete": assignment_to_complete_mapping(
                init_problem, init_assignment
            ),
        }

    # ---- the disturbance sequence (shared exogenous world state) ---------- #
    rng = random.Random(scenario_seed(scenario_id, seed) ^ 0x9E3779B9)
    payloads = _make_payloads(profile, scenario_id, seed, assigned_ids, rng)

    registry = EventRegistry(base)
    event_rows: list[dict[str, Any]] = []
    # canonical active-demand-set state, independent of any arm's carried plan
    prev_active_ids: list[str] = [d.task_id for d in init_problem.demands]
    prev_cumulative = 0

    for step, (kind_name, payload) in enumerate(payloads, start=1):
        kind = _KIND_BY_PROFILE[kind_name]
        event_obj, _impact = registry.register(
            kind, payload, timestamp=f"2026-11-05T09:{30 + step:02d}:00",
            note="E9 v4 synthetic replay",
        )

        unusable = registry.unusable_resource_ids()
        # FIX: v4 appended the FULL current demand set to the FULL previous set
        # at every event.  Maintain one canonical active set instead.
        active_demands = canonical_active_demands(
            init_problem.demands, registry.demands_added())
        assert_demand_integrity(
            scenario_id=scenario_id, step=step, kind_name=kind_name,
            payload=payload, d0=init_problem.demands,
            added_cumulative=registry.demands_added(),
            active=active_demands, prev_active_ids=prev_active_ids,
            prev_cumulative=prev_cumulative)
        _new_ids_this_event = [d.task_id for d in active_demands
                              if d.task_id not in set(prev_active_ids)]
        prev_active_ids = [d.task_id for d in active_demands]
        prev_cumulative = len(registry.demands_added())

        # Per-event re-dispatch configuration (dispatchers are built per arm
        # inside the loop because each arm's carried plan differs).
        cfg = ReDispatchConfig(
            strategy=strategy,
            seed=scenario_seed(scenario_id, seed),
            population_size=population,
            generations=generations,
        )

        row: dict[str, Any] = {
            "scenario_id": scenario_id,
            "seed": seed,
            "profile": profile,
            "event_id": event_obj.event_id,
            "event_kind": kind_name,
            "step": step,
        }
        # --- group 1: event-triggered's OWN degradation -------------------- #
        row["event_triggered_degradation"] = ""   # filled in that arm's branch
        row["event_triggered_threshold"] = threshold
        # --- group 3: demand integrity --------------------------------------- #
        _aid = [d.task_id for d in active_demands]
        row["n_demands_active"] = len(active_demands)
        row["n_unique_task_ids"] = len(set(_aid))
        row["n_duplicate_task_ids"] = len(active_demands) - len(set(_aid))
        row["n_new_demands"] = len(_new_ids_this_event)
        row["new_demand_ids_this_event"] = ";".join(_new_ids_this_event)
        row["demand_ids_digest"] = hashlib.sha256(
            "|".join(_aid).encode()).hexdigest()[:16]

        # Reference degradation for the descriptive trigger table: how much the
        # "do-nothing" (keep) plan is hurt by this event.
        keep_arm = state["keep"]
        keep_new = DispatchProblem(
            resources=[r for r in keep_arm["problem"].resources
                       if r.resource_id not in unusable
                       and r.status is ResourceStatus.AVAILABLE],
            demands=list(active_demands),  # FIX: canonical active set
            event_latitude=keep_arm["problem"].event_latitude,
            event_longitude=keep_arm["problem"].event_longitude,
            distance_provider=provider,
            scenario_id=scenario_id,
        )
        keep_carried = map_assignment(
            keep_arm["problem"], keep_arm["assignment"], keep_new
        )
        keep_metrics = evaluate(keep_new, keep_carried).to_dict()
        deg_keep = _degradation(keep_arm["metrics"], keep_metrics)
        row["degradation_keep"] = round(deg_keep, 6)
        row["triggered_keep"] = bool(deg_keep > threshold)

        # ---- each arm reacts independently -------------------------------- #
        for arm in ARMS:
            a = state[arm]
            new_problem = DispatchProblem(
                resources=[r for r in a["problem"].resources
                           if r.resource_id not in unusable
                           and r.status is ResourceStatus.AVAILABLE],
                demands=list(active_demands),  # FIX: canonical active set
                event_latitude=a["problem"].event_latitude,
                event_longitude=a["problem"].event_longitude,
                distance_provider=provider,
                scenario_id=scenario_id,
            )
            carried = map_assignment(a["problem"], a["assignment"], new_problem)

            # Dispatchers are built per arm inside the loop because each arm's
            # carried plan (and therefore its warm-start seed) differs.
            # ---- group 2: one decision point, one recorded solver call ---- #
            sd = {"attempted": False, "completed": False, "exception": "",
                  "runtime_s": 0.0}
            if arm == "keep":
                should_solve, seed_assignments = False, None
            elif arm == "warm":
                should_solve, seed_assignments = True, [carried]
            elif arm == "cold":
                should_solve, seed_assignments = True, None
            elif arm == "fixed_period":
                should_solve = (step % period == 0)
                seed_assignments = None
            else:  # event_triggered: degradation of THIS arm's carried plan
                deg_arm = _degradation(
                    a["metrics"], evaluate(new_problem, carried).to_dict())
                row["event_triggered_degradation"] = round(deg_arm, 6)
                row["event_triggered_threshold"] = threshold
                should_solve = deg_arm > threshold
                seed_assignments = [carried]

            reopt = bool(should_solve)
            rt = 0.0
            if should_solve:
                t0 = time.perf_counter()
                sd["attempted"] = True
                try:
                    applied = NSGA2Dispatcher(
                        proposed=(strategy == "proposed_nsga2"),
                        seed=cfg.seed, population_size=population,
                        generations=generations,
                        seed_assignments=seed_assignments,
                    ).solve(new_problem)
                    sd["completed"] = True
                except Exception as exc:  # keep diagnostics, then fail loudly
                    sd["exception"] = f"{type(exc).__name__}: {exc}"
                    raise SolverCallError(sd) from exc
                finally:
                    sd["runtime_s"] = time.perf_counter() - t0
                    rt = sd["runtime_s"]
            else:
                applied = list(carried)

            applied_metrics = evaluate(new_problem, applied).to_dict()
            prev_complete = a["prev_complete"]
            new_complete = assignment_to_complete_mapping(new_problem, applied)
            # group 3: no silent overwrite of duplicate task IDs is allowed
            assert len(applied) == len(new_problem.demands), (
                f"A4b {scenario_id}/{step}/{arm}: assignment length "
                f"{len(applied)} != n_demands {len(new_problem.demands)}")
            assert len(new_complete) == len(new_problem.demands), (
                f"A4c {scenario_id}/{step}/{arm}: complete mapping has "
                f"{len(new_complete)} keys for {len(new_problem.demands)} "
                f"demands -> duplicate task ids were overwritten")
            stability = solution_stability(prev_complete, new_complete)
            # reassignment fraction vs the carried plan (this event)
            n = len(new_problem.demands)
            reassign = (
                sum(1 for j in range(n) if applied[j] != carried[j]) / n if n else 0.0
            )

            row[f"{arm}_fulfillment"] = round(applied_metrics["demand_fulfillment_rate"], 6)
            row[f"{arm}_distance_km"] = round(applied_metrics["weighted_response_distance_km"], 4)
            row[f"{arm}_unmet"] = int(applied_metrics.get("unmet_demands", 0))
            row[f"{arm}_stability"] = round(stability, 6)
            row[f"{arm}_violations"] = int(applied_metrics.get("violation_count", 0))
            row[f"{arm}_runtime_s"] = round(rt, 6)
            row[f"{arm}_reopt"] = bool(reopt)
            # --- group 2: per-arm solver bookkeeping ----------------------- #
            row[f"{arm}_solve_attempted"] = sd["attempted"]
            row[f"{arm}_solve_completed"] = sd["completed"]
            row[f"{arm}_solve_exception"] = sd["exception"]
            row[f"{arm}_solve_runtime_s"] = round(sd["runtime_s"], 6)
            row[f"{arm}_solve_invocations"] = 1 if sd["attempted"] else 0
            # --- group 3: per-arm demand / mapping integrity --------------- #
            row[f"{arm}_n_demands"] = len(new_problem.demands)
            row[f"{arm}_assignment_count"] = len(applied)
            row[f"{arm}_mapping_count"] = len(new_complete)
            row[f"{arm}_demand_ids_digest"] = hashlib.sha256(
                "|".join(d.task_id for d in new_problem.demands).encode()
            ).hexdigest()[:16]
            row[f"{arm}_reassign_frac"] = round(reassign, 6)

            # advance this arm's state
            a["problem"] = new_problem
            a["assignment"] = list(applied)
            a["metrics"] = applied_metrics
            a["prev_complete"] = new_complete

        # --- event-level group 2 / 3 aggregates and hard assertion --------- #
        row["assignment_count"] = row["warm_assignment_count"]
        row["mapping_count"] = row["warm_mapping_count"]
        row["n_solve_attempted"] = sum(
            1 for a in ARMS if row[f"{a}_solve_attempted"])
        row["n_solve_completed"] = sum(
            1 for a in ARMS if row[f"{a}_solve_completed"])
        row["n_solve_exceptions"] = sum(
            1 for a in ARMS if row[f"{a}_solve_exception"])
        row["solve_attempted"] = row["n_solve_attempted"] > 0
        row["solve_completed"] = (
            row["n_solve_completed"] == row["n_solve_attempted"])
        row["solve_exception"] = ";".join(
            row[f"{a}_solve_exception"] for a in ARMS
            if row[f"{a}_solve_exception"])
        row["solve_runtime_s"] = round(sum(
            row[f"{a}_solve_runtime_s"] for a in ARMS), 6)
        _digests = {row[f"{a}_demand_ids_digest"] for a in ARMS}
        assert len(_digests) == 1, (
            f"A5 {scenario_id}/{step}: five arms disagree on demand set")
        assert (row["n_demands_active"] == row["n_unique_task_ids"]
                == row["assignment_count"] == row["mapping_count"]), (
            f"A7 {scenario_id}/{step}: N_demands={row['n_demands_active']}, "
            f"N_unique={row['n_unique_task_ids']}, "
            f"N_assignments={row['assignment_count']}, "
            f"N_mapping={row['mapping_count']} -> allowed-exception set is EMPTY")
        assert all(row[f"{a}_assignment_count"] == row["n_demands_active"]
                   and row[f"{a}_mapping_count"] == row["n_demands_active"]
                   for a in ARMS), (
            f"A7 {scenario_id}/{step}: per-arm count mismatch")
        event_rows.append(row)

    return {
        "scenario_id": scenario_id,
        "seed": seed,
        "profile": profile,
        "strategy": strategy,
        "distance_provider": provider,
        "variant": VARIANT,
        "n_events": len(event_rows),
        "scarcity_ratio": ratio,
        "n_demands": len(init_problem.demands),
        "n_resources": len(init_problem.resources),
        "init_fulfillment": round(init_metrics["demand_fulfillment_rate"], 6),
        "init_distance_km": round(init_metrics["weighted_response_distance_km"], 4),
        "events": event_rows,
        "arms": {
            "keep": "retain the carried-over plan, never re-optimises",
            "warm": "warm-started re-optimisation every event (system policy)",
            "cold": "cold-started re-optimisation every event",
            "fixed_period": f"re-optimises every {period} events, keeps otherwise",
            "event_triggered": "re-optimises only when carried-plan degradation "
                               "> threshold (uses the trigger)",
        },
    }


# --------------------------------------------------------------------------- #
# resumable sharded driver
# --------------------------------------------------------------------------- #
def _shard_file(out: Path, shard_index: int) -> Path:
    return out / f"_shards" / f"shard_{shard_index:02d}.jsonl"


def _completed_keys(path: Path) -> set[tuple]:
    keys: set[tuple] = set()
    if not path.exists():
        return keys
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            keys.add((rec["scenario_id"], rec["seed"], rec["profile"]))
    return keys


def _assign_scenarios(scenarios: list[dict], shards: int) -> list[list[dict]]:
    n = len(scenarios)
    base = n // shards
    rem = n % shards
    chunks: list[list[dict]] = []
    i = 0
    for s in range(shards):
        size = base + (1 if s < rem else 0)
        chunks.append(scenarios[i:i + size])
        i += size
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=20,
                        help="independent seeds per (scenario, profile)")
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=30)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--period", type=int, default=PERIOD)
    parser.add_argument("--distance-provider",
                        choices=("haversine", "network", "haversine_matrix"),
                        default="haversine",
                        help="haversine = legacy E9 basis (synthetic coords, "
                             "47-crew roster); network/haversine_matrix = "
                             "NET-E1b basis (39-crew primary pool, OSM matrix)")
    parser.add_argument("--strategy", choices=("standard_nsga2", "proposed_nsga2"),
                        default="proposed_nsga2")
    parser.add_argument("--scenarios", type=str, default="",
                        help="comma separated scenario ids; default = all 28")
    parser.add_argument("--profiles", type=str, default=",".join(PROFILES))
    parser.add_argument("--out", type=Path,
                        default=ROOT / "experiments" / "outputs" / "_v5_staging_unused")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--status", action="store_true",
                        help="print completed counts per shard and exit")
    parser.add_argument("--merge", action="store_true",
                        help="concatenate shards and write canonical CSVs + summary")
    args = parser.parse_args()

    if args.status:
        for s in range(args.shards):
            p = _shard_file(args.out, s)
            print(f"shard {s:02d}: {len(_completed_keys(p))} runs")
        return 0

    if args.merge:
        return _merge(args)

    if args.replicates < 1 or args.population < 4 or args.generations < 1:
        parser.error("replicates>=1, population>=4 and generations>=1 are required")

    scenarios = load_scenarios()
    if args.scenarios.strip():
        wanted = {s.strip() for s in args.scenarios.split(",") if s.strip()}
        scenarios = [s for s in scenarios if s["scenario_id"] in wanted]
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]

    chunks = _assign_scenarios(scenarios, args.shards)
    my_scenarios = chunks[args.shard_index % args.shards]
    shard_path = _shard_file(args.out, args.shard_index % args.shards)
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    done = _completed_keys(shard_path)

    jobs = [
        (sc["scenario_id"], args.seed_start + rep, profile)
        for sc in my_scenarios
        for profile in profiles
        for rep in range(args.replicates)
    ]
    jobs = [j for j in jobs if j not in done]
    print(f"E9 v4 shard {args.shard_index}: {len(my_scenarios)} scenarios, "
          f"{len(jobs)} remaining jobs "
          f"({len(my_scenarios)} scenarios x {args.replicates} seeds x "
          f"{len(profiles)} profiles), out={args.out}", flush=True)

    start_all = time.perf_counter()
    n_ok = 0
    n_fail = 0
    with shard_path.open("a", encoding="utf-8") as fh:
        for k, (sid, seed, profile) in enumerate(jobs, start=1):
            try:
                rec = run_one(
                    sid, seed, profile,
                    strategy=args.strategy, population=args.population,
                    generations=args.generations, threshold=args.threshold,
                    period=args.period, provider=args.distance_provider,
                )
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n_ok += 1
            except Exception as exc:  # pragma: no cover - defensive
                n_fail += 1
                print(f"  FAIL {sid}/{seed}/{profile}: {type(exc).__name__}: {exc}",
                      flush=True)
            if k % 10 == 0 or k == len(jobs):
                print(f"  [{k}/{len(jobs)}] ok={n_ok} fail={n_fail} "
                      f"elapsed={time.perf_counter() - start_all:.0f}s", flush=True)
    print(f"shard {args.shard_index} done: ok={n_ok} fail={n_fail} "
          f"elapsed={time.perf_counter() - start_all:.0f}s")
    return 0 if n_fail == 0 else 2


def _merge(args) -> int:
    out = args.out
    runs: list[dict[str, Any]] = []
    for s in range(args.shards):
        p = _shard_file(out, s)
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))

    if not runs:
        print("no shard data to merge")
        return 1

    event_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    for r in runs:
        rows = r.pop("events")
        event_rows.extend(rows)
        rec = {
            "scenario_id": r["scenario_id"],
            "seed": r["seed"],
            "profile": r["profile"],
            "n_events": r["n_events"],
            "scarcity_ratio": r["scarcity_ratio"],
            "n_demands": r["n_demands"],
            "n_resources": r["n_resources"],
            "init_fulfillment": r["init_fulfillment"],
            "init_distance_km": r["init_distance_km"],
        }
        for arm in ARMS:
            f = [x[f"{arm}_fulfillment"] for x in rows]
            d = [x[f"{arm}_distance_km"] for x in rows]
            u = [x[f"{arm}_unmet"] for x in rows]
            st = [x[f"{arm}_stability"] for x in rows]
            v = [x[f"{arm}_violations"] for x in rows]
            rt = [x[f"{arm}_runtime_s"] for x in rows]
            reo = [1 if x[f"{arm}_reopt"] else 0 for x in rows]
            ra = [x[f"{arm}_reassign_frac"] for x in rows]
            rec[f"{arm}_fulfillment_mean"] = round(sum(f) / len(f), 6)
            rec[f"{arm}_distance_km_mean"] = round(sum(d) / len(d), 4)
            rec[f"{arm}_unmet_mean"] = round(sum(u) / len(u), 6)
            rec[f"{arm}_stability_mean"] = round(sum(st) / len(st), 6)
            rec[f"{arm}_violations_mean"] = round(sum(v) / len(v), 6)
            rec[f"{arm}_runtime_s_total"] = round(sum(rt), 6)
            rec[f"{arm}_n_reopt"] = sum(reo)
            rec[f"{arm}_reassign_total"] = round(sum(ra), 6)
            rec[f"{arm}_worst_fulfillment"] = round(min(f), 6)
            rec[f"{arm}_n_events_below_init"] = sum(
                1 for x in rows if x[f"{arm}_fulfillment"] < r["init_fulfillment"] - 1e-9
            )
            rec[f"{arm}_cumulative_unmet"] = sum(u)
        rec["n_triggered"] = sum(1 for x in rows if x["triggered_keep"])
        rec["degradation_mean"] = round(
            sum(x["degradation_keep"] for x in rows) / len(rows), 6
        )
        run_rows.append(rec)

    _write_csv(out / "event_level_results.csv", event_rows)
    _write_csv(out / "run_level_results.csv", run_rows)

    summary = {
        "experiment": "E9_dynamic_replay_v5_verified",
        "status": "complete" if all(_completed_keys(_shard_file(out, s))
                                    for s in range(args.shards)) else "partial",
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variant": VARIANT,
        "demand_integrity": {
            "rule": "D_t = D_0 UNION D_added,t, keyed by task_id",
            "four_count_identity": "N_demands == N_unique == N_assignments == N_mapping",
            "allowed_exceptions": [],
            "six_runtime_assertions": True,
            "solver_diagnostics": True,
            "event_triggered_own_degradation": True,
        },
        "config": {
            "replicates_per_scenario_profile": args.replicates,
            "n_scenarios": len({r["scenario_id"] for r in runs}),
            "scenario_ids": sorted({r["scenario_id"] for r in runs}),
            "profiles": sorted({r["profile"] for r in runs}),
            "population_size": args.population,
            "generations": args.generations,
            "seed_start": args.seed_start,
            "threshold": args.threshold,
            "period": args.period,
            "strategy": args.strategy,
            "distance_provider": args.distance_provider,
            "arms": ARMS,
        },
        "design": {
            "unit_of_analysis": "run (scenario x seed x profile); events nested inside",
            "each_arm_owns_trajectory": True,
            "trigger_used": True,
            "arms": {
                "keep": "never re-optimises",
                "warm": "warm-started re-optimisation every event",
                "cold": "cold-started re-optimisation every event",
                "fixed_period": f"re-optimises every {args.period} events",
                "event_triggered": "re-optimises only when degradation > threshold",
            },
        },
        "provenance": {
            "event_sequences": "synthetic event replay, not observed field incidents",
            "road_closure_effect": "affected_resource_ids are explicitly supplied; "
                                   "no road-network topology is used in this replay",
            "distance_model": (
                "precomputed OSM routing matrix by (resource_seq, scenario_id); "
                "'network' = edge-length shortest path, 'haversine_matrix' = "
                "straight line between the same matrix endpoints"
                if args.distance_provider != "haversine" else
                "default haversine (synthetic coordinates), identical "
                "to the static benchmark basis; network distance is "
                "validated separately in NET-E1"),
            "coordinates": (
                "official crew unit-coordinate proxies (organization locations, "
                "datum unknown) + synthetic route-relative scenario endpoints "
                "(snap_dist = 0); must not be read as measured travel times"
                if args.distance_provider != "haversine" else
                "synthetic Qinghai bbox coordinates, tagged synthetic; "
                "must not be read as measured travel times"),
            "resource_pool": (
                "official 39-crew primary network pool (road-access QA passed); "
                "synthetic traffic-control teams and simulated equipment excluded"
                if args.distance_provider != "haversine" else
                "official 47-crew roster + simulated inventory + "
                "synthetic traffic-control teams (not the official roster)"),
        },
        "n_runs": len(run_rows),
        "n_event_rows": len(event_rows),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"merged: runs={len(run_rows)} events={len(event_rows)} -> {out}")
    return 0


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
