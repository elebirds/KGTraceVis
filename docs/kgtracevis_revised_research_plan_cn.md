# KGTraceVis 修订版研究与实现计划

状态：组会后研究路线草案，面向论文方案、demo 叙事和后续实现排期。

日期：2026-05-02。

本文将用户提供的 GPT Pro 讨论结论固化为 KGTraceVis 仓库可执行的中文计划。核心约束是：数据集 adapter 只产出观测到的异常 evidence；`KGTracePipeline` 在运行时计算 entity linking、一致性检查、修正候选和 candidate/plausible RCA paths；MVTec/DS-MVTec 不能被叙述为自带真实工厂 root-cause labels。

## 1. 修订后的论文定位

推荐将论文定位为：

> KGTraceVis: Source-Constrained Knowledge Graph Reasoning over Unified Industrial Anomaly Evidence for Explainable Traceability

中文叙述可写为：

> KGTraceVis 不是新的异常检测模型，而是一个面向工业异常输出的知识约束 evidence analysis 与 traceability pipeline。系统将图像、时间序列和日志异常输出转换为统一的 anomaly evidence JSON，再通过 source-constrained、task-oriented KG 执行可解释的实体链接、一致性检查、噪声 evidence 修正和候选根因路径排序，并在可视分析界面中暴露 provenance 与人工反馈入口。

最稳妥的研究问题：

- RQ1：不同形态的异常检测输出能否被规范化为统一、可验证、可追溯的 evidence item？
- RQ2：source-constrained KG 能否帮助发现 evidence 字段冲突并生成可解释的修正候选？
- RQ3：relation-weighted KG path ranking 能否在有合适 reference 的场景中提高候选 RCA/path 命中表现？
- RQ4：将 source edge provenance 和 human feedback hooks 暴露给界面，能否减少系统看起来像静态展示的问题，并支持专家审阅？

需要避免的强声明：

- 不声称系统自动发现真实工业根因。
- 不声称 MVTec/DS-MVTec 原生提供 factory RCA ground truth。
- 不把人工 plausible reference 当成 verified ground truth。
- 不把 adapter 输出的字段包装成 pipeline 推理结果。

## 2. 数据集角色分工

| 数据集 | 推荐角色 | 可评估内容 | 不应声称 |
| --- | --- | --- | --- |
| MVTec / DS-MVTec | 视觉异常 evidence normalization、morphology/location consistency、噪声修正和可解释 candidate path demo | schema validity、entity linking、字段一致性、morphology/location correction、against curated plausible references 的 path hit | 原生真实工厂 RCA、verified process root cause |
| TEP | 主 RCA/path ranking 量化场景 | variable-unit-fault-root-cause linking、top-k path hit、MRR、relation-weighted ranking ablation | 真实工厂生产事故；应说明是经典仿真 benchmark |
| Wafer | 多模态 image/log/process case study 与 demo 场景 | image/log evidence consistency、source edge provenance、case-level path plausibility、专家反馈或人工审阅记录 | 在缺少可靠标签时做大规模 RCA accuracy claim |

论文主线建议：

- MVTec 负责展示视觉 evidence 如何进入统一 schema，并证明 KG constraints 能发现形态/位置冲突。
- TEP 负责承担最清晰的 RCA/path ranking 量化。
- Wafer 负责展示 image + log + process context 的可视分析价值。

## 3. Evidence Item 合同与 Schema 方向

统一 evidence item 是系统的输入合同。所有 adapter 输出必须兼容同一个 schema，不创建 dataset-specific 顶层 schema。

必需顶层字段继续保持：

```text
case_id
dataset
source
object
anomaly_type
location
morphology
severity
confidence
timestamp
raw_evidence
normalized_evidence
kg_analysis
```

字段边界：

- `observations`：KG reasoning 的唯一 canonical observed-evidence contract。adapter/manual annotation 应为 object、anomaly_type、location、morphology、variable、log_event 等可推理 facet 生成稳定 observation item。
- `raw_evidence`：保存 dataset-specific 内容，例如 image region、mask/heatmap path、variables、variable_contributions、log_events、caption、source row、extra metadata。
- `normalized_evidence`：保存 pipeline 运行后的规范化字段或 what-if 后的候选规范化结果；初始可以为空。
- `kg_analysis`：由 `KGTracePipeline` 运行时填充；adapter/manual annotation 不应预置 top-k paths 或 root cause answer。
- `human_feedback`：可选；记录 correction、path、entity linking、KG edge 的审阅结果。

边界：顶层字段只描述 evidence envelope 和展示元数据，不作为 KG reasoning 输入合同。
`raw_evidence` 只保存源数据、模型输出和 provenance。新
adapter、example 和评估输入必须以 `observations` 为准。

建议补充的 evidence metadata：

```text
annotation_type: native_ground_truth | official_fault_type | literature_supported | manual_plausible | llm_candidate | demo_synthetic
reference_scope: input_evidence | evaluation_reference | kg_edge_evidence
evidence_role: observed_anomaly | reference_label | candidate_explanation
```

这些字段不一定马上进入 Pydantic 必填项，但应先在 docs、example metadata 或 `raw_evidence.extra` 中保持一致命名。

## 4. Adapter 合同

Adapter 的职责是数据转换，不是根因推理。

输入：

- 原始异常检测输出、数据集记录、人工 demo annotation 或批处理 CSV/JSON/JSONL。
- 可选的 caption、mask、变量贡献、log event 和时间戳。

输出：

- 一个通过 Pydantic schema 校验的 `Evidence`。
- `kg_analysis` 初始为空对象或空分析占位。
- 不包含 root-cause label 作为预测答案。

禁止：

- 在 adapter 中写入 `top_k_paths`、`root_cause`、`ranked_causes` 等运行时推理结果。
- 将 MVTec 人工 plausible RCA 作为输入字段传给 pipeline。
- 在 adapter 里复制 entity linking、consistency checking、path ranking 逻辑。

可允许：

- 在 `raw_evidence.extra` 中记录用于追溯输入来源的 dataset row、mask path、caption id、manual annotation id。
- 在 evaluation-only reference 文件中记录 reference root cause 或 plausible path target，但该文件不作为 adapter 输出的一部分。

可放入论文 method 的表述：

> Dataset adapters only convert raw detector outputs or curated case records into observed anomaly evidence. They do not emit root causes. The `kg_analysis` field is intentionally empty at ingestion time and is populated only after `KGTracePipeline.analyze(...)` performs entity linking, evidence consistency checking, correction candidate generation, and candidate RCA path ranking.

## 5. Annotation Taxonomy

| 类型 | 含义 | 可否用于主评估 | 推荐 confidence | review_status |
| --- | --- | --- | --- | --- |
| `native_ground_truth` | 数据集原生提供的标签，例如明确 fault id 或 mask | 可以，前提是任务定义匹配 | 0.90-1.00 | `reviewed` |
| `official_fault_type` | 官方文档或 benchmark 定义的 fault type | 可以用于 fault-level 评估 | 0.80-0.95 | `reviewed` |
| `literature_supported` | 论文、技术报告或公开资料支持的 cause/path | 可用于辅助评估或 case study | 0.70-0.90 | `reviewed` 或 `auto` |
| `manual_plausible` | 项目人工整理的合理参考，不是事实标签 | 只用于 demo 或明确标注的 plausible-reference 评估 | 0.55-0.80 | `auto`，人工确认后 `reviewed` |
| `llm_candidate` | LLM 从提供 source 中抽取的候选三元组 | 不直接用于主评估；需人工审阅 | 0.30-0.65 | `auto` |
| `demo_synthetic` | 为展示冲突、噪声或 UI 而构造的样例 | 仅用于 demo/smoke | 0.30-0.70 | `auto` |

Reference 文件建议字段：

```csv
case_id,dataset,reference_id,annotation_type,target_node,target_relation,
source,evidence,confidence,review_status,notes
```

当前仓库已将 v0 reference 边界材料放在 `data/references/`。这些文件不作为
adapter 输入，也不会预填 `kg_analysis`；它们用于记录 demo/evaluation reference
的可信度边界，帮助区分 observed evidence、KG source edge 和 evaluation reference。

评估边界：

- 主表只使用 `native_ground_truth`、`official_fault_type` 和清楚说明过的 `literature_supported`。
- `manual_plausible` 可以计算 path hit/MRR，但表头必须写成 "against curated plausible references"。
- `llm_candidate` 不应作为 ground truth；只能作为 KG construction 候选或人工审阅队列。

## 6. KG Schema 与 Provenance 升级

当前 v0 节点 schema 保持：

```csv
id,name,label,scenario,aliases,description
```

当前 v0 边 schema 保持：

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,
feedback_count,accepted_count,rejected_count
```

短期不建议强行扩展所有 CSV 列，以免破坏已有 loader、QA 和 demo。更稳妥的升级路径：

1. v0 主 CSV 保持兼容。
2. 新增可选 provenance/reference 文件或 sidecar metadata。
3. 需要进入 paper-grade KG 时，再把经过验证的字段迁入主 schema。

建议优先增加的 provenance 字段：

| 字段 | 用途 | 推荐落点 |
| --- | --- | --- |
| `source_id` | 连接 `data/kg/source_registry.csv` 或 `docs/sources/` | sidecar 或未来 edge column |
| `source_type` | official_table、dataset_label、paper、manual_note、llm_extraction 等 | sidecar 或 future edge column |
| `extractor` | manual、script、llm_model_name、rule_name | sidecar |
| `annotation_type` | 对应上一节 taxonomy | reference file 或 sidecar |
| `created_by` | 区分 human、script、llm | sidecar |
| `last_reviewed_at` | 人工审阅时间 | sidecar |
| `reviewer` | 审阅者或角色 | sidecar |

覆盖规则：

- `review_status=reviewed` 的 edge 不得被自动抽取结果覆盖。
- `review_status=rejected` 的 edge 不应进入默认 KG reasoning。
- `confidence` 在 `[0, 1]`，`weight` 默认 `1 - confidence`，除非后续明确引入 relation-specific weight。
- feedback counters 保持非负整数，不把轻量 confidence update 描述成复杂 online learning。

## 7. Source-Constrained KG Construction Workflow

推荐工作流：

1. Source collection
   - 收集 dataset 文档、官方表、论文、技术报告、SOP 摘要、项目人工 note。
   - 在 `data/kg/source_registry.csv` 或 `docs/sources/` 记录 source id、URL、摘要、适用 scenario 和使用限制。

2. Candidate extraction
   - 手工或 LLM 从已登记来源中抽取 candidate entities/triples。
   - LLM 只能从提供文本中抽取，不允许补充外部常识作为事实。
   - 输出必须包含 `head`、`relation`、`tail`、`scenario`、`source`、`evidence`、`confidence`、`review_status`。

3. Confidence assignment
   - dataset label / official table：高 confidence。
   - 论文或技术报告明确语句：中高 confidence。
   - 项目人工 plausible mapping：中等 confidence。
   - LLM extraction from text：中低 confidence。
   - common industrial heuristic：低 confidence。

4. Cleaning and deduplication
   - 节点按 id、alias、normalized lowercase name 去重。
   - 边按 `(head, relation, tail, scenario)` 去重。
   - 冲突边进入 review queue，不静默覆盖。

5. QA
   - required columns。
   - missing node refs。
   - invalid confidence/weight。
   - invalid review_status。
   - duplicate edges。
   - isolated nodes warning。
   - feedback counters。

6. Review and import
   - 人工审阅后将关键边标为 `reviewed`。
   - 默认 demo 使用 in-memory KG CSV。
   - Neo4j import 作为可选后端，不改变 reasoning contract。

## 8. Runtime KGTracePipeline 逻辑

运行时入口保持：

```text
Evidence JSON
-> KGTracePipeline.analyze(evidence)
-> AnalysisResult
```

推荐步骤：

1. Validate evidence schema。
2. Link evidence entities：
   - exact ID。
   - exact name。
   - alias。
   - fuzzy。
   - embedding/LLM fallback 仅作为未来选项。
3. Check consistency：
   - `anomaly_type` vs `morphology`。
   - `anomaly_type` vs `location`。
   - `variable` vs `process_unit`。
   - `log_event` vs `fault_event`。
   - `fault_event` vs `root_cause`。
4. Generate correction candidates：
   - 每个候选要有 stable `candidate_id`。
   - 保留 source edge 和 supporting evidence。
   - 不直接修改原始 evidence。
5. Rank candidate/plausible RCA paths：
   - 使用 relation-weighted score，而不是只取 shortest path。

Path score 保持：

```text
Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)
```

输出 path 必须包含：

```text
path_id
nodes
relations
score
supporting_evidence
source_edges
reference_scope
```

叙事边界：

- 对 TEP：可以说 path ranking 对 fault/root-cause reference 做候选排序。
- 对 MVTec：只能说基于 observed visual anomaly evidence 和 curated plausible references 计算 candidate explanations。
- 对 Wafer：优先说 multimodal traceability 和 source-provenance case study。

## 9. Evaluation Plan

主表建议：

| 任务 | 指标 | 适用数据 |
| --- | --- | --- |
| Schema validation | schema validity rate | all |
| Entity linking | top-1 / top-k linking accuracy | curated cases with entity refs |
| Consistency checking | precision / recall / F1 | injected noise or reviewed conflicts |
| Correction | top-1 / top-k correction accuracy | noisy evidence with clean reference |
| RCA path ranking | top-k path hit, MRR | TEP; MVTec only if labeled plausible-reference |

辅助表或 appendix：

- KG QA issue counts。
- path length distribution。
- confidence bucket analysis。
- feedback action counts。
- case-level qualitative screenshots。

可执行 ablation：

- `relation-weighted ranking` vs `shortest path only`。
- without `EvidenceMatch(P)`。
- without correction step。
- clean vs noisy evidence。
- reviewed-only KG vs auto+reviewed KG。

不建议当前承诺：

- manual KG vs LLM-extracted KG 的大规模定量比较，除非有足够 source 和 review 预算。
- MVTec true factory RCA accuracy。
- wafer large-scale RCA accuracy，除非补齐可靠 labels。

结果表述模板：

> For MVTec-style visual anomalies, KGTraceVis evaluates evidence normalization, consistency checking, and correction under curated plausible references. We do not treat MVTec as a verified factory RCA benchmark. For quantitative RCA path ranking, TEP is used as the primary benchmark because fault labels and process variables can be mapped more directly to process units and candidate causes.

## 10. Noise Protocol

通用原则：

- 噪声是 field-level、deterministic、可复现。
- 每个 noisy item 保存 `is_noisy`、`noise_level`、`corrupted_fields`、`clean_reference`。
- 每个 experiment 保存 seed、输入路径、KG 版本、脚本命令和输出摘要。

建议 noise levels：

| level | 定义 |
| --- | --- |
| 0.0 | clean evidence |
| 0.1 | 单字段轻微扰动 |
| 0.3 | 1-2 个关键字段扰动 |
| 0.5 | 多字段扰动，仍保留足够上下文 |

Dataset-specific protocol：

- MVTec：`anomaly_type replacement`、`location replacement`、`morphology replacement`、`synonym substitution`、`contradiction injection`。重点观察 consistency recall 和 correction top-k。
- TEP：`variable deletion`、`variable name perturbation`、`fault/event mismatch`。重点观察 linking top-k、path hit 和 MRR 降幅。
- Wafer：`log event deletion`、`location replacement`、`contradiction injection`。重点观察 multimodal consistency 和 source provenance 是否能解释冲突。

报告格式：

```text
dataset,case_count,noise_type,noise_level,seed,
schema_validity,linking_top1,linking_topk,
inconsistency_precision,inconsistency_recall,
correction_top1,correction_topk,
path_hit_topk,mrr,notes
```

## 11. Demo Script

现场演示目标：证明 demo 是 runtime pipeline，不是静态 JSON 展示。

推荐脚本：

1. 打开 FastAPI backend
   - 命令：`uv run python scripts/run_web_api.py`。
   - 先说明 v0 backend 使用手工整理 example evidence 和小型 CSV KG，不是 paper-grade experiment。Legacy Streamlit/React demos 已移除，RootLens dashboard 后续重建。

2. MVTec clean case
   - 展示输入 JSON 只有 observed visual evidence。
   - 指出 `kg_analysis` 初始为空。
   - 运行 pipeline，展示 linked entities、consistency score、candidate RCA paths 和 source edges。
   - 口径：candidate paths are runtime plausible explanations, not MVTec native factory RCA.

3. MVTec noisy morphology case
   - 展示 morphology 被故意设错。
   - 运行后看 inconsistent fields。
   - 展示 correction candidate 和 supporting KG edge。
   - what-if 修改字段后重新运行，观察 stale analysis 被清空并重算。

4. TEP case
   - 展示 variables / variable_contributions。
   - 展示 variable -> process unit -> fault/root-cause candidate path。
   - 强调这是更适合 RCA path ranking 量化的场景。

5. Wafer case
   - 展示 image/log multimodal evidence。
   - 展示 log event、location、process provenance。
   - 说明缺少可靠标签时以 case study 和 expert review 为主。

6. Reproducibility backup
   - `uv run python scripts/run_examples.py`
   - `uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json`
   - `uv run python scripts/run_path_ranking.py`
   - `uv run python scripts/run_noise_experiment.py`
   - `uv run python scripts/run_experiment_suite.py`

## 12. Method Section Outline

建议论文方法章节：

1. Problem Definition
   - industrial anomaly evidence。
   - traceability graph。
   - candidate RCA path，不等于最终事实。

2. Unified Anomaly Evidence Schema
   - top-level fields。
   - raw vs normalized evidence。
   - adapter boundary。

3. Source-Constrained KG Construction
   - source registry。
   - candidate extraction。
   - confidence assignment。
   - manual review。
   - QA and provenance。

4. Evidence Entity Linking
   - deterministic matching order。
   - ambiguity recording。

5. KG-Based Consistency Checking and Correction
   - relation constraints。
   - correction candidate IDs。
   - source edge support。

6. Relation-Weighted RCA Path Ranking
   - scoring formula。
   - path provenance。
   - dataset-specific interpretation。

7. Visual Analytics and Feedback
   - evidence review。
   - what-if editing。
   - provenance panels。
   - feedback-compatible IDs。

8. Experimental Protocol
   - dataset roles。
   - annotation taxonomy。
   - noise injection。
   - metrics and ablations。

## 13. System Figures

建议至少准备四张图：

1. Overall Architecture Figure
   - detector/adapters -> unified evidence JSON -> source-constrained KG -> KGTracePipeline -> visual analytics/feedback。

2. Adapter Boundary Figure
   - 左侧 raw records。
   - 中间 adapters output observed evidence only。
   - 右侧 runtime KG analysis。
   - 用红色标注 root cause 不进入 adapter 输出。

3. KG Construction Workflow Figure
   - source registry -> LLM/manual extraction -> validation -> confidence assignment -> review -> QA -> CSV/Neo4j import。

4. Runtime Reasoning Flow Figure
   - linking -> consistency -> correction -> path ranking -> provenance display。

可选图：

- Noise experiment flow。
- Future RootLens dashboard screenshot montage。
- Annotation taxonomy table。

## 14. Implementation Backlog

必须做：

- 确保 example evidence 的 `kg_analysis` 初始为空，adapter 不输出 root cause。
- 在 README/demo notes 中统一 MVTec 边界：curated plausible references, not verified factory RCA。
- 保持 `KGTracePipeline` 为 scripts 和 service 的唯一 reasoning 入口。
- 保证 path 和 correction 输出有 stable IDs 和 source edge provenance。
- 运行 `scripts/run_examples.py`、`scripts/run_kg_qa.py`、`scripts/run_path_ranking.py` 作为 demo backup。

应该做：

- 补充 `annotation_type` / `reference_scope` 的文档和 reference CSV。
- 扩展 `source_registry.csv`，把 MVTec、TEP、wafer 的 source URL 和摘要登记清楚。
- 建立 TEP 小型变量-单元-fault-root-cause mapping，作为主 RCA evaluation 起点。
- 将 noise experiment 输出整理成 paper-ready table 模板。
- 为 KG QA 输出加 summary table，便于组会和论文 appendix。

可延后：

- 大规模 LLM extraction + manual review benchmark。
- Neo4j 后端性能对比。
- 嵌入式 entity linking fallback。
- 复杂 human feedback confidence learning。
- wafer 大规模 RCA 定量评估。

## 15. 最终叙事

最终对外叙事应保持克制但完整：

> KGTraceVis addresses the gap between heterogeneous anomaly detector outputs and explainable industrial traceability. Instead of assuming verified root causes are always available, it converts observations into a unified evidence schema, constrains reasoning with a source-traceable task KG, detects inconsistent evidence, proposes auditable corrections, and ranks candidate RCA paths with provenance. In MVTec-style visual anomalies, the system demonstrates evidence normalization and plausible explanation under curated references; in TEP, it supports more direct quantitative path-ranking evaluation; in wafer cases, it demonstrates multimodal evidence traceability and review.

中文版本：

> KGTraceVis 解决的不是“再训练一个异常检测模型”，而是异常检测之后的证据组织、知识约束推理和可追溯审阅问题。系统把图像、时间序列和日志异常输出转成统一 evidence，经由 source-constrained KG 在运行时完成链接、一致性检查、修正候选和候选 RCA 路径排序。MVTec 只承担视觉 evidence 与 plausible explanation 角色，TEP 承担更自然的 RCA/path ranking 量化，wafer 承担多模态 traceability case study。

## 16. References

- MVTec AD official download documentation: <https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads?cHash=a79aa4ef833d7bfed981e2fba6342c8f&gad_source=1>
- MVTec AD paper: <https://link.springer.com/article/10.1007/s11263-020-01400-4>
- Defect Spectrum arXiv paper: <https://arxiv.org/abs/2310.17316>
- Defect Spectrum Hugging Face dataset page: <https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum>
- Tennessee Eastman process original reference: <https://users.abo.fi/~khaggblo/RS/Downs.pdf>
- Extended Tennessee Eastman dataset paper: <https://www.sciencedirect.com/science/article/pii/S0098135421000594>
- Knowledge Graphs in Manufacturing and Production survey: <https://arxiv.org/abs/2012.09049>
- Industrial RCA using Knowledge Graphs: <https://www.sciencedirect.com/science/article/pii/S1877050922003015>
- Interactive RCA with Bayesian Networks and Knowledge Graphs: <https://arxiv.org/abs/2402.00043>
- PIXAL anomaly reasoning visual analytics: <https://arxiv.org/abs/2205.11004>
