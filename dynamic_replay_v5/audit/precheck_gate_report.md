# 112 次预检：最终门禁报告

- 生成时间：2026-11-12 15:12:45
- **结论：PRECHECK PASSED -- full run may proceed**

> 两套配置**独立报告、不合并统计**（距离度量、资源池、坐标基础三者同时不同）。

## 七条通过条件

### 配置 A · haversine

- runs/events：112 / 191；运行错误 0
- 版本 `fixed_v2_full_diagnostics`；network shim=False；源码 SHA-256 清单 19 项

| 条件 | 结果 | 明细 |
|---|---|---|
| G1_112_runs_all_normal | ✅ PASS | runs=112, summary=112, errors=0 |
| G2_no_duplicate_task_ids | ✅ PASS | violating events=0 / 191 |
| G3_failure_closure_add_no_demand | ✅ PASS | violating events=0 |
| G4_surge_only_declared_new_demands | ✅ PASS | surge events=56, violating=0 |
| G5_five_arms_same_active_set | ✅ PASS | violating events=0 / 191 |
| G6_solver_bookkeeping_consistent | ✅ PASS | violating events=0 / 191 |
| G7_no_unexplained_mapping_overwrite | ✅ PASS | violating events=0 / 191 |
| X1_deg_arm_recorded_and_drives_reopt | ✅ PASS | violating events=0 / 191 |

### 配置 B · network

- runs/events：112 / 191；运行错误 0
- 版本 `fixed_v2_full_diagnostics`；network shim=True；源码 SHA-256 清单 19 项

| 条件 | 结果 | 明细 |
|---|---|---|
| G1_112_runs_all_normal | ✅ PASS | runs=112, summary=112, errors=0 |
| G2_no_duplicate_task_ids | ✅ PASS | violating events=0 / 191 |
| G3_failure_closure_add_no_demand | ✅ PASS | violating events=0 |
| G4_surge_only_declared_new_demands | ✅ PASS | surge events=56, violating=0 |
| G5_five_arms_same_active_set | ✅ PASS | violating events=0 / 191 |
| G6_solver_bookkeeping_consistent | ✅ PASS | violating events=0 / 191 |
| G7_no_unexplained_mapping_overwrite | ✅ PASS | violating events=0 / 191 |
| X1_deg_arm_recorded_and_drives_reopt | ✅ PASS | violating events=0 / 191 |

## 关键问题：正确需求集下，事件触发能否减少重优化成本而不损失满足率？

### 配置 A · haversine

- `event_triggered_degradation`（该臂 carried plan 的真实退化）共 191 条、**11 个不同取值**（min 0.117647 / median 0.166667 / max 0.5），τ=0.05 下超阈值比例 **100.0%**
- Warm 与 Event-triggered：逐事件轨迹相同 **191/191**，Fulfillment 最大绝对差 `0.0`；求解调用 Warm `191` vs Event-triggered `191`
- 质量—成本参照（run 级均值）：Warm fulfilment `0.427175` / Fixed-period `0.33066` （差 `0.096515`）；Fixed-period 求解调用 `51`

### 配置 B · network

- `event_triggered_degradation`（该臂 carried plan 的真实退化）共 191 条、**7 个不同取值**（min 0.117647 / median 0.2 / max 0.5），τ=0.05 下超阈值比例 **100.0%**
- Warm 与 Event-triggered：逐事件轨迹相同 **191/191**，Fulfillment 最大绝对差 `0.0`；求解调用 Warm `191` vs Event-triggered `191`
- 质量—成本参照（run 级均值）：Warm fulfilment `0.355916` / Fixed-period `0.268046` （差 `0.08787`）；Fixed-period 求解调用 `51`

## 结论（预检证据，1 seed；正式统计须待 20 seeds + 场景聚类 bootstrap）

- **在 τ=0.05（冻结值）下，两套配置的 Event-triggered 仍 100% 重优化**，
  与 Warm 轨迹逐行相同，**没有减少求解次数**，因此按 Go/No-Go 表应
  「保留机制实现，撤回计算效率优势」。
- 但 `deg_arm` 不再是旧数据的 0 / ≥0.333 两极分布，而是出现连续梯度；
  τ 网格显示提高阈值会抑制触发。这说明**机制本身具备区分能力**，
  限制来自所选阈值，而非触发条件失效。按冻结事项未改 τ、未做校准集/验证集分离，
  故本次只能作描述性陈述，不能主张最优阈值。
- 真正的质量—成本杠杆仍是 **Fixed-period 的重优化频次**；
  它减少求解调用但伴随满足率下降，属于质量—成本权衡。
- 若新结果与旧结果差异大，首先归因于**输入需求集合修正**，不得解释成算法改进。

## 边界

- 预检只用了 1 个固定种子；不能替代正式 20 seeds 的统计推断。
- 所有事件均为 run 内嵌套观测，未被当作独立样本。
- 两配置分开报告，未合并扩大样本量。
