# -*- coding: utf-8 -*-
"""
analyze_verified_replay.py
==========================
Independent statistical recomputation for ONE config+phase.

Statistical rules required by Young
-----------------------------------
* Unit of analysis = RUN (scenario x seed x profile).
* Events are NESTED inside a run and are NEVER treated as independent samples.
* Primary strategy comparisons are PAIRED on the same scenario / seed / profile.
* Confidence intervals use a SCENARIO-CLUSTERED bootstrap with 28 clusters
  (resample scenarios with replacement, carry all their runs together).
* Config A (haversine / 47-crew) and config B (network / 39-crew) are reported
  SEPARATELY.  They are never pooled: they differ in distance metric, resource
  pool AND coordinate basis, so this is not a controlled comparison.

Usage
-----
  python analyze_verified_replay.py --config A --phase precheck
  python analyze_verified_replay.py --config A --phase full --bootstrap 20000
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARMS = ["keep", "warm", "cold", "fixed_period", "event_triggered"]
METRICS = ["fulfillment_mean", "unmet_mean", "distance_km_mean",
           "stability_mean"]
PAIRS = [("warm", "event_triggered"), ("warm", "fixed_period"),
         ("warm", "keep"), ("warm", "cold"),
         ("event_triggered", "fixed_period"),
         ("event_triggered", "keep")]


def read_csv(p):
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def mean(v):
    return sum(v)/len(v) if v else float("nan")


def quantile(v, q):
    if not v:
        return float("nan")
    s = sorted(v)
    i = min(len(s)-1, max(0, int(round(q*(len(s)-1)))))
    return s[i]


def out_dir(config, phase):
    root = ("E9_v5_legacy" if config == "A" else "NET_E9_v5")
    return ROOT / "experiments" / "outputs" / f"{root}_{phase}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", choices=("A", "B"), required=True)
    ap.add_argument("--phase", choices=("precheck", "full"), default="full")
    ap.add_argument("--bootstrap", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20261112)
    args = ap.parse_args()

    out = out_dir(args.config, args.phase)
    runs = read_csv(out / "run_level_results.csv")
    if not runs:
        print("no runs:", out)
        return 1
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    n_scen = len({r["scenario_id"] for r in runs})
    n_seeds = len({r["seed"] for r in runs})

    # ---- per-arm run-level descriptive ----------------------------------- #
    arms = {}
    for a in ARMS:
        arms[a] = {
            m: round(mean([float(r[f"{a}_{m}"]) for r in runs]), 6)
            for m in METRICS
        }
        arms[a]["runtime_s_total"] = round(
            sum(float(r[f"{a}_runtime_s_total"]) for r in runs), 3)
        arms[a]["n_solve_attempted"] = sum(
            int(r[f"{a}_n_solve_attempted"]) for r in runs)
        arms[a]["n_solve_completed"] = sum(
            int(r[f"{a}_n_solve_completed"]) for r in runs)
        arms[a]["n_solve_exceptions"] = sum(
            int(r[f"{a}_n_solve_exceptions"]) for r in runs)

    # ---- paired contrasts + scenario-clustered bootstrap ----------------- #
    by_scen = defaultdict(list)
    for r in runs:
        by_scen[r["scenario_id"]].append(r)
    scen_ids = sorted(by_scen)
    rng = random.Random(args.seed)
    contrasts = {}
    for a1, a2 in PAIRS:
        key = f"{a1}_minus_{a2}"
        entry = {"metrics": {}}
        for m in METRICS:
            diffs = {}
            for r in runs:
                rk = (r["scenario_id"], r["seed"], r["profile"])
                diffs[rk] = (float(r[f"{a1}_{m}"])
                            - float(r[f"{a2}_{m}"]))
            obs = mean(list(diffs.values()))
            # cluster bootstrap: resample whole scenarios
            boots = []
            for _ in range(args.bootstrap):
                picked = [scen_ids[rng.randrange(len(scen_ids))]
                          for _ in range(len(scen_ids))]
                vals = []
                for sid in picked:
                    for r in by_scen[sid]:
                        rk = (r["scenario_id"], r["seed"], r["profile"])
                        vals.append(diffs[rk])
                boots.append(mean(vals))
            entry["metrics"][m] = {
                "paired_mean_diff": round(obs, 6),
                "ci95_low": round(quantile(boots, 0.025), 6),
                "ci95_high": round(quantile(boots, 0.975), 6),
                "ci_excludes_zero": (quantile(boots, 0.025) > 0
                                     or quantile(boots, 0.975) < 0),
            }
        contrasts[key] = entry

    # ---- solver-call and cost comparison --------------------------------- #
    calls = {a: arms[a]["n_solve_attempted"] for a in ARMS}
    warm_calls = calls["warm"] or 1
    cost = {
        a: {
            "n_solve_attempted": calls[a],
            "share_of_warm": round(calls[a]/warm_calls, 6),
            "runtime_s_total": arms[a]["runtime_s_total"],
            "fulfillment_mean": arms[a]["fulfillment_mean"],
        } for a in ARMS
    }

    report = {
        "tool": "analyze_verified_replay.py",
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": args.config,
        "phase": args.phase,
        "provider": manifest["config"]["provider"],
        "independent_experiment": True,
        "never_pooled_with_other_config": True,
        "n_runs": len(runs), "n_scenarios": n_scen, "n_seeds": n_seeds,
        "n_event_rows": analysis["n_event_rows"],
        "statistical_unit": "run; events nested, never independent samples",
        "bootstrap": {"resamples": args.bootstrap, "clusters": n_scen,
                      "unit": "scenario", "seed": args.seed},
        "inference_caveat": (
            "DESCRIPTIVE ONLY -- precheck has 1 seed, so confidence intervals "
            "here describe scenario-level variability only and MUST NOT be used "
            "for inferential claims."
            if args.phase == "precheck" else
            "Full 20-seed run. CIs are scenario-clustered; no event-level "
            "pseudo-replication."),
        "arms": arms,
        "paired_contrasts_scenario_clustered": contrasts,
        "quality_cost": cost,
        "warm_vs_event_triggered": {
            "identical_event_rows": analysis["warm_vs_event_triggered"]["identical_rows"],
            "total_event_rows": analysis["warm_vs_event_triggered"]["total_rows"],
            "solve_calls_warm": calls["warm"],
            "solve_calls_event_triggered": calls["event_triggered"],
            "event_triggered_reduces_calls": calls["event_triggered"] < calls["warm"],
            "fulfilment_diff": contrasts["warm_minus_event_triggered"]
                               ["metrics"]["fulfillment_mean"],
        },
        "deg_arm": analysis["event_triggered_degradation"],
        "demand_integrity": analysis["demand_integrity"],
    }
    dest = out / "statistical_report.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    lines = [
        f"# 统计复算报告 · 配置 {args.config} ({report['provider']}) · {args.phase}", "",
        f"- 生成 {report['generated_at_local']}；runs {len(runs)}；"
        f"场景簇 {n_scen}；seeds {n_seeds}；事件行 {report['n_event_rows']}"
        "（**嵌套观测，非独立样本**）",
        f"- 场景聚类 bootstrap {args.bootstrap} 次；两配置分开报告，未合并", "",
        f"> {report['inference_caveat']}", "",
        "## 各策略 run 级表现", "",
        "| 策略 | Fulfilment | Unmet | Distance(km) | Stability | 求解调用 | 总耗时(s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for a in ARMS:
        x = arms[a]
        lines.append(f"| {a} | {x['fulfillment_mean']} | {x['unmet_mean']} | "
                     f"{x['distance_km_mean']} | {x['stability_mean']} | "
                     f"{x['n_solve_attempted']} | {x['runtime_s_total']} |")
    lines += ["", "## 配对差与场景聚类 95% CI", "",
              "| 对比 | 指标 | 配对均值差 | CI 下限 | CI 上限 | 不含 0 |",
              "|---|---|---:|---:|---:|---|"]
    for k, e in contrasts.items():
        for m, v in e["metrics"].items():
            lines.append(f"| {k} | {m} | {v['paired_mean_diff']} | "
                         f"{v['ci95_low']} | {v['ci95_high']} | "
                         f"{'是' if v['ci_excludes_zero'] else '否'} |")
    w = report["warm_vs_event_triggered"]
    lines += ["", "## 关键问题", "",
              f"- Warm 求解调用 `{w['solve_calls_warm']}`、"
              f"Event-triggered `{w['solve_calls_event_triggered']}`；"
              f"是否减少：**{'是' if w['event_triggered_reduces_calls'] else '否'}**",
              f"- 逐事件轨迹相同 `{w['identical_event_rows']}/"
              f"{w['total_event_rows']}`",
              f"- Warm − Event-triggered 的 Fulfilment 配对差："
              f"`{w['fulfilment_diff']['paired_mean_diff']}` "
              f"(95% CI [{w['fulfilment_diff']['ci95_low']}, "
              f"{w['fulfilment_diff']['ci95_high']}])", "",
              "## deg_arm 与阈值（描述性）", "",
              f"- 取值 {report['deg_arm']['n']} 条，"
              f"distinct {report['deg_arm']['distinct']}，"
              f"min/median/max = {report['deg_arm']['min']}/"
              f"{report['deg_arm']['median']}/{report['deg_arm']['max']}", ""]
    (out / "statistical_report.md").write_text("\n".join(lines),
                                                encoding="utf-8")
    print(f"config={args.config} phase={args.phase} runs={len(runs)} "
          f"scenarios={n_scen} seeds={n_seeds}")
    print(f"  warm calls={calls['warm']} ET calls={calls['event_triggered']} "
          f"fixed={calls['fixed_period']} keep={calls['keep']}")
    print(f"  warm-ET fulfilment diff="
          f"{contrasts['warm_minus_event_triggered']['metrics']['fulfillment_mean']}")
    print("written ->", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
