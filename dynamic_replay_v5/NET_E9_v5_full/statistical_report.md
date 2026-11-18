# 统计复算报告 · 配置 B (network) · full

- 生成 2026-11-13 11:11:38；runs 2240；场景簇 28；seeds 20；事件行 3820（**嵌套观测，非独立样本**）
- 场景聚类 bootstrap 20000 次；两配置分开报告，未合并

> Full 20-seed run. CIs are scenario-clustered; no event-level pseudo-replication.

## 各策略 run 级表现

| 策略 | Fulfilment | Unmet | Distance(km) | Stability | 求解调用 | 总耗时(s) |
|---|---:|---:|---:|---:|---:|---:|
| keep | 0.222724 | 9.595685 | 647.537114 | 0.918594 | 0 | 0.0 |
| warm | 0.358191 | 7.944494 | 1295.142841 | 0.839765 | 3820 | 1760.498 |
| cold | 0.358191 | 7.944494 | 1295.478908 | 0.824378 | 3820 | 1767.853 |
| fixed_period | 0.269607 | 8.989174 | 878.318984 | 0.896298 | 1020 | 466.763 |
| event_triggered | 0.358191 | 7.944494 | 1295.142841 | 0.839765 | 3820 | 1760.824 |

## 配对差与场景聚类 95% CI

| 对比 | 指标 | 配对均值差 | CI 下限 | CI 上限 | 不含 0 |
|---|---|---:|---:|---:|---|
| warm_minus_event_triggered | fulfillment_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_event_triggered | unmet_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_event_triggered | distance_km_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_event_triggered | stability_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_fixed_period | fulfillment_mean | 0.088584 | 0.082306 | 0.094692 | 是 |
| warm_minus_fixed_period | unmet_mean | -1.04468 | -1.078609 | -1.008519 | 是 |
| warm_minus_fixed_period | distance_km_mean | 416.823857 | 336.165774 | 495.760797 | 是 |
| warm_minus_fixed_period | stability_mean | -0.056533 | -0.062441 | -0.051111 | 是 |
| warm_minus_keep | fulfillment_mean | 0.135467 | 0.127341 | 0.143705 | 是 |
| warm_minus_keep | unmet_mean | -1.65119 | -1.725893 | -1.567894 | 是 |
| warm_minus_keep | distance_km_mean | 647.605726 | 522.19395 | 774.114618 | 是 |
| warm_minus_keep | stability_mean | -0.078829 | -0.086856 | -0.071262 | 是 |
| warm_minus_cold | fulfillment_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_cold | unmet_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_cold | distance_km_mean | -0.336067 | -0.539492 | -0.133252 | 是 |
| warm_minus_cold | stability_mean | 0.015387 | 0.01218 | 0.018926 | 是 |
| event_triggered_minus_fixed_period | fulfillment_mean | 0.088584 | 0.082434 | 0.094758 | 是 |
| event_triggered_minus_fixed_period | unmet_mean | -1.04468 | -1.07872 | -1.008631 | 是 |
| event_triggered_minus_fixed_period | distance_km_mean | 416.823857 | 335.446851 | 495.261399 | 是 |
| event_triggered_minus_fixed_period | stability_mean | -0.056533 | -0.062335 | -0.051077 | 是 |
| event_triggered_minus_keep | fulfillment_mean | 0.135467 | 0.127301 | 0.143654 | 是 |
| event_triggered_minus_keep | unmet_mean | -1.65119 | -1.726339 | -1.56901 | 是 |
| event_triggered_minus_keep | distance_km_mean | 647.605726 | 522.323602 | 775.387759 | 是 |
| event_triggered_minus_keep | stability_mean | -0.078829 | -0.086831 | -0.071211 | 是 |

## 关键问题

- Warm 求解调用 `3820`、Event-triggered `3820`；是否减少：**否**
- 逐事件轨迹相同 `3820/3820`
- Warm − Event-triggered 的 Fulfilment 配对差：`0.0` (95% CI [0.0, 0.0])

## deg_arm 与阈值（描述性）

- 取值 3820 条，distinct 7，min/median/max = 0.117647/0.2/0.5
