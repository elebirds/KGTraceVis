# KGTraceVis 给 GPT Pro 的讨论简报

本文档用于和 GPT Pro 讨论 KGTraceVis 的论文方案、系统架构与下一步实现路线。目标是让 GPT Pro 在不依赖本地上下文的情况下，能够理解当前想法、已有仓库状态、关键概念问题，并进一步调研和提出一套可完成的 paper/demo 方案。

## 1. 当前论文与系统想法

KGTraceVis 是一个面向工业异常检测和根因可追溯的研究原型。核心想法不是再训练一个大型异常检测模型，而是把来自不同数据形态的异常输出转换成统一的 anomaly evidence JSON，然后借助一个 source-constrained、task-oriented 的工业知识图谱完成：

- entity linking：把 evidence 中的异常类型、位置、形态、变量、日志事件等观测证据链接到 KG 节点。
- evidence consistency scoring：检查 evidence 字段和 KG 约束是否一致。
- noisy evidence correction：在 evidence 有噪声或字段冲突时，生成可解释的修正候选。
- relation-weighted root-cause path ranking：从观测异常实体出发，在 KG 中计算候选/合理的 RCA 路径。
- visual analytics：在轻量 demo 中展示 raw evidence、normalized evidence、linked entities、consistency、correction candidates、top-k paths 和 source edge provenance。
- optional human feedback：保留 correction/path/entity/KG edge 的反馈入口与稳定 ID，便于后续 human-in-the-loop 扩展。

当前设想里的 KG 不是一个巨大的通用工业 KG，而是围绕三个 demo/use case 构建的小型任务图谱：

- `mvtec`：视觉缺陷场景，用 MVTec 风格缺陷作为视觉异常 evidence。这里尤其要谨慎：MVTec 不天然提供真实工厂 root-cause labels，不能声称 MVTec 有 verified factory RCA。最多只能使用人工整理的 plausible references，用于展示 KGTracePipeline 如何基于 observed visual anomaly evidence 计算 candidate/plausible RCA paths。
- `tep`：Tennessee Eastman Process 风格的过程变量异常场景，更适合展示变量、过程单元、fault/root-cause 的关系。
- `wafer`：晶圆图像/日志混合异常场景，用于展示 image/log multimodal evidence、工艺位置和报警/事件之间的 KG 约束。

论文要强调的贡献应当是“把多源异常输出统一为可追溯 evidence，并用 source-constrained KG 做可解释的一致性检查、噪声修正和候选 RCA 路径排序”，而不是声称系统已经拥有真实工业根因标签或完整工业知识。

## 2. 用户的四阶段方案（需原样纳入后续设计）

用户当前明确提出的系统路线是四个阶段：

1. 数据集准备与 root-cause annotation

   为每个数据集准备 demo/paper 所需的样本。样本需要包含可进入统一 schema 的观测异常字段，例如 object、anomaly_type、location、morphology、variables、variable_contributions、log_events、timestamp 等。对于 root-cause，要区分数据集原生提供的 ground truth、论文/官方文档中可支撑的 fault labels、以及为了 demo 人工整理的 plausible RCA labels。尤其 MVTec 不能被说成天然有真实工厂 RCA，只能标注为 manual plausible RCA/reference，用于评估或展示候选路径是否命中人工参考。

2. Source-constrained semi-automatic KG construction

   通过 manual/AI document collection 收集来源文档、表格、数据集说明、已有论文/说明文字等，再用 LLM 进行 candidate triple extraction。LLM 只能作为 adapter，不是 authority。抽取出的 triples 必须带 evidence fields，包括 `source`、`evidence`、`confidence`、`review_status`，并且 KG edges 还要保留 feedback counters。然后做 simple QA：schema 列检查、节点/边引用检查、confidence/weight 检查、review_status 检查、重复项检查、孤立节点 warning 等。低置信或自动抽取内容必须保持可审阅状态，不能直接当工业真值。

3. Dataset-specific adapters 生成 unified JSON

   每个数据集有自己的 adapter，把原始记录转换成统一 anomaly evidence JSON。关键边界是：adapters produce observed anomaly evidence, not root cause。adapter/manual demo annotation 应该只产出被观测到或由异常检测模型输出的 evidence，如 anomaly_type、location、morphology、variables、log_events、raw_evidence 等。adapter 不应把 root cause 写成输入答案，也不应预先塞入 top-k paths。`normalized_evidence` 和 `kg_analysis` 应该由后续 KG pipeline 在运行时生成或填充。

4. KG-based RCA over unified JSON

   `KGTracePipeline` 读取 unified JSON 后，在运行时完成 entity linking、consistency checking、correction candidate generation 和 candidate/plausible RCA path ranking。也就是说，KGTracePipeline computes candidate/plausible RCA paths at runtime，而不是读取 adapter 预置的 root-cause 字段。输出应包括 stable correction IDs、stable path IDs、node/relation sequence、score、supporting evidence 和 source edges，便于 visual analytics 和 human feedback。

## 3. 当前概念问题

当前方案最需要澄清的不是代码细节，而是研究叙事和系统边界：

1. Adapter-vs-KG boundary 仍然容易混淆

   现在必须明确：adapter 的职责是把各数据集输出转换成 observed anomaly evidence；KG pipeline 的职责是从 observed evidence 推理出 consistency、correction candidates 和 candidate/plausible RCA paths。若 adapter 输入已经包含 root cause，demo 会变成“把答案包装后展示”，削弱研究贡献。

2. 数据集强度偏弱

   当前三个场景覆盖 image、time series、log/multimodal，但仓库内样本和 KG 都是 v0 demo 规模。它们能展示 pipeline 完整性，但还不足以支撑 paper-grade 的大规模实证。GPT Pro 需要帮助判断：论文评估最低需要多少样本、哪些指标、哪些 ablation，才能让贡献可信。

3. MVTec 不天然适合 RCA

   MVTec 主要是视觉异常/缺陷检测数据集，并不提供真实工厂流程、设备、工艺 root cause。若把 MVTec paths 讲成 verified factory RCA，会被审稿质疑。更合理的定位是：MVTec 用来展示视觉 evidence normalization、morphology/location consistency、噪声修正和 KG explanation；RCA path 只能称为 curated plausible candidate explanation，不是 verified RCA。

4. Manual plausible RCA labels 有双刃剑风险

   人工 plausible references 对 demo 和初步评估有用，但必须标清来源和用途。如果论文用它们计算 path hit rate 或 top-k accuracy，需要说明这是 against curated plausible references，而不是真实工厂 ground truth。

5. Demo 可能看起来像 static display 或 placeholder

   如果 example JSON 已经写入 `kg_analysis` 或 root cause，UI/API 只是在展示静态 JSON，就会显得像 placeholder。正确方式是 example JSON 只包含 evidence input；每次 what-if 编辑后清空 stale analysis，由 `KGTracePipeline` 重新计算 linking、consistency、correction candidates 和 candidate RCA paths，并展示 source edge provenance。

## 4. Codex/GPT Agent 的分析与推荐架构

推荐把 KGTraceVis 解释为一个四层流水线，而不是“数据集 + KG + app”的松散堆叠：

1. Evidence ingestion layer

   数据集 adapter 或人工 demo annotation 将原始 anomaly outputs 转成统一 `Evidence` schema。输出只代表 observed anomaly evidence。字段包括 `case_id`、`dataset`、`source`、`object`、`anomaly_type`、`location`、`morphology`、`severity`、`confidence`、`timestamp`、`raw_evidence`、`normalized_evidence`、`kg_analysis`、可选 `human_feedback`。其中 `kg_analysis` 初始应为空。

2. Source-constrained KG construction layer

   来源材料先进入 source registry 或 docs/sources；LLM 可以从文档中抽取 candidate entities/triples，但每条 edge 都必须保留 source、evidence、confidence、review_status 和 feedback counters。QA 只负责发现问题，不负责编造缺失事实。reviewed triples 不应被自动覆盖。

3. KGTracePipeline reasoning layer

   统一入口是 `KGTracePipeline.analyze(evidence)`。该层按顺序运行：

   - `link_evidence_entities`
   - `check_consistency`
   - `generate_correction_candidates`
   - `rank_root_cause_paths`

   Path ranking 不应只依赖 shortest path，而应使用 relation-weighted score：

   `Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)`

   输出是 candidate/plausible RCA paths，不是最终事实断言。MVTec 场景尤其要写成 curated plausible references and runtime candidates。

4. Visual analytics and feedback layer

   服务或未来 UI 只调用 pipeline，不复制核心逻辑。UI/API 应把 evidence input、runtime KG analysis、source edge provenance 分开展示。用户反馈可针对 correction candidate、path、entity linking、KG edge 记录稳定引用。

推荐论文叙事：

- 不把系统宣传成“自动发现真实工业根因”的强声明。
- 改成“knowledge-constrained evidence analysis for explainable anomaly traceability”。
- 对 TEP/wafer 强调 RCA path ranking，对 MVTec 强调视觉 evidence normalization、consistency/correction 和 plausible explanation。
- 所有 MVTec RCA 相关输出必须写清楚：MVTec should not be claimed as verified factory RCA。

## 5. 当前仓库实现状态

当前仓库已经有一个可运行的 v0 pipeline 和组会 demo 基础。根据任务 PRD 与本地代码，主要状态如下。

### 5.1 Core pipeline

- `src/kgtracevis/core/pipeline.py` 定义 `KGTracePipeline`，统一运行 entity linking、consistency checking、correction generation 和 path ranking。
- `src/kgtracevis/core/result.py` 定义 `AnalysisResult`，包含 `case_id`、`linked_entities`、`consistency_score`、`inconsistent_fields`、`correction_candidates`、`top_k_paths`、`human_feedback`。
- 这个 pipeline 是 scripts 和 service 应调用的核心入口。

### 5.2 Unified evidence schema

- `src/kgtracevis/schema/evidence_schema.py` 定义 Pydantic schema：
  - `DatasetName = "mvtec" | "tep" | "wafer"`
  - `EvidenceSource = "image" | "time_series" | "log" | "multimodal" | "unknown"`
  - `RawEvidence` 包含 image region、heatmap path、variables、variable_contributions、log_events、description、extra。
  - `Evidence` 包含统一 top-level 字段和 `kg_analysis`。
- 设计上支持 dataset-specific 内容放在 `raw_evidence`，避免创建多个 dataset-specific JSON schema。

### 5.3 Dataset adapters

- `src/kgtracevis/adapters/ds_mvtec_adapter.py`
- `src/kgtracevis/adapters/tep_adapter.py`
- `src/kgtracevis/adapters/wafer_adapter.py`
- `src/kgtracevis/adapters/batch.py`

这些 adapter 已经能把 MVTec/TEP/wafer 风格输入转换成统一 `Evidence`。`batch.py` 支持 JSON、JSONL、CSV records，按 dataset 选择 adapter，并写出 evidence JSON/JSONL。

### 5.4 KG and reasoning modules

- `src/kgtracevis/kg/graph.py`：从 CSV 加载 in-memory KG，默认读取 `data/kg/nodes.csv`、`data/kg/edges.csv`、`data/kg/mvtec_rca_reference.csv`。节点/边 schema 包括 required columns，edge 有稳定 `edge_id`。
- `src/kgtracevis/kg/entity_linker.py`：基于 exact/id/name/alias/fuzzy 等规则生成 top-k candidates，并记录 ambiguity。
- `src/kgtracevis/kg/consistency_checker.py`：检查 evidence 字段与 KG constraints。
- `src/kgtracevis/kg/correction_generator.py`：基于 KG 支持边生成 correction candidates。
- `src/kgtracevis/kg/path_ranker.py`：使用 relation confidence、evidence match 和 length penalty 计算 candidate RCA paths，并生成稳定 `path_id`、source edges、supporting evidence。
- `src/kgtracevis/kg/import_neo4j.py`：提供 Neo4j 导入支持。

### 5.5 KG construction and QA

- `src/kgtracevis/kg_construction/source_loader.py`
- `src/kgtracevis/kg_construction/candidate_entity_extractor.py`
- `src/kgtracevis/kg_construction/candidate_triple_extractor.py`
- `src/kgtracevis/kg_construction/confidence_assigner.py`
- `src/kgtracevis/kg_construction/triple_cleaner.py`
- `src/kgtracevis/kg_construction/export_kg_csv.py`
- `src/kgtracevis/kg_construction/qa.py`

这些模块支持 source-constrained semi-automatic KG construction 的雏形：从来源加载文本，抽取候选实体/三元组，分配 confidence/weight，清理/导出 CSV，并做结构 QA。QA 会检查 required columns、missing node refs、duplicate edges、confidence/weight、review_status、feedback counters、isolated nodes 等。

### 5.6 Data and KG assets

- `data/examples/ds_mvtec_example.json`
- `data/examples/mvtec_noisy_morphology_demo.json`
- `data/examples/tep_example.json`
- `data/examples/wafer_example.json`
- `data/kg/nodes.csv`
- `data/kg/edges.csv`
- `data/kg/mvtec_rca_reference.csv`
- `data/kg/source_registry.csv`

当前 checked-in examples 已经加入 demo boundary metadata，说明这些 JSON 是 observed anomaly evidence only，不包含 root-cause label；`KGTracePipeline` 在运行时计算 linking/consistency/corrections/candidate RCA paths。另有 noisy MVTec case 用于展示 morphology inconsistency 和 correction candidate。

当前 KG 是小规模 v0 demo KG。PRD 中记录此前 smoke checks 通过：`uv run --extra dev pytest -q` 为 63 passed，`uv run python scripts/run_examples.py` 可分析 MVTec、TEP 和 wafer examples；QA 输出记录过约 36 nodes 和 29 edges，足以 demo，但不是 paper-grade KG。

### 5.7 FastAPI backend and dashboard boundary

- `src/kgtracevis/service/` 是当前保留的 web-facing backend。
- Legacy Streamlit demo and old React/Vite frontend have been removed so the
  RootLens dashboard can be rebuilt cleanly later.
- Service/API outputs must keep example case selection, what-if editing,
  runtime pipeline analysis, KG analysis, and correction/path source provenance
  available to future clients.
- MVTec client copy must continue to explain that RCA source edges are curated
  plausible references and displayed paths are runtime candidates, not MVTec
  native factory RCA labels.

### 5.8 Scripts, metrics, experiments, tests

- Scripts：
  - `scripts/generate_evidence.py`
  - `scripts/build_kg.py`
  - `scripts/run_examples.py`
  - `scripts/run_kg_qa.py`
  - `scripts/run_path_ranking.py`
  - `scripts/run_noise_experiment.py`
  - `scripts/run_experiment_suite.py`
  - `scripts/run_feedback_update.py`
  - `scripts/import_kg.py`
  - `scripts/run_web_api.py`
- Metrics：
  - schema validity
  - linking metrics
  - consistency/detection metrics
  - correction metrics
  - ranking metrics
- Tests cover adapters, schema, KG graph/loading, entity linking, consistency checking, path ranking, noise injection, metrics, KG construction/QA, service behavior, scripts.

## 6. 希望 GPT Pro 重点调研和回答的问题

请 GPT Pro 不只是给概念建议，而是产出一套可以直接转化为论文/实现路线的 finished solution。重点问题如下。

1. 论文研究问题如何定义最稳妥？

   应该把 KGTraceVis 定义为 KG-enhanced anomaly RCA、evidence correction、traceability visualization，还是 knowledge-constrained evidence analysis？怎样避免“没有真实 RCA ground truth”的攻击？

2. 三个数据集如何分工最合理？

   - MVTec：适合承担哪些任务？是否只用于 visual anomaly evidence normalization、consistency/correction 和 plausible explanation？
   - TEP：是否应作为主 RCA evaluation dataset？如何把 TEP fault labels、variables、process units 和 root causes 组织成 KG？
   - Wafer：如果缺少公开真实 root cause，如何构造 image-log demo 而不夸大结论？

3. Root-cause annotation 的最低可信方案是什么？

   需要区分 native ground truth、official fault type、literature-supported cause、manual plausible reference、LLM candidate。请 GPT Pro 设计 annotation taxonomy、CSV/JSON 字段、评估时可用/不可用的标签边界。

4. Adapter-vs-KG boundary 如何在论文和代码中写清楚？

   请提出一段可放入论文 method 的定义：adapters produce observed anomaly evidence, not root cause；KGTracePipeline computes candidate/plausible RCA paths at runtime。还需要说明 `kg_analysis` 何时为空、何时由 pipeline 填充。

5. Source-constrained semi-automatic KG construction 的 pipeline 应如何完善？

   GPT Pro 需要给出从文档收集、source registry、LLM triple extraction、schema validation、confidence assignment、manual review、QA、CSV/Neo4j import 的完整流程。还要说明 confidence 如何根据 source type 分配，review_status 如何影响 overwrite 和 evaluation。

6. Evaluation design 如何更有说服力？

   当前可评估的指标包括 schema validity rate、entity linking accuracy/top-k accuracy、inconsistency detection precision/recall、correction accuracy/top-k correction accuracy、noise recovery rate、top-k root-cause accuracy、MRR、path hit rate。请 GPT Pro 判断哪些指标适合 paper 主表，哪些只适合 appendix/demo。

7. Noise experiment 应该怎样设计？

   当前 noise injection 支持 anomaly type replacement、location replacement、morphology replacement、variable deletion、variable name perturbation、log event deletion、synonym substitution、contradiction injection。请设计每个 dataset 的 noise protocol、noise level、random seed、clean reference、reporting format。

8. Demo 如何避免 static placeholder impression？

   请 GPT Pro 提出一个现场演示脚本：每一步展示什么、如何进行 what-if 编辑、如何证明 paths 是 runtime computation、如何展示 source edge provenance，以及如何解释 noisy MVTec case。

9. KG schema 是否需要调整？

   当前 node columns 是 `id,name,label,scenario,aliases,description`；edge columns 是 `head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count`。请判断是否还需要 source_id、source_type、extractor、created_by、last_reviewed_at、annotation_type 等字段，或者保持 v0 简洁。

10. 论文贡献和消融实验如何写？

   可以考虑的 ablations：without KG constraints、shortest path only vs relation-weighted ranking、without evidence match、without correction step、manual KG vs LLM-extracted+QA KG、不同 noise levels。请 GPT Pro 判断哪些能在当前资源下完成，哪些不应承诺。

11. 是否需要替换/补充数据集？

   如果 MVTec 对 RCA 太弱，是否应增加一个更自然的 RCA dataset 或 benchmark？若不能增加，如何调整 claim 和 evaluation 让方案仍然成立？

12. 最终系统图和方法章节应该怎么画/写？

   请输出建议的 architecture figure、data flow diagram、algorithm boxes、table layouts，以及 method section 的小节结构。

## 7. 建议下一步

1. 先让 GPT Pro 给出“论文定位 + dataset/evaluation 方案”的明确建议，尤其判断 MVTec 在论文中的角色边界。

2. 固化 adapter-vs-KG boundary：

   - adapter/manual annotation 输出 observed anomaly evidence only。
   - `kg_analysis` 初始为空。
   - `KGTracePipeline` runtime computes linking/consistency/corrections/candidate RCA paths。
   - root cause references 只进入 evaluation/reference 文件或 KG source edges，不进入 adapter 输出作为答案。

3. 建立 annotation taxonomy：

   - verified/native
   - official fault type
   - literature-supported
   - manual plausible
   - LLM candidate

   每个 label/reference 都要有 source、evidence、confidence、review_status。

4. 把 TEP 作为主要 RCA 评估场景，MVTec 作为视觉 evidence + correction/explanation 场景，wafer 作为 multimodal demo 场景，除非 GPT Pro 找到更强数据集替代方案。

5. 完善 KG construction pipeline：

   - source registry
   - document collection guide
   - LLM extraction prompt/output schema
   - QA report
   - manual review workflow
   - reviewed triples overwrite protection

6. 做一个 small-but-honest experiment suite：

   - schema validity
   - linking top-k accuracy
   - consistency/correction under injected noise
   - top-k RCA path hit/MRR against appropriate references
   - clear separation between demo-scale curated data and paper-grade claims

7. 强化 demo：

   - 首页或 sidebar 明确 v0 demo scope。
   - 至少一个 noisy case 展示 inconsistency 和 correction。
   - What-if 编辑后实时重算。
   - 展示 source edge provenance。
   - 对 MVTec 明确说：candidate paths are curated plausible/runtime explanations, not verified factory RCA。

8. 在 README、docs/project_design.md、docs/evidence_schema.md、docs/ontology_schema.md 中同步最终术语和边界，避免论文、代码、demo 三套说法不一致。

## 8. 给 GPT Pro 的期望输出格式

请 GPT Pro 最终输出：

- 一段推荐的论文 title/abstract-level positioning。
- 一张系统架构图的文字描述。
- 一个 dataset-role table，说明每个数据集负责什么任务、能评估什么、不能声称什么。
- 一个 annotation taxonomy 和字段设计。
- 一个 KG construction workflow，包括 LLM extraction prompt/schema、QA、manual review。
- 一个 method section outline。
- 一个 evaluation plan，包括主指标、辅助指标、ablation、可执行实验命令建议。
- 一个 demo script，说明如何避免 static placeholder impression。
- 一个 implementation backlog，按“必须做 / 应该做 / 可延后”排序。

最重要的约束：不要把 MVTec 说成有 verified factory RCA；不要让 adapters 输出 root cause；不要把 `KGTracePipeline` 的 runtime candidate paths 伪装成输入标签或静态展示。
