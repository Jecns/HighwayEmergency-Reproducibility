# 旧动态回放实验数据状态标记

- 状态字符串：`superseded_pending_demand_integrity_correction`
- 标记时间：2026-11-12 14:34:58

## 政策

KEEP everything. Do not delete, do not overwrite, do not use as final paper evidence. Only a verified full new run in a separate output directory may supersede these.

## 根因

run_dynamic_benchmark_v4.py L329 + L356/L377 append the FULL current demand set to the FULL previous demand set at every event; DispatchProblem performs no dedup; mapping functions key on task_id and silently overwrite duplicates.

## 受影响的指标

- `demand_fulfillment_rate`
- `unmet_demands`
- `weighted_response_distance_km`
- `plan_stability`
- `degradation`
- `trigger_rate`
- `reoptimisation_rate`
- `reassignment_fraction`
- `all paired contrasts derived from them`

## 目录与既有文件哈希（证明未修改）

### `E9_dynamic_replay_v3` — 4 个既有文件（未修改）

| 文件 | bytes | sha256 |
|---|---:|---|
| `analysis.json` | 58740 | `750939617271de76…` |
| `event_level_results.csv` | 670504 | `8d50c12f5b4281f8…` |
| `run_level_results.csv` | 257160 | `469a07f3efd9eb08…` |
| `summary.json` | 2093 | `f182283ce9787328…` |

### `E9_dynamic_replay_v4` — 11 个既有文件（未修改）

| 文件 | bytes | sha256 |
|---|---:|---|
| `_shards/shard_00.jsonl` | 1188052 | `c480aafb52c311eb…` |
| `_shards/shard_01.jsonl` | 1174443 | `86e67700b2a313d5…` |
| `_shards/shard_02.jsonl` | 1128412 | `16e31480e7b6ece6…` |
| `_shards/shard_03.jsonl` | 1054971 | `03b44b35fe6921b9…` |
| `_shards/shard_04.jsonl` | 943978 | `c03a2466dc201627…` |
| `_shards/shard_05.jsonl` | 943527 | `85d1931af100577b…` |
| `analysis.json` | 141577 | `4c7c1248e0342d6d…` |
| `clustered_analysis.json` | 15860 | `18ee34342390b2c2…` |
| `event_level_results.csv` | 1132494 | `a662a763d620bd37…` |
| `run_level_results.csv` | 827098 | `11869015151634bd…` |
| `summary.json` | 2174 | `b978df930b40750d…` |

### `NET_E9_dynamic_replay` — 11 个既有文件（未修改）

| 文件 | bytes | sha256 |
|---|---:|---|
| `_shards/shard_00.jsonl` | 1199545 | `3b6ce8b8a4999013…` |
| `_shards/shard_01.jsonl` | 1186795 | `a808a165982a65c5…` |
| `_shards/shard_02.jsonl` | 1142255 | `af8d406c003d4727…` |
| `_shards/shard_03.jsonl` | 1068665 | `1c9ba800e89d54ee…` |
| `_shards/shard_04.jsonl` | 957701 | `7f44c888f53ec4c4…` |
| `_shards/shard_05.jsonl` | 953352 | `e6f8441ef501e6fd…` |
| `analysis.json` | 141458 | `61299094345c13d3…` |
| `clustered_analysis.json` | 15603 | `11d09657e4f58115…` |
| `event_level_results.csv` | 1136460 | `41ac4058d8ff4aa9…` |
| `run_level_results.csv` | 830683 | `4a0363e4658b99ce…` |
| `summary.json` | 2356 | `acb91a385d1c78c2…` |

## 复现

```bash
cd HighwayEmergency_A
D:/Python3.10.8/python.exe audit_demand_integrity/mark_superseded.py
```

## 结论边界

- 方案 A 的**负面结果叙事**不依赖这些数值，不被直接推翻；
- 但论文 E9 / NET-E9 章节与结论中引用动态数值的部分，必须在完整重跑并通过核验后重新定稿；
- 旧实验的策略间配对结果**也不能直接保留**：五个策略都受同一输入缺陷影响，不等于相对比较自然有效。
