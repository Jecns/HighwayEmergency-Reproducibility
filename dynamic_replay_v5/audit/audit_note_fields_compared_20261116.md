# 独立审计说明 · v5 `analysis.json` 的 `fields_compared` 字段命名

- 写入时间：2026-11-16（R1+ v3.1 注入执行期间，§3 H「既有产物保护」要求项）
- 性质：**审计说明**，不修改、不覆盖、不重新生成任何 `experiments/outputs/` 下的既有产物。

## 1. 问题

`{E9_v5_legacy_full, NET_E9_v5_full}/analysis.json`（时间戳 2026-11-13 11:03 / 11:07）
的 `warm_vs_event_triggered.fields_compared` 记录的是 **25 个候选列名**
（5 臂 × 5 指标：fulfillment / distance_km / unmet / stability / reopt），
而**实际逐事件比较的只有 5 个字段**：

- 四项数值型输出：`warm_fulfillment` / `warm_distance_km` / `warm_unmet` / `warm_stability`
  （各自与 `event_triggered_*` 对应项差 < 1e-9）；
- 一项重优化布尔标志：`warm_reopt == event_triggered_reopt`。

即「五项比较 = 四项数值输出 + 一项布尔标志」，**不含** assignment 数组与资源分配映射。
字段名 `fields_compared` 有误导性（会被读成 25 个字段都被比较）。
对应实现：`run_verified_replay.py` 原 L325–331（ident_cols 与 n_identical 表达式）。

## 2. 处置（符合 v3.1 §3 H 既有产物保护）

1. **既有两个 `analysis.json` 保持原样**：不覆盖、不改写、不重跑 `merge()`。
   `fields_compared` 在这两个文件中继续表示「25 个候选列」，其真实语义以本说明为准。
2. **生成器处置（2026-11-16 更新）**：为消除 manifest 源哈希不一致
   （GPT 独立核验发现的唯一待核项），`run_verified_replay.py` **已恢复为
   2026-11-13 manifest 冻结版**（SHA-256 `4b559f3e34bb39cf…`，与两配置
   `source_sha256` 记录精确一致）。命名改进（`candidate_columns` /
   `compared_fields`）保留在独立文件
   `run_verified_replay_renamedfields_20261116.py` 及
   `run_verified_replay_frozen_vs_renamedfields.diff`（15 增 / 3 删，
   全为注释与报告字段名，零计算逻辑差异），**仅在末来有意放弃哈希对齐时
   才可合入**。完整时间线与 20/20 哈希比对表见
   `provenance_verification_20261116.md`。
3. 论文中的对应表述（v3.1 §2.5 统一口径）：
   *"Within each setting, warm and event-triggered strategies matched on four
   event-level numerical outputs (fulfilment, weighted response distance, unmet
   demand and plan stability) and one re-optimisation indicator across all 3820
   event records per setting; assignment arrays and resource-allocation mappings
   were not compared."*

## 3. 校验记录

- 命名改进版仅通过语法编译检查（`py_compile`），**从未执行**，
  未产生任何新输出文件；现已从主脚本位置撤下（见上）。
- 既有 v5 产物 SHA 与时间戳未变（未触碰）。
- 主脚本恢复冻结版后已复核：SHA-256 与 manifest 一致，`py_compile` 通过。
