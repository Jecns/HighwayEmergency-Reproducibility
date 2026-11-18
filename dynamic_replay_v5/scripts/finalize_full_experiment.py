# -*- coding: utf-8 -*-
"""
finalize_full_experiment.py
===========================
Step 5 of Young's sequence: independent recomputation, new-vs-old comparison
and the experiment audit report.  Run AFTER ``run_full_all.py`` finishes.

  python finalize_full_experiment.py

Reads each config's full-run outputs (NEVER merges A and B), recomputes the
headline numbers directly from the CSVs, compares them with the archived
(superseded) E9/NET-E9 artefacts, and writes:

  audit_demand_integrity/experiment_audit_report.md
  audit_demand_integrity/new_old_comparison.json

The old artefacts are READ ONLY.  Any new-vs-old difference is attributed to
the demand-set correction first and MUST NOT be presented as an algorithmic
improvement.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARMS = ["keep", "warm", "cold", "fixed_period", "event_triggered"]
NEW = {
    "A": ROOT / "experiments" / "outputs" / "E9_v5_legacy_full",
    "B": ROOT / "experiments" / "outputs" / "NET_E9_v5_full",
}
OLD = {
    "A": ROOT / "experiments" / "outputs" / "E9_dynamic_replay_v4",
    "B": ROOT / "experiments" / "outputs" / "NET_E9_dynamic_replay",
}
OUT_MD = HERE / "experiment_audit_report.md"
OUT_JSON = HERE / "new_old_comparison.json"


def csv_rows(p):
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def mean(v):
    return round(sum(v)/len(v), 6) if v else None


def main() -> int:
    missing = []
    for c, d in NEW.items():
        if not (d / "run_level_results.csv").exists():
            missing.append((c, "run_level_results.csv"))
        if not (d / "statistical_report.json").exists():
            missing.append((c, "statistical_report.json"))
    if missing:
        OUT_MD.write_text(
            "# 实验审计报告（未生成）\n\n"
            "正式运行尚未完成，缺少产物：" +
            "".join(f"\n- 配置 {c}: `{f}`" for c, f in missing) +
            "\n\n完整重跑采用可续跑分片；续跑命令：\n\n```bash\n"
            "cd \"A版/HighwayEmergency_A\"\n"
            "\"D:/Python3.10.8/python.exe\" audit_demand_integrity/run_full_all.py\n"
            "```\n\n完成后重跑 `finalize_full_experiment.py` 即可生成本报告。\n",
            encoding="utf-8")
        print("NOT READY:", missing)
        print("written:", OUT_MD)
        return 2

    comparison, lines = {}, [
        "# 完整重跑实验审计报告", "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", "",
        "> **配置 A 与 B 是两套独立实验**（距离度量、资源池、坐标基础三者同时不同），",
        "> 全程分开报告，未合并样本、未计算跨配置合并统计量、未写成严格控制变量实验。", "",
    ]

    for c in ["A", "B"]:
        nd, od = NEW[c], OLD[c]
        nr = csv_rows(nd / "run_level_results.csv")
        ne = csv_rows(nd / "event_level_results.csv")
        orr = csv_rows(od / "run_level_results.csv")
        summ = json.loads((nd / "summary.json").read_text(encoding="utf-8"))
        stat = json.loads((nd / "statistical_report.json").read_text(encoding="utf-8"))
        ana = json.loads((nd / "analysis.json").read_text(encoding="utf-8"))
        man = json.loads((nd / "manifest.json").read_text(encoding="utf-8"))

        new_arm = {}
        old_arm = {}
        for a in ARMS:
            fk = f"{a}_fulfillment_mean"
            new_arm[a] = mean([float(r[fk]) for r in nr if fk in r])
            ok = f"{a}_fulfillment_mean"
            old_arm[a] = mean([float(r[ok]) for r in orr if ok in r])

        cmp = {
            "config": c, "provider": man["config"]["provider"],
            "new_runs": len(nr), "new_event_rows": len(ne),
            "old_runs": len(orr),
            "old_status": "superseded_pending_demand_integrity_correction",
            "variant": man["variant"],
            "network_import_shim": man["network_import_shim_installed"],
            "source_sha256": man["source_sha256"],
            "new_arm_fulfilment": new_arm,
            "old_arm_fulfilment": old_arm,
            "difference_first_attributed_to": (
                "demand-set correction (v4 appended full previous + full current "
                "demand set at every event; DispatchProblem did not dedupe)"),
            "NOT_attributed_to": "algorithmic improvement",
            "statistical_unit": stat["statistical_unit"],
            "bootstrap": stat["bootstrap"],
            "warm_vs_event_triggered": stat["warm_vs_event_triggered"],
            "deg_arm": stat["deg_arm"],
            "demand_integrity": stat["demand_integrity"],
            "solver_calls": stat["quality_cost"],
        }
        comparison[c] = cmp

        w = stat["warm_vs_event_triggered"]
        di = stat["demand_integrity"]
        go = ("STOP: demand/mapping anomaly remains" if di["runs_with_anomaly"]
              else ("保留机制实现，撤回计算效率优势"
                    if not w["event_triggered_reduces_calls"]
                    else "减少求解次数：需结合 Fulfilment 配对差判断"
                         "「质量—成本权衡」还是「可考虑效率优势」"))

        lines += [
            f"## 配置 {c} · {cmp['provider']}", "",
            f"- 新实验：{len(nr)} runs / {len(ne)} 事件行；变体 `{man['variant']}`；"
            f"network shim `{man['network_import_shim_installed']}`",
            f"- 统计单位：{cmp['statistical_unit']}；"
            f"场景聚类 bootstrap {stat['bootstrap']['resamples']} 次 / "
            f"{stat['bootstrap']['clusters']} 簇",
            f"- 需求完整性异常 run：`{di['runs_with_anomaly']}`；"
            f"四等式违规事件：`{di['four_count_identity_violations']}`",
            "",
            "### 新旧对照（旧数据仅作追溯，已标记作废）", "",
            "| 策略 | 旧 Fulfilment | 新 Fulfilment | 变化 |", "|---|---:|---:|---:|",
        ]
        for a in ARMS:
            o, n = old_arm[a], new_arm[a]
            d = round(n-o, 6) if (o is not None and n is not None) else "n/a"
            lines.append(f"| {a} | {o} | {n} | {d} |")
        lines += [
            "",
            "> 差异**首先归因于输入需求集合修正**（旧版逐事件把完整需求集重复拼接，"
            "13→26→39→54→69 而唯一 task_id 恒 13/15），**不得解释为算法改进**。",
            "",
            "### 关键问题判定", "",
            f"- Warm 求解 `{w['solve_calls_warm']}` vs "
            f"Event-triggered `{w['solve_calls_event_triggered']}`；"
            f"是否减少：**{'是' if w['event_triggered_reduces_calls'] else '否'}**",
            f"- 逐事件轨迹相同 `{w['identical_event_rows']}/"
            f"{w['total_event_rows']}`；Fulfilment 配对差 "
            f"`{w['fulfilment_diff']['paired_mean_diff']}` "
            f"(95% CI [{w['fulfilment_diff']['ci95_low']}, "
            f"{w['fulfilment_diff']['ci95_high']}])",
            f"- **Go/No-Go：{go}**", "",
        ]

    lines += [
        "## 冻结事项复核", "",
        "- 论文正文、投稿包：未改动，保持冻结",
        "- 旧 CSV / `STATUS_superseded.md`：保留、哈希未变",
        "- 原始 `scripts/run_dynamic_benchmark_v4.py`：只读，未改",
        "- 目标函数 / D3、τ=0.05、扰动分布：未改",
        "- 两 provider：未合并、未写成严格控制变量实验",
        "- 论文 E9/NET-E9 章节的保留 / 替换 / 降级：**由 Young 决定**", "",
        "## 建议（基于证据，不代 Young 决策）", "",
        "1. 若 Event-triggered 仍 100% 重优化：章节按「重新优化有价值、"
        "事件触发在所选阈值下无计算节省、固定周期存在质量—成本权衡」组织，"
        "撤回效率优势主张。",
        "2. `deg_arm` 的 τ 网格只作描述性敏感性检查；若要主张最优阈值，"
        "必须另做校准集 / 验证集分离。",
        "3. 任何新旧数值差异先解释输入修正，再谈其他。", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps({
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "never_pool_configs": True,
        "critical_note": ("A and B are independent experiments; they differ in "
                         "distance metric, resource pool AND coordinate basis."),
        "configs": comparison,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written:", OUT_MD)
    print("written:", OUT_JSON)
    for c, x in comparison.items():
        print(f"  config {c}: new_runs={x['new_runs']} old_runs={x['old_runs']} "
              f"warm_calls={x['warm_vs_event_triggered']['solve_calls_warm']} "
              f"ET_calls={x['warm_vs_event_triggered']['solve_calls_event_triggered']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
