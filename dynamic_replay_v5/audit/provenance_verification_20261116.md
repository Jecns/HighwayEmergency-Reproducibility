# V5 来源追溯核验报告（回应 GPT "run_verified_replay.py 哈希不一致" 待核事项）

日期：2026-11-16
核验人：WorkBuddy（本地原始工作区）
结论：**全部 20 项 manifest 源哈希现已逐一比对通过；不一致项根因已查明并消除，实验产物零改动。**

## 1. 三方哈希比对结果

对 `E9_v5_legacy_full/manifest.json` 与 `NET_E9_v5_full/manifest.json` 记录的全部 20 项
`source_sha256`（两配置记录相同），逐一与本地当前文件比对：

| # | 文件 | 结果 |
|---|---|---|
| 1 | scripts/run_dynamic_benchmark_v4.py | MATCH |
| 2 | audit_demand_integrity/run_dynamic_benchmark_v4_fixed.py | MATCH |
| 3 | audit_demand_integrity/run_dynamic_benchmark_v5_verified.py | MATCH |
| 4 | audit_demand_integrity/build_verified_variant.py | MATCH |
| 5 | audit_demand_integrity/experiment_configs.json | MATCH |
| 6 | audit_demand_integrity/audit_demand_integrity.py | MATCH |
| 7 | **audit_demand_integrity/run_verified_replay.py** | **曾 DIFFER → 已恢复 MATCH** |
| 8 | src/pipeline/event_registry.py | MATCH |
| 9 | src/dispatch/problem.py | MATCH |
| 10 | src/dispatch/redispatch.py | MATCH |
| 11 | src/dispatch/nsga2.py | MATCH |
| 12 | src/dispatch/objectives.py | MATCH |
| 13 | src/dispatch/constraints.py | MATCH |
| 14 | src/road_network/router.py | MATCH |
| 15 | scripts/run_experiments.py | MATCH |
| 16 | scripts/run_net_experiments.py | MATCH |
| 17 | config/scenario_matrix.yaml | MATCH |
| 18 | config/demand_rules.yaml | MATCH |
| 19 | data/spatial/resource_event_route_matrix.parquet | MATCH |
| 20 | outputs（event/run CSV、summary、analysis）| 与 manifest `merge_result.outputs_sha256` 一致（2026-11-16 首包已验） |

## 2. 唯一不一致项的根因（时间线）

- **2026-11-13 11:11** 实验完成，`run_verified_replay.py` 当时的哈希
  `4b559f3e34bb39cf…` 写入两配置 manifest 的 `source_sha256`。
- **2026-11-16（R1 换数字注入期间）** 本地对该脚本做了一处**报告字段命名**修改
  （v3.1 预案 §3 H）：把 25 个候选列名从误导性的 `fields_compared` 拆分为
  `candidate_columns`（候选列）与 `compared_fields`（实际比较的 5 项）。
  该修改**只影响未来重跑时写出的新 analysis.json 的字段名**，
  不触碰任何计算逻辑、不动已冻结的 v5 产物。
  修改后哈希变为 `4962c840816ea286…`，遂与 manifest 不一致 —— 即 GPT 发现的差异。
- **2026-11-16（本次）** 已将本地 `run_verified_replay.py` **恢复为 manifest 记录的冻结版**
  （哈希 `4b559f3e34bb39cf07e4b3ac16c08478cc31053422043c60e2edca3c6010d605`，
  语法检查通过）；命名改进版本另存为
  `run_verified_replay_renamedfields_20261116.py`，其与冻结版的 unified diff 见
  `run_verified_replay_frozen_vs_renamedfields.diff`（15 增 / 3 删，全为注释与字段名）。

## 3. 冻结版来源

冻结版取自 `V5_experiment_materials_20261113.zip`（2026-11-13 实验收口当日打包，
先于 11-16 的任何脚本改动），其内附脚本哈希与 manifest 精确一致，可独立复核。

## 4. 对论文与实验结论的影响

零。该脚本在实验中的角色是"经验证的动态回放运行器"，其输出（CSV/报告）的哈希
与 manifest 自始至终一致；11-16 的改动从未运行、从未产出任何新实验文件。
