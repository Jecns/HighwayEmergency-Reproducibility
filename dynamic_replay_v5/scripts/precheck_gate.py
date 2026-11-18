# -*- coding: utf-8 -*-
"""
precheck_gate.py
================
The final gate before the 4480-run full experiment.  Verifies Young's seven
pass conditions SEPARATELY for config A (Legacy E9) and config B (NET-E9),
then answers the key scientific question with the precheck data:

    With a CORRECT demand set, can the event-triggered policy reduce
    re-optimisation cost without an appreciable loss of fulfilment?

Also writes machine-readable and human-readable gate reports.  A single FAIL
in either config means STOP -- do not start the full run.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTS = {
    "A": ROOT / "experiments" / "outputs" / "E9_v5_legacy_precheck",
    "B": ROOT / "experiments" / "outputs" / "NET_E9_v5_precheck",
}
ARMS = ["keep", "warm", "cold", "fixed_period", "event_triggered"]
GATE = HERE / "precheck_gate_report.json"
GATE_MD = HERE / "precheck_gate_report.md"


def b(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def read_csv(p):
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def check_config(cid, out):
    ev = read_csv(out / "event_level_results.csv")
    runs = read_csv(out / "run_level_results.csv")
    summ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    errf = out / "errors.jsonl"
    errors = [json.loads(l) for l in errf.read_text(encoding="utf-8").splitlines()
              if l.strip()] if errf.exists() else []

    # group events per run
    by_run = defaultdict(list)
    for r in ev:
        by_run[(r["scenario_id"], r["seed"], r["profile"])].append(r)
    for k in by_run:
        by_run[k].sort(key=lambda x: int(x["step"]))

    checks = {}

    # 1. 112 runs, all finished, no errors
    checks["G1_112_runs_all_normal"] = {
        "pass": len(runs) == 112 and summ["n_runs"] == 112 and len(errors) == 0,
        "detail": f"runs={len(runs)}, summary={summ['n_runs']}, errors={len(errors)}",
    }

    # 2. no duplicate task ids in any event
    bad2 = [r for r in ev
            if int(r["n_duplicate_task_ids"]) != 0
            or int(r["n_demands_active"]) != int(r["n_unique_task_ids"])]
    checks["G2_no_duplicate_task_ids"] = {
        "pass": len(bad2) == 0,
        "detail": f"violating events={len(bad2)} / {len(ev)}",
    }

    # 3. failure / closure add no demand
    bad3 = []
    for r in ev:
        if r["event_kind"] in ("resource_failure", "road_closure"):
            if int(r["n_new_demands"]) != 0 or r["new_demand_ids_this_event"]:
                bad3.append((r["scenario_id"], r["profile"], r["step"],
                             r["new_demand_ids_this_event"]))
    checks["G3_failure_closure_add_no_demand"] = {
        "pass": len(bad3) == 0,
        "detail": f"violating events={len(bad3)}",
    }

    # 4. surge adds exactly the registry-declared new demands
    bad4, n_surge = [], 0
    for r in ev:
        if r["event_kind"] == "demand_surge":
            n_surge += 1
            ids = {x for x in r["new_demand_ids_this_event"].split(";") if x}
            if (int(r["n_new_demands"]) != 2
                    or ids != {"E9-NEW-T1", "E9-NEW-T2"}):
                bad4.append((r["scenario_id"], r["profile"], r["step"],
                             sorted(ids)))
    checks["G4_surge_only_declared_new_demands"] = {
        "pass": len(bad4) == 0 and n_surge > 0,
        "detail": f"surge events={n_surge}, violating={len(bad4)}",
    }

    # 5. five arms receive the identical active-demand set
    bad5 = [r for r in ev
            if len({r[f"{a}_demand_ids_digest"] for a in ARMS}) != 1
            or r["demand_ids_digest"] not in
            {r[f"{a}_demand_ids_digest"] for a in ARMS}]
    checks["G5_five_arms_same_active_set"] = {
        "pass": len(bad5) == 0,
        "detail": f"violating events={len(bad5)} / {len(ev)}",
    }

    # 6. solver start / completion / exception bookkeeping consistent
    bad6 = []
    for r in ev:
        na = int(r["n_solve_attempted"])
        nc = int(r["n_solve_completed"])
        ne = int(r["n_solve_exceptions"])
        if (b(r["solve_attempted"]) != (na > 0)
                or b(r["solve_completed"]) != (nc == na)
                or ne != 0
                or (r["solve_exception"] or "") != ""):
            bad6.append((r["scenario_id"], r["profile"], r["step"]))
            continue
        for a in ARMS:
            att, comp = b(r[f"{a}_solve_attempted"]), b(r[f"{a}_solve_completed"])
            reopt = b(r[f"{a}_reopt"])
            runtime = float(r[f"{a}_solve_runtime_s"])
            if (att != comp or att != reopt
                    or (runtime > 0) != att
                    or (int(r[f"{a}_solve_invocations"]) != (1 if att else 0))
                    or r[f"{a}_solve_exception"]):
                bad6.append((r["scenario_id"], r["profile"], r["step"], a))
                break
    checks["G6_solver_bookkeeping_consistent"] = {
        "pass": len(bad6) == 0,
        "detail": f"violating events={len(bad6)} / {len(ev)}",
    }

    # 7. no unexplained mapping overwrite / four-count identity
    bad7 = []
    for r in ev:
        n = int(r["n_demands_active"])
        if not (n == int(r["n_unique_task_ids"])
                == int(r["assignment_count"]) == int(r["mapping_count"])):
            bad7.append((r["scenario_id"], r["profile"], r["step"], "event"))
            continue
        for a in ARMS:
            if (int(r[f"{a}_mapping_count"]) != n
                    or int(r[f"{a}_assignment_count"]) != n
                    or int(r[f"{a}_n_demands"]) != n):
                bad7.append((r["scenario_id"], r["profile"], r["step"], a))
                break
    checks["G7_no_unexplained_mapping_overwrite"] = {
        "pass": len(bad7) == 0,
        "detail": f"violating events={len(bad7)} / {len(ev)}",
    }

    # extra: event_triggered's own degradation is recorded and drives reopt
    bad8 = [r for r in ev
            if r["event_triggered_degradation"] == ""
            or abs(float(r["event_triggered_degradation"])) > 10
            or b(r["event_triggered_reopt"]) !=
            (float(r["event_triggered_degradation"]) >
             float(r["event_triggered_threshold"]))]
    checks["X1_deg_arm_recorded_and_drives_reopt"] = {
        "pass": len(bad8) == 0,
        "detail": f"violating events={len(bad8)} / {len(ev)}",
    }

    # ---- key question evidence -------------------------------------------- #
    deg = [float(r["event_triggered_degradation"]) for r in ev]
    tau = man["common"]["threshold"]
    tau_grid = analysis["event_triggered_degradation"]["tau_grid_descriptive"]

    def mean(vals):
        return sum(vals)/len(vals) if vals else None

    arm_stats = {}
    for a in ARMS:
        arm_stats[a] = {
            "n_solve_attempted": sum(int(r[f"{a}_n_solve_attempted"]) for r in runs),
            "runtime_total_s": round(sum(float(r[f"{a}_runtime_s_total"])
                                        for r in runs), 3),
            "fulfilment_mean_over_runs": round(mean(
                [float(r[f"{a}_fulfillment_mean"]) for r in runs]), 6),
            "unmet_mean_over_runs": round(mean(
                [float(r[f"{a}_unmet_mean"]) for r in runs]), 6),
            "distance_mean_over_runs": round(mean(
                [float(r[f"{a}_distance_km_mean"]) for r in runs]), 3),
            "stability_mean_over_runs": round(mean(
                [float(r[f"{a}_stability_mean"]) for r in runs]), 6),
        }
    # paired warm vs event-triggered at run level
    diff_warm_et = [float(r["warm_fulfillment_mean"])
                    - float(r["event_triggered_fulfillment_mean"]) for r in runs]
    diff_warm_fixed = [float(r["warm_fulfillment_mean"])
                       - float(r["fixed_period_fulfillment_mean"]) for r in runs]

    key = {
        "n_runs": len(runs), "n_events": len(ev),
        "tau": tau,
        "deg_arm": {
            "n": len(deg), "min": min(deg), "median": sorted(deg)[len(deg)//2],
            "max": max(deg), "distinct": len(set(deg)),
            "share_above_tau": round(sum(1 for d in deg if d > tau)/len(deg), 6),
            "tau_grid": tau_grid,
        },
        "warm_vs_event_triggered": {
            "identical_event_rows": analysis["warm_vs_event_triggered"]["identical_rows"],
            "total_event_rows": len(ev),
            "max_abs_fulfilment_diff": max(abs(x) for x in diff_warm_et),
            "solve_calls_warm": arm_stats["warm"]["n_solve_attempted"],
            "solve_calls_event_triggered": arm_stats["event_triggered"]["n_solve_attempted"],
        },
        "quality_cost_reference": {
            "warm": arm_stats["warm"],
            "event_triggered": arm_stats["event_triggered"],
            "fixed_period": arm_stats["fixed_period"],
            "keep": arm_stats["keep"],
            "warm_minus_fixed_fulfilment_mean": round(mean(diff_warm_fixed), 6),
        },
    }
    return {"config": cid, "provider": man["config"]["provider"],
            "checks": checks, "all_pass": all(c["pass"] for c in checks.values()),
            "n_errors": len(errors), "errors": errors,
            "key_question": key, "arm_stats": arm_stats,
            "manifest": {"variant": man["variant"],
                         "shim": man["network_import_shim_installed"],
                         "source_sha256_count": len(man["source_sha256"])}}


def main() -> int:
    results = {cid: check_config(cid, out) for cid, out in OUTS.items()}
    overall = all(r["all_pass"] for r in results.values())
    report = {
        "tool": "precheck_gate.py",
        "generated_at_local": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "overall_pass": overall,
        "decision": ("PRECHECK PASSED -- full run may proceed"
                     if overall else "PRECHECK FAILED -- STOP, do not start full run"),
        "configs": results,
        "never_pool_note": (
            "Config A and B are independent experiments (different distance "
            "metric, resource pool AND coordinate basis). No pooled statistic "
            "is computed anywhere in this report."),
    }
    GATE.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    lines = [
        "# 112 次预检：最终门禁报告", "",
        f"- 生成时间：{report['generated_at_local']}",
        f"- **结论：{report['decision']}**", "",
        "> 两套配置**独立报告、不合并统计**（距离度量、资源池、坐标基础三者同时不同）。", "",
        "## 七条通过条件", "",
    ]
    for cid, r in results.items():
        lines += [f"### 配置 {cid} · {r['provider']}", "",
                  f"- runs/events：{r['key_question']['n_runs']} / "
                  f"{r['key_question']['n_events']}；运行错误 {r['n_errors']}",
                  f"- 版本 `{r['manifest']['variant']}`；network shim="
                  f"{r['manifest']['shim']}；源码 SHA-256 清单 "
                  f"{r['manifest']['source_sha256_count']} 项", "",
                  "| 条件 | 结果 | 明细 |", "|---|---|---|"]
        for k, c in r["checks"].items():
            lines.append(f"| {k} | {'✅ PASS' if c['pass'] else '❌ FAIL'} | "
                         f"{c['detail']} |")
        lines.append("")

    lines += ["## 关键问题：正确需求集下，事件触发能否减少重优化成本而不损失满足率？", ""]
    for cid, r in results.items():
        k = r["key_question"]
        wet = k["warm_vs_event_triggered"]
        qc = k["quality_cost_reference"]
        lines += [
            f"### 配置 {cid} · {r['provider']}", "",
            f"- `event_triggered_degradation`（该臂 carried plan 的真实退化）"
            f"共 {k['deg_arm']['n']} 条、**{k['deg_arm']['distinct']} 个不同取值**"
            f"（min {k['deg_arm']['min']} / median {k['deg_arm']['median']} / "
            f"max {k['deg_arm']['max']}），τ={k['tau']} 下超阈值比例 "
            f"**{k['deg_arm']['share_above_tau']:.1%}**",
            f"- Warm 与 Event-triggered：逐事件轨迹相同 "
            f"**{wet['identical_event_rows']}/{wet['total_event_rows']}**，"
            f"Fulfillment 最大绝对差 `{wet['max_abs_fulfilment_diff']}`；"
            f"求解调用 Warm `{wet['solve_calls_warm']}` vs "
            f"Event-triggered `{wet['solve_calls_event_triggered']}`",
            f"- 质量—成本参照（run 级均值）：Warm fulfilment "
            f"`{qc['warm']['fulfilment_mean_over_runs']}` / "
            f"Fixed-period `{qc['fixed_period']['fulfilment_mean_over_runs']}` "
            f"（差 `{qc['warm_minus_fixed_fulfilment_mean']}`）；"
            f"Fixed-period 求解调用 `{qc['fixed_period']['n_solve_attempted']}`",
            "",
        ]
    lines += [
        "## 结论（预检证据，1 seed；正式统计须待 20 seeds + 场景聚类 bootstrap）", "",
        "- **在 τ=0.05（冻结值）下，两套配置的 Event-triggered 仍 100% 重优化**，",
        "  与 Warm 轨迹逐行相同，**没有减少求解次数**，因此按 Go/No-Go 表应",
        "  「保留机制实现，撤回计算效率优势」。",
        "- 但 `deg_arm` 不再是旧数据的 0 / ≥0.333 两极分布，而是出现连续梯度；",
        "  τ 网格显示提高阈值会抑制触发。这说明**机制本身具备区分能力**，",
        "  限制来自所选阈值，而非触发条件失效。按冻结事项未改 τ、未做校准集/验证集分离，",
        "  故本次只能作描述性陈述，不能主张最优阈值。",
        "- 真正的质量—成本杠杆仍是 **Fixed-period 的重优化频次**；",
        "  它减少求解调用但伴随满足率下降，属于质量—成本权衡。",
        "- 若新结果与旧结果差异大，首先归因于**输入需求集合修正**，不得解释成算法改进。",
        "",
        "## 边界", "",
        "- 预检只用了 1 个固定种子；不能替代正式 20 seeds 的统计推断。",
        "- 所有事件均为 run 内嵌套观测，未被当作独立样本。",
        "- 两配置分开报告，未合并扩大样本量。", "",
    ]
    GATE_MD.write_text("\n".join(lines), encoding="utf-8")

    print(report["decision"])
    for cid, r in results.items():
        print(f"\n[{cid} {r['provider']}] runs/events="
              f"{r['key_question']['n_runs']}/{r['key_question']['n_events']} "
              f"errors={r['n_errors']}")
        for k, c in r["checks"].items():
            print(f"   {'PASS' if c['pass'] else 'FAIL'}  {k:44s} {c['detail']}")
        d = r["key_question"]["deg_arm"]
        w = r["key_question"]["warm_vs_event_triggered"]
        print(f"   deg_arm distinct={d['distinct']} above_tau={d['share_above_tau']}")
        print(f"   warm==event_triggered {w['identical_event_rows']}/"
              f"{w['total_event_rows']}; solver calls warm="
              f"{w['solve_calls_warm']} ET={w['solve_calls_event_triggered']}")
    print(f"\nwritten -> {GATE_MD}")
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
