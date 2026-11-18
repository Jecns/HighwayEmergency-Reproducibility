# -*- coding: utf-8 -*-
"""
mark_superseded.py
==================
Mark the archived E9 / NET-E9 dynamic-replay artefacts as

    superseded_pending_demand_integrity_correction

STRICTLY ADDITIVE: this script only CREATES one new STATUS file per directory
and one master record.  It NEVER modifies, deletes, renames or overwrites any
existing artefact.  sha256 of every pre-existing file is recorded so anyone
can verify that nothing was touched.

Re-running is idempotent (STATUS file is rewritten, artefacts are untouched).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_BASE = ROOT / "experiments" / "outputs"
STATUS = "superseded_pending_demand_integrity_correction"

TARGETS = [
    OUT_BASE / "E9_dynamic_replay_v3",
    OUT_BASE / "E9_dynamic_replay_v4",
    OUT_BASE / "NET_E9_dynamic_replay",
]

SIDECAR_NAME = "STATUS_superseded.md"
MASTER = HERE / "DATA_STATUS_20261112.md"


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def collect(d: Path):
    files = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name == SIDECAR_NAME:
            continue
        files.append({
            "rel": str(p.relative_to(d)).replace("\\", "/"),
            "bytes": p.stat().st_size,
            "sha256": digest(p),
        })
    return files


def main() -> int:
    master = {
        "status": STATUS,
        "marked_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "policy": ("KEEP everything. Do not delete, do not overwrite, do not "
                   "use as final paper evidence. Only a verified full new run "
                   "in a separate output directory may supersede these."),
        "root_cause": ("run_dynamic_benchmark_v4.py L329 + L356/L377 append the "
                       "FULL current demand set to the FULL previous demand set "
                       "at every event; DispatchProblem performs no dedup; "
                       "mapping functions key on task_id and silently overwrite "
                       "duplicates."),
        "affected_metrics": ["demand_fulfillment_rate", "unmet_demands",
                             "weighted_response_distance_km", "plan_stability",
                             "degradation", "trigger_rate",
                             "reoptimisation_rate", "reassignment_fraction",
                             "all paired contrasts derived from them"],
        "directories": [],
    }

    body = [
        "# 旧动态回放实验数据状态标记", "",
        f"- 状态字符串：`{STATUS}`",
        f"- 标记时间：{master['marked_at_local']}", "",
        "## 政策", "", master["policy"], "",
        "## 根因", "", master["root_cause"], "",
        "## 受影响的指标", "",
    ]
    body += [f"- `{m}`" for m in master["affected_metrics"]]
    body += ["", "## 目录与既有文件哈希（证明未修改）", ""]

    for d in TARGETS:
        if not d.is_dir():
            continue
        pre = collect(d)
        sc = d / SIDECAR_NAME
        sc.write_text(
            f"# STATUS: {STATUS}\n\n"
            f"- Marked: {master['marked_at_local']}\n"
            f"- Directory: `{d.name}`\n\n"
            "All files in this directory are **retained verbatim** but are "
            "**NOT valid final paper evidence**. The dynamic replay driver "
            "appended the full current demand set to the full previous demand "
            "set at every event (`run_dynamic_benchmark_v4.py` L329 + L356/L377), "
            "so demand lists grew 13 -> 26 -> 39 -> ... while unique task ids "
            "stayed 13/15; `DispatchProblem` does not deduplicate and mapping "
            "functions overwrite duplicate `task_id` keys.\n\n"
            "Fulfilment, unmet demand, distance, stability, degradation, "
            "trigger/reoptimisation rates and every paired contrast derived "
            "from them are affected. Six-gate checks do NOT detect this class "
            "of generator defect.\n\n"
            "A corrected independent variant lives at "
            "`audit_demand_integrity/run_dynamic_benchmark_v4_fixed.py`. "
            "Only a verified FULL new run in a separate output directory may "
            "replace these numbers in the manuscript. Until then the paper "
            "files stay frozen.\n\n"
            "This STATUS file is ADDITIVE: no pre-existing artefact was "
            "modified, renamed or deleted. See "
            "`audit_demand_integrity/DATA_STATUS_20261112.md` for hashes.\n",
            encoding="utf-8")
        after = collect(d)
        assert pre == after, f"artefacts changed while marking {d}"
        master["directories"].append({
            "directory": str(d.relative_to(ROOT)).replace("\\", "/"),
            "sidecar_added": SIDECAR_NAME,
            "n_existing_files": len(pre),
            "existing_files": pre,
            "unchanged_verified": True,
        })
        body += [f"### `{d.name}` — {len(pre)} 个既有文件（未修改）", "",
                 "| 文件 | bytes | sha256 |", "|---|---:|---|"]
        body += [f"| `{f['rel']}` | {f['bytes']} | `{f['sha256'][:16]}…` |"
                 for f in pre]
        body.append("")

    body += ["## 复现", "",
             "```bash\n"
             "cd HighwayEmergency_A\n"
             "D:/Python3.10.8/python.exe audit_demand_integrity/mark_superseded.py\n"
             "```\n",
             "## 结论边界", "",
             "- 方案 A 的**负面结果叙事**不依赖这些数值，不被直接推翻；",
             "- 但论文 E9 / NET-E9 章节与结论中引用动态数值的部分，"
             "必须在完整重跑并通过核验后重新定稿；",
             "- 旧实验的策略间配对结果**也不能直接保留**：五个策略都受同一"
             "输入缺陷影响，不等于相对比较自然有效。", ""]
    MASTER.write_text("\n".join(body), encoding="utf-8")
    (HERE / "DATA_STATUS_20261112.json").write_text(
        json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")

    print("status:", STATUS)
    for x in master["directories"]:
        print(f"  {x['directory']}: {x['n_existing_files']} existing files "
              f"unchanged=True  sidecar added")
    print("written:", MASTER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
