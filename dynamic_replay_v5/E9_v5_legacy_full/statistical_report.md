# 统计复算报告 · 配置 A (haversine) · full

- 生成 2026-11-13 11:07:27；runs 2240；场景簇 28；seeds 20；事件行 3820（**嵌套观测，非独立样本**）
- 场景聚类 bootstrap 20000 次；两配置分开报告，未合并

> Full 20-seed run. CIs are scenario-clustered; no event-level pseudo-replication.

## 各策略 run 级表现

| 策略 | Fulfilment | Unmet | Distance(km) | Stability | 求解调用 | 总耗时(s) |
|---|---:|---:|---:|---:|---:|---:|
| keep | 0.289455 | 8.643899 | 1028.495564 | 0.918594 | 0 | 0.0 |
| warm | 0.426109 | 7.010677 | 1567.721041 | 0.830421 | 3820 | 2470.274 |
| cold | 0.426109 | 7.010677 | 1567.680378 | 0.820015 | 3820 | 2468.3 |
| fixed_period | 0.332445 | 8.098772 | 1212.118443 | 0.893193 | 1020 | 655.991 |
| event_triggered | 0.426109 | 7.010677 | 1567.721041 | 0.830421 | 3820 | 2468.609 |

## 配对差与场景聚类 95% CI

| 对比 | 指标 | 配对均值差 | CI 下限 | CI 上限 | 不含 0 |
|---|---|---:|---:|---:|---|
| warm_minus_event_triggered | fulfillment_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_event_triggered | unmet_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_event_triggered | distance_km_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_event_triggered | stability_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_fixed_period | fulfillment_mean | 0.093663 | 0.080858 | 0.106635 | 是 |
| warm_minus_fixed_period | unmet_mean | -1.088095 | -1.174256 | -1.007589 | 是 |
| warm_minus_fixed_period | distance_km_mean | 355.602598 | 301.642727 | 413.336168 | 是 |
| warm_minus_fixed_period | stability_mean | -0.062772 | -0.067966 | -0.057364 | 是 |
| warm_minus_keep | fulfillment_mean | 0.136654 | 0.120292 | 0.153265 | 是 |
| warm_minus_keep | unmet_mean | -1.633222 | -1.755208 | -1.521577 | 是 |
| warm_minus_keep | distance_km_mean | 539.225476 | 454.971414 | 627.669302 | 是 |
| warm_minus_keep | stability_mean | -0.088173 | -0.095862 | -0.079942 | 是 |
| warm_minus_cold | fulfillment_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_cold | unmet_mean | 0.0 | 0.0 | 0.0 | 否 |
| warm_minus_cold | distance_km_mean | 0.040663 | -0.534147 | 0.722525 | 否 |
| warm_minus_cold | stability_mean | 0.010406 | 0.007931 | 0.012969 | 是 |
| event_triggered_minus_fixed_period | fulfillment_mean | 0.093663 | 0.081002 | 0.106834 | 是 |
| event_triggered_minus_fixed_period | unmet_mean | -1.088095 | -1.174368 | -1.007329 | 是 |
| event_triggered_minus_fixed_period | distance_km_mean | 355.602598 | 301.179293 | 412.184933 | 是 |
| event_triggered_minus_fixed_period | stability_mean | -0.062772 | -0.06791 | -0.057351 | 是 |
| event_triggered_minus_keep | fulfillment_mean | 0.136654 | 0.1202 | 0.153365 | 是 |
| event_triggered_minus_keep | unmet_mean | -1.633222 | -1.753013 | -1.523661 | 是 |
| event_triggered_minus_keep | distance_km_mean | 539.225476 | 455.060006 | 626.452376 | 是 |
| event_triggered_minus_keep | stability_mean | -0.088173 | -0.095762 | -0.08011 | 是 |

## 关键问题

- Warm 求解调用 `3820`、Event-triggered `3820`；是否减少：**否**
- 逐事件轨迹相同 `3820/3820`
- Warm − Event-triggered 的 Fulfilment 配对差：`0.0` (95% CI [0.0, 0.0])

## deg_arm 与阈值（描述性）

- 取值 3820 条，distinct 11，min/median/max = 0.117647/0.166667/0.5
