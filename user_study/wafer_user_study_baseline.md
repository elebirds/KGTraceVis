# Wafer User Study Baseline — Nearfull Record Case

- upload file: `user_study/wafer_user_study_records.jsonl`
- upload mode: `records`
- dataset: `wafer`
- case_id: `wafer_user_study_record_001`
- claim boundary: candidate/plausible explanation only; not a verified root-cause label

## 1. 给参与者看的 baseline 信息

### 已观测异常证据

- Wafer pattern: `Near-full`
- Canonical anomaly_type: `nearfull`
- Location: `wafer_surface`
- Morphology: `dense_particles`
- Supporting log event: `example_alarm`

### 不使用系统时的 baseline RCA 候选清单

参与者可以只看上面的证据，再参考下面的候选列表进行人工 RCA：

| Rank | Candidate | Why it is included |
| --- | --- | --- |
| 1 | `GlueRemovalInsufficient` | Local reviewed seed edge exists: `NearfullDefect -> GlueRemovalInsufficient` with confidence `0.78`. |
| 2 | `WetCleanResidue` | Wafer scenario edge exists: `NearfullDefect -> WetCleanResidue` with confidence `0.52`. |
| 3 | `ParticleContamination` | Wafer scenario edge exists: `NearfullDefect -> ParticleContamination` with confidence `0.60`. |
| 4 | `RinseFlowInsufficient` | Wafer scenario edge exists: `NearfullDefect -> RinseFlowInsufficient` with confidence `0.49`. |
| 5 | `WaterQualityExcursion` | Wafer scenario edge exists: `NearfullDefect -> WaterQualityExcursion` with confidence `0.46`. |

### 建议的 user study 对比方式

1. 让参与者先只看本文件，完成一次人工 RCA。 
2. 记录参与者的：
   - Top-1 选择
   - Top-3 候选
   - 用时
   - 自信度
3. 然后让参与者使用 RootLens 对同一案例做 RCA。 
4. 再比较：
   - 是否更快
   - 是否更稳定地选到参考候选
   - 是否更容易解释原因路径

## 2. 研究者评分参考（不要直接展示给参与者）

> 注意：下面这个“参考目标”是 **user study 的对照参考答案**，不是工业真值，也不是 verified root cause。

### 建议评分参考目标

- reference target: `GlueRemovalInsufficient`
- reference type: `plausible reference target`
- evidence basis: reviewed local edge `NearfullDefect -> GlueRemovalInsufficient`

### 推荐统计口径

- `Top-1 agreement with reference target`
- `Top-3 hit rate on reference target`
- `Decision time`
- `Self-reported confidence`
- `Explanation quality / path plausibility`（主观问卷）

## 3. 说明

- 这个 baseline 文件是为了比较“使用系统”和“未使用系统”的差异。
- 它不意味着存在已验证 wafer root-cause ground truth。
- 如果你要做正式论文表述，建议使用“agreement with study reference target”而不是“true RCA accuracy”。
