# 03 KGTracePipeline 推理机制与不足

## 当前实现概览

当前仓库已有可运行的 v0 `KGTracePipeline`。入口是：

```text
Evidence JSON
  -> KGTracePipeline.analyze(evidence)
  -> AnalysisResult
```

实际步骤如下：

1. `link_evidence_entities`：从 observations 和 legacy fields 中抽取 mentions，并链接到 KG 节点。
2. `check_consistency`：根据预定义字段关系检查 evidence 内部是否符合 KG 约束。
3. `generate_correction_candidates`：对未通过的字段关系，从 KG 邻域生成修正候选。
4. `rank_root_cause_paths`：从 linked anomaly/variable/log_event 节点出发，枚举到 root-cause/fault 类节点的路径并打分。

输出 `AnalysisResult` 包含：

```text
case_id
linked_entities
consistency_score
inconsistent_fields
correction_candidates
top_k_paths
human_feedback
```

这已经足够支撑组会 demo：输入不是静态结果，app 可以在 what-if 编辑后清空 stale analysis，再由 pipeline 重新计算 linking、consistency、corrections 和 candidate paths。

## Entity linking 机制

当前 linker 主要是 deterministic matching baseline（确定性匹配基线）。它从以下字段收集 mentions：

- observations 中 facet 属于 object、anomaly_type、location、morphology、variable、log_event 的条目。
- 如果某类 observation 不存在，则 fallback 到 top-level `object`、`anomaly_type`、`location`、`morphology`。
- 再 fallback 到 `raw_evidence.variables` 和 `raw_evidence.log_events`。

候选由 `KnowledgeGraph.candidates(...)` 返回，当前逻辑保留 top-k candidates、score、match_type、ambiguous 标记和 stable link_id。它会记录低置信或相近候选的 ambiguity，而不是悄悄强选。

从研究角度看，它仍然是 keyword/entity linking baseline，不是语义推理模型。它适合 v0 的优点是可解释、稳定、可复现；不足是对同义词、缩写、跨语言、长描述和上下文消歧能力有限。

## Consistency checking 机制

当前 consistency checker 使用字段对和 KG relation 规则：

| 字段对 | KG relation |
| --- | --- |
| anomaly_type -> morphology | HAS_MORPHOLOGY |
| anomaly_type -> location | OCCURS_ON / HAS_LOCATION |
| variable -> location | MEASURED_IN / BELONGS_TO_UNIT |
| anomaly_type -> log_event | ASSOCIATED_WITH_EVENT |

如果 linked source entity 和 target entity 之间没有匹配 relation，就把相关字段加入 `inconsistent_fields`。分数由 entity linking 覆盖率和 relation check pass rate 组合得到。

它的优点是能清楚展示“为什么不一致”；不足是规则集合仍较小，且主要检查 pairwise constraints（成对约束），还没有建模时序传播、因果强度、操作阶段、设备状态或多证据冲突。

## Correction candidate 机制

当某个 consistency check 失败时，correction generator 会从 source entity 的 KG outgoing edges 中找满足规则 relation 的目标节点，生成候选：

```text
candidate_id
source_field
target_field
original_value
suggested_entity_id
suggested_value
score
reason
supporting_edges
```

这保证候选有 stable ID 和 source edge provenance。当前它更像 KG neighborhood suggestion（图邻域建议），不是概率生成模型；它不会直接修改原 evidence，这一点符合 human feedback compatibility。

## Path ranking 机制

当前 `rank_root_cause_paths` 使用 NetworkX 枚举 simple paths，从 linked anomaly_type、variable、log_event 节点出发，目标是 label 属于 RootCause、CauseCategory、FaultType 或 ID 以 `Cause` 结尾的节点。

打分公式是：

```text
Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)
```

其中：

- `Conf(P)` 是路径边 confidence 的平均值。
- `EvidenceMatch(P)` 是路径节点与 linked evidence entity 的重叠比例。
- `Length(P)` 惩罚过长路径。

每条 path 输出 stable `path_id`、nodes、node_names、relations、score、confidence、evidence_match、supporting_evidence、source_edge_ids 和 source_edges。

这比 shortest path only 更适合论文叙事，但仍是 graph search + heuristic scoring baseline（图搜索加启发式评分基线），不能被说成已完成 causal discovery（因果发现）或真实工厂 RCA。

## 为什么当前仍是 baseline

当前 v0 可以称为 source-constrained KG reasoning baseline，但不应夸大为成熟智能 RCA 系统，原因包括：

- KG 很小，主要是 demo-scale CSV KG，不是 paper-grade industrial KG。
- Entity linking 主要依赖名称、别名和模糊匹配，尚未引入 embedding 或上下文消歧。
- Consistency rules 是预定义字段对，不覆盖复杂过程时序和多跳约束。
- Correction candidates 来自 KG 邻域，不做概率校准或多证据融合。
- Path ranking 是关系置信度、证据匹配和长度惩罚的线性组合，没有学习到的 relation weight。
- MVTec path 只能解释为 curated plausible/runtime candidates，不是 verified factory RCA。
- Wafer 缺少真实 process logs 和 RCA labels 时，只能做 traceability case study。

## 下一步升级方向

优先升级方向应服务论文可信度，而不是堆复杂模型：

1. **TEP 主量化**：补强 TEP variable-unit-fault-root-cause KG 和 reference 文件，做 top-k path hit、MRR 和 ablation。
2. **Noise/correction protocol**：固定 noise types、noise levels、random seed 和 clean reference，评估 consistency/correction robustness。
3. **Annotation taxonomy**：把 native ground truth、official fault type、literature-supported、manual plausible、llm_candidate、demo_synthetic 分清楚。
4. **Provenance sidecar**：在不破坏 v0 CSV loader 的前提下增加 source_id、source_type、annotation_type、extractor、created_by 等元数据。
5. **Linking 增强**：在 deterministic linker 后加入可选 embedding/LLM fallback，但必须记录 ambiguity 和 source。
6. **Relation weight ablation**：比较 relation-weighted ranking、shortest path only、without evidence match、without correction step。
7. **UI 证明 runtime**：what-if 编辑后重新运行 pipeline，展示 source edge provenance，避免看起来像静态 JSON 展示。

## 组会可用表述

> 当前 KGTracePipeline 已经把 evidence 输入、实体链接、一致性检查、修正候选和候选路径排序串起来，足够做一个可复现 v0 demo。但它本质上还是 deterministic entity linking + KG constraint checking + graph search ranking baseline。下一阶段要把强结论放在 TEP 和 noise/correction 量化上，把 MVTec 和 wafer 作为边界清楚的视觉/多模态 traceability case。
