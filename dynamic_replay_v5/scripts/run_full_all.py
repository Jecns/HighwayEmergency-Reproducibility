# -*- coding: utf-8 -*-
"""
run_full_all.py
================
Resumable background driver for the 4480-run full experiment.

  config A: 28 scenarios x 4 profiles x 20 seeds = 2240 runs
  config B: 28 scenarios x 4 profiles x 20 seeds = 2240 runs
  56 shards total (1 scenario per shard -> ~80 runs / ~6-8 min each)

IDEMPOTENT / RESUMABLE: every shard writes its own JSONL.  Re-running this
driver skips any (scenario, seed, profile) already present.  If the session
ends and the background process is killed, just run this command again.

Progress is written to ``audit_demand_integrity/full_progress.json`` after
every shard, so the state is always inspectable without waiting for the process.

The two configs are NEVER merged.  No paper file is touched.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
DRIVER = HERE / "run_verified_replay.py"
PROGRESS = HERE / "full_progress.json"
SHARDS = 28
CONFIGS = ["A", "B"]
PHASE = "full"


def shard_done(config, index):
    root = "E9_v5_legacy" if config == "A" else "NET_E9_v5"
    p = ROOT / "experiments" / "outputs" / f"{root}_{PHASE}" \
        / "_shards" / f"shard_{index:02d}.jsonl"
    if not p.exists():
        return 0
    return sum(1 for l in p.read_text(encoding="utf-8").splitlines()
               if l.strip())


def run(cmd, label):
    print(f"[{time.strftime('%H:%M:%S')}] {label}", flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    tail = "\n".join((r.stdout or "").splitlines()[-4:])
    if r.returncode != 0:
        print(f"  !! exit={r.returncode}\n{r.stdout or ''}\n{r.stderr or ''}",
              flush=True)
    elif tail:
        print("  " + tail.replace("\n", "\n  "), flush=True)
    return r.returncode


def main() -> int:
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    state = json.loads(PROGRESS.read_text(encoding="utf-8")) \
        if PROGRESS.exists() else {}
    state.setdefault("started_at_local", started)
    state["shards"] = SHARDS
    state["phase"] = PHASE
    state.setdefault("completed_shards", [])
    state.setdefault("errors", [])
    state["last_update_local"] = started

    def save():
        PROGRESS.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    total = SHARDS * len(CONFIGS)
    for config in CONFIGS:
        for i in range(SHARDS):
            key = f"{config}:{i:02d}"
            n = shard_done(config, i)
            expected = 4 * 20  # 4 profiles x 20 seeds for one scenario
            if n >= expected:
                if key not in state["completed_shards"]:
                    state["completed_shards"].append(key)
                continue
            rc = run([PY, str(DRIVER), "--config", config,
                      "--phase", PHASE, "--shards", str(SHARDS),
                      "--shard-index", str(i)],
                     f"config {config} shard {i:02d}/{SHARDS} "
                     f"(resuming from {n}/{expected})")
            n2 = shard_done(config, i)
            state["last_update_local"] = time.strftime("%Y-%m-%d %H:%M:%S")
            state["current"] = {"config": config, "shard": i,
                                "rows": n2, "expected": expected}
            if rc != 0 or n2 < expected:
                state["errors"].append(
                    {"key": key, "exit": rc, "rows": n2,
                     "at": state["last_update_local"]})
                save()
                print(f"STOP: shard {key} incomplete ({n2}/{expected}). "
                      f"Re-run this driver to resume.", flush=True)
                return 2
            if key not in state["completed_shards"]:
                state["completed_shards"].append(key)
            state["done"] = len(state["completed_shards"])
            state["total"] = total
            state["pct"] = round(100*state["done"]/total, 2)
            save()

    # merge + statistics, per config only
    for config in CONFIGS:
        run([PY, str(DRIVER), "--config", config, "--phase", PHASE,
             "--shards", str(SHARDS), "--merge"],
            f"merge config {config}")
        run([PY, str(HERE / "analyze_verified_replay.py"),
             "--config", config, "--phase", PHASE, "--bootstrap", "20000"],
            f"statistics config {config}")

    state["status"] = "COMPLETE" if not state["errors"] else "COMPLETE_WITH_ERRORS"
    state["finished_at_local"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["done"] = len(state["completed_shards"])
    state["total"] = total
    state["pct"] = round(100*state["done"]/total, 2)
    save()
    print("FULL EXPERIMENT", state["status"], flush=True)
    return 0 if not state["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
