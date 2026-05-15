1. 结构 Review：三段式合理，但建议微调标题

我的判断：保留三段式结构。handoff 里已经把 RootLens 定位为一个 requirements-driven visual analytics system，而不是新的 detector 或纯 RCA 算法；其核心贡献是把 image / time-series / log / document 输出统一成 evidence、KG entity、source trace、candidate path 与 human feedback。这个定位决定 Related Work 应按“上游检测与 RCA → 知识层 → 交互可视分析层”来组织。 

我建议把 subsection 标题稍微 sharpen：

当前标题	建议标题	原因

Industrial Anomaly Detection and Root Cause Analysis	Modality-Specific Industrial Anomaly Detection and Root-Cause Analysis	强调这些方法多是 modality/scenario-specific，RootLens 不替代它们，而是包装其输出。
Knowledge Graphs and LLMs for Industrial Knowledge	Source-Grounded Knowledge Graphs and LLM-Assisted Industrial Knowledge Construction	把 RootLens 的关键差异“source grounding / provenance / reviewability”提前放进标题。
Visual Analytics for Diagnosis, Provenance, and Human-AI Decision Making	Visual Analytics for Diagnosis, Provenance, and Human-AI Decision Making	这个标题可以保留；它已经覆盖 VA、provenance、human-in-the-loop 三个必要论点。


最终每段建议只写 1 个紧凑段落，最多 2 个短段落。handoff 里也明确说 Related Work 目标长度约 0.7–0.8 页，且不应变成 citation dump。 所以下面我列的是审核用 citation pool；正式正文里每节大概只需要 6–8 篇核心引用，剩余作为 bib / rebuttal / appendix 储备。

Alternative structures

A. Pipeline-centric structure

1. Evidence from modality-specific detectors


2. Source-grounded KG and RCA reasoning


3. Provenance-aware visual analytics and human feedback
这个结构最贴 RootLens pipeline，但标题会显得偏“方法介绍”，Related Work 的 reviewer-facing 分类感稍弱。



B. Reviewer-facing structure，也就是我推荐的三段式

1. Modality-specific industrial AD/RCA


2. Source-grounded KG + LLM construction


3. VA + provenance + human-AI decision making
这个结构最平衡，能同时回应工业过程、KG/LLM、可视化三个审稿群体。



C. 五段式：Process RCA / Visual AD / KG / Provenance / Human-AI VA
不推荐。ChinaVis full paper 篇幅有限，handoff 也要求 Related Work concise；五段式会把 gap 拆碎，容易变成罗列文献。


---

2. 推荐 subsection structure 与每节论证目标

2.1 Modality-Specific Industrial Anomaly Detection and Root-Cause Analysis

段落目标：说明已有工业 AD/RCA 方法在各自 modality 或场景内很强：TEP/process monitoring、multivariate time-series RCA、causal/process-topology RCA、visual anomaly localization。但它们通常输出异常分数、变量排名、热图、mask、root-cause candidate list，而不是跨模态、可追溯、可交互修正的 evidence-to-KG-to-path workflow。handoff 中也特别要求这里以 cross-modal evidence、source traces、interactive verification 作为 gap 收尾。

2.2 Source-Grounded Knowledge Graphs and LLM-Assisted Industrial Knowledge Construction

段落目标：说明 KG 能编码设备、变量、工艺、故障、事件、因果/拓扑关系；LLM/IE 能从 manuals、papers、logs、documents 中加速抽取实体和关系。但自动构建的 KG 会有 hallucination、entity ambiguity、schema mismatch、relation noise、provenance 不足等问题。因此 RootLens 的差异不是“构一个 KG”，而是把 KG edge / LLM-extracted triple / candidate path 都作为 source-grounded、可审查、可编辑的对象。handoff 也明确要求这一节强调 source grounding、quality governance、human correction。

2.3 Visual Analytics for Diagnosis, Provenance, and Human-AI Decision Making

段落目标：说明 VA 研究提供了 design study methodology、task abstraction、interactive diagnosis、analytic provenance、human-AI decision support 的基础。但现有系统常分别关注 anomaly exploration、model debugging、provenance capture 或 KG exploration；RootLens 的定位是把 heterogeneous evidence inspection、source-grounded KG path reasoning、human feedback / write-back 合成一个工业 RCA workflow。handoff 也把这一节的 gap 定义为“VA / provenance / KG path reasoning / grounded feedback 尚未充分结合”。


---

3. 文献池：先审核，不直接写正文

标记说明：
核心 = 正文优先引用；可选 = 可作为补充、替换或 rebuttal 储备；[VERIFY] = 正式写 BibTeX 前需要再次核对版本、venue 或 metadata。


---

A. Modality-Specific Industrial Anomaly Detection and Root-Cause Analysis

推荐	文献	一句总结	与 RootLens 的关系

核心	Downs & Vogel, A plant-wide industrial process control problem, Computers & Chemical Engineering, 1993	经典 TEP benchmark，提出 plant-wide industrial process control problem，用于研究和评估工业过程控制 / 监测 / 诊断技术。	作为 RootLens TEP case 的标准背景；但要避免把 TEP 单独写成多源异构验证。handoff 也提醒 TEP 若只做时序 RCA，不足以支撑全部 multi-source claim。
核心	Venkatasubramanian et al., A review of process fault detection and diagnosis, Computers & Chemical Engineering, 2003, Parts I–III	三篇综述分别覆盖 quantitative model-based、qualitative model-based、process history-based FDD，并指出不同方法各有局限、可互补。	用来支撑“工业 FDD/RCA 方法强但分散，难以统一到可追溯工作流”的总论点。
核心	Qin, Survey on data-driven industrial process monitoring and diagnosis, Annual Reviews in Control, 2012	系统回顾数据驱动工业过程监测与诊断方法，强调复杂工业过程下 FDD 方法的发展。	作为工业 process monitoring / diagnosis 的权威综述引用，帮助 Related Work 不只依赖近年深度学习论文。
核心	Chen et al., Root-KGD: A Novel Framework for Root Cause Diagnosis Based on Knowledge Graph and Industrial Data, arXiv, 2024 [VERIFY venue]	将工业数据特征与知识图谱结合，用于把故障定位到设备、物流等物理实体，并在 TEP 等案例上验证。	与 RootLens 最直接相邻：RootLens 可把这类 KG-based RCA 算法作为 pluggable reasoning plugin，而不是替代它。
核心	Wang et al., Root cause diagnosis for complex industrial process faults via spatiotemporal coalescent based time series prediction and optimized Granger causality, Chemometrics and Intelligent Laboratory Systems, 2023	用时空预测与优化 Granger causality 做复杂工业过程故障根因诊断。	支撑“process RCA 常依赖 temporal/causal assumptions”；RootLens 可以接收其 root-cause ranking / causal path 作为 evidence。
核心	Song, Zhao, Huang, MPGE and RootRank, Neural Networks, 2023	通过捕捉直接与间接 Granger causality、故障传播路径和 RootRank 分数来量化工业过程故障根因。	与 RootLens 的 candidate path / path score 概念相近，但 RootLens 进一步强调 source trace 与 human review。
可选	Yang, Zhang, Hoi, A Causal Approach to Detecting Multivariate Time-series Anomalies and Root Causes, arXiv, 2022 [VERIFY venue]	从 local causal mechanism 角度处理 multivariate time-series anomaly detection 和 root-cause analysis。	可用于补充 causal MTS RCA 方向；若篇幅紧张，可被 Wang / MPGE 替代。
核心	Zhang et al., A Deep Neural Network for Unsupervised Anomaly Detection and Diagnosis in Multivariate Time Series Data, AAAI, 2019	MSCRED 用多尺度 signature matrix 与卷积循环 encoder-decoder 建模传感器相关性，用于无监督异常检测和诊断。	支撑 time-series detector/diagnoser 输出 anomaly score、sensor correlation、diagnostic clues，而非 traceable RCA workflow。
核心	Su et al., OmniAnomaly: Robust Anomaly Detection for Multivariate Time Series through Stochastic Recurrent Neural Network, KDD, 2019	用 stochastic recurrent neural network 做多变量时序异常检测，并可通过 reconstruction probability 解释异常变量。	适合作为 RootLens time-series adapter 的代表性上游模型。
核心	Zhao et al., Multivariate Time-Series Anomaly Detection via Graph Attention Network, ICDM, 2020	MTAD-GAT 用 graph attention 同时建模 feature-wise 与 temporal dependencies。	支撑“graph/attention-based MTS AD 可提供变量关系线索，但仍需被映射为可审查 evidence”。
核心	Deng & Hooi, Graph Neural Network-Based Anomaly Detection in Multivariate Time Series, AAAI, 2021	GDN 学习传感器之间的 graph structure，并用 attention/graph relation 支持异常检测与解释。	与 RootLens 的 KG entity alignment 有连接点：模型关系图可转化为候选 evidence/edge，但不等同于领域 KG。
核心	Bergmann et al., MVTec AD: A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection, CVPR, 2019 / IJCV extension	MVTec AD 是工业视觉异常检测与分割 benchmark，提供 pixel-level ground-truth anomaly regions。	用来界定 visual evidence 的边界：它支持 defect localization，不提供生产过程 RCA ground truth；handoff 也明确不能把 MVTec 写成 RCA benchmark。
核心	Defard et al., PaDiM: Patch Distribution Modeling Framework for Anomaly Detection and Localization, ICPR, 2021	用预训练 CNN patch embedding 与 Gaussian distribution 建模正常 patch 分布，实现 anomaly localization。	代表 visual detector 输出 heatmap/mask/score，RootLens 可将这些输出包装为 image evidence。
核心	Zavrtanik et al., DRAEM: A Discriminatively Trained Reconstruction Embedding for Surface Anomaly Detection, ICCV, 2021	结合 reconstruction 与 discriminative segmentation 做 surface anomaly detection。	支撑 image adapter 中 anomaly mask / segmentation map 的来源。
核心	Roth et al., Towards Total Recall in Industrial Anomaly Detection, CVPR, 2022	PatchCore 使用代表性 memory bank 的 nominal patch features，在工业 anomaly detection/localization 上取得强性能。	作为视觉异常检测强 baseline；RootLens 不是与 PatchCore 比检测精度，而是利用其输出进入 traceable RCA workflow。
可选	Jeong et al., WinCLIP, CVPR, 2023	用 CLIP 做 zero-/few-shot anomaly classification 与 segmentation。	可用于补充 VLM/semantic mapping 方向，尤其是把 visual anomaly 映射到 KG candidate entity。
可选	Batzner et al., EfficientAD, WACV, 2024	面向低延迟工业视觉异常检测，结合 lightweight feature extractor、student-teacher 与 autoencoder。	若论文强调系统实时性或工业部署，可作为 visual detector 近期代表。


这一节正文建议最终保留：Downs & Vogel、Venkatasubramanian review、Qin、Root-KGD、Wang/MPGE 二选一或都引、MSCRED/OmniAnomaly/MTAD-GAT/GDN 选 2–3 篇、MVTec、PatchCore、PaDiM/DRAEM 二选一。


---

B. Source-Grounded Knowledge Graphs and LLM-Assisted Industrial Knowledge Construction

推荐	文献	一句总结	与 RootLens 的关系

核心	Hogan et al., Knowledge Graphs, ACM Computing Surveys, 2021	系统介绍 KG 的数据模型、schema、identity、context、deductive/inductive reasoning 等基础问题。	用作 KG 总体背景，避免只引用应用论文。
核心	Ji et al., A Survey on Knowledge Graphs: Representation, Acquisition, and Applications, IEEE TNNLS, 2022	综述 KG representation learning、KG acquisition/completion、temporal KG 与应用。	支撑“KG construction 与 reasoning 是成熟方向，但 RootLens 关注工业 RCA 中的 source-grounded governance”。
核心	Wan et al., Making knowledge graphs work for smart manufacturing, Journal of Manufacturing Systems, 2024	系统梳理 KG 在 smart manufacturing 中的研究主题、应用和前景。	最贴工业制造 KG 背景，可作为本节核心引用之一。
核心	Xiao et al., Knowledge graph-based manufacturing process planning: A state-of-the-art review, Journal of Manufacturing Systems, 2023	回顾 KG 在 manufacturing process planning 中的应用。	用于说明 KG 能表达 process、resource、operation 等制造知识，但 RootLens 更关注异常证据与 RCA path。
可选	Cai et al., Knowledge graph-driven equipment fault diagnosis method for intelligent manufacturing, IJAMT, 2024	提出面向设备故障诊断的 KG-driven 方法，结合多源数据构建多层级 KG。	领域相关但 venue 不如 TVCG/CHI/IEEE TNNLS；可作为工业 fault diagnosis KG 的补充引用。
核心	W3C, PROV-DM: The PROV Data Model, 2013	定义 provenance 的核心概念、类型和关系。	支撑 RootLens 中 source trace / evidence provenance 的概念基础。
核心	W3C, PROV-O: The PROV Ontology, 2013	用 OWL2 表达 PROV-DM，使 provenance 可在 RDF/semantic web 中交换和建模。	可用于论证 KG edge / evidence / source trace 可以结构化建模，而不是仅存文本备注。
可选	Carroll et al., Named Graphs, Provenance and Trust, WWW, 2005	提出 named graph 机制以支持 RDF 中的 provenance 与 trust 表达。	对“每条 KG triple/edge 应保留 source/evidence”很相关；可作为 semantic provenance 的早期基础。
核心	Pan et al., Unifying Large Language Models and Knowledge Graphs: A Roadmap, IEEE TKDE, 2024	综述 KG-enhanced LLM、LLM-augmented KG 以及二者协同方向。	用来定位 LLM 与 KG 的互补关系；RootLens 采用 LLM 辅助候选生成，而不是把 LLM 输出当作事实。
核心	Zhu et al., LLMs for Knowledge Graph Construction and Reasoning, arXiv / WWWJ version [VERIFY], 2023–2024	评估 LLM 在 entity/relation extraction、event extraction、link prediction、QA 等 KG construction/reasoning 任务上的能力与局限。	支撑“LLM 可加速 KG construction，但仍需要 verification、source grounding 和 human correction”。
核心	Li et al., A Survey of Graph Meets Large Language Model, IJCAI, 2024	系统梳理 LLM 与 graph 任务结合的 taxonomy，包括 LLM as enhancer、predictor、alignment component 等。	可作为 LLM+graph 总综述，帮助本节避免只引用单个 LLM 抽取方法。
可选	SAC-KG, Exploiting Large Language Models as Skilled Automatic Constructors for Domain Knowledge Graph, ACL, 2024	使用 LLM 自动构建 domain knowledge graph。	代表 LLM-assisted domain KG construction；RootLens 的差异是把自动构建结果作为可审查候选。
核心	Cabot & Navigli, REBEL: Relation Extraction By End-to-end Language Generation, Findings of EMNLP, 2021	将 relation extraction 建模为端到端序列生成任务，可抽取实体关系三元组。	支撑 text/document adapter 中 relation/triple extraction 的技术背景。
核心	Yao et al., DocRED: A Large-Scale Document-Level Relation Extraction Dataset, ACL, 2019	提出大规模 document-level relation extraction 数据集，强调跨句推理。	与从 manuals / papers / logs 中抽取工业关系相关，尤其适合说明 document-level IE 的必要性。
可选	Zhao et al., A Comprehensive Survey on Relation Extraction: Recent Advances and New Frontiers, ACM Computing Surveys, 2024	综述 relation extraction 的数据集、方法、预训练模型和挑战。	可替代 REBEL/DocRED 中的部分背景，尤其当正文想少列具体 IE 方法时。


这一节正文建议最终保留：Hogan 或 Ji 二选一作 KG 背景；Wan 作为 smart manufacturing KG 核心；PROV-DM/PROV-O 或 Named Graphs 选 1–2 篇作 provenance grounding；Pan + Zhu/Li 作 LLM+KG；REBEL/DocRED 选 1–2 篇作 extraction 背景。


---

C. Visual Analytics for Diagnosis, Provenance, and Human-AI Decision Making

推荐	文献	一句总结	与 RootLens 的关系

核心	Munzner, A Nested Model for Visualization Design and Validation, IEEE TVCG, 2009	提出 visualization design/validation 的四层模型：domain problem、abstraction、encoding/interaction、algorithm。	适合支撑 RootLens 作为 requirements-driven VA system 的方法论。
核心	Sedlmair, Meyer, Munzner, Design Study Methodology, IEEE TVCG, 2012	提出 design study 的九阶段方法，强调从真实领域问题与专家需求出发。	与 RootLens 的 design requirements、expert feedback、case-driven evaluation 直接相关。
可选	Brehmer & Munzner, A Multi-Level Typology of Abstract Visualization Tasks, IEEE TVCG, 2013	提出 why/how/what 的任务抽象 typology。	可用于后文设计需求或任务分析，不一定放入 Related Work。
核心	Heer et al., Graphical Histories for Visualization, IEEE TVCG, 2008	通过记录和可视化交互历史支持分析回溯、交流与评估。	支撑 RootLens 的 analysis history / provenance / source-trace review 方向。
核心	Gotz & Zhou, Characterizing Users’ Visual Analytic Activity for Insight Provenance, Information Visualization, 2009	将用户分析活动抽象为多层级 actions，用于 insight provenance。	可用于说明 RootLens 不只记录数据来源，还应记录人机分析过程与确认状态。
核心	Ragan et al., Characterizing Provenance in Visualization and Data Analysis, IEEE TVCG, 2016	提出 visualization/data analysis provenance 的类型与用途框架。	本节最核心的 provenance 引用；可直接支撑 source trace、candidate path、human status 可视化。
核心	Endert et al., The Human is the Loop, Journal of Intelligent Information Systems, 2014	强调 VA 中人不是“在环外监督”，而是分析和模型更新循环的一部分。	与 RootLens 的 human confirmation、editing、write-back 机制高度相关。
核心	Amershi et al., Guidelines for Human-AI Interaction, CHI, 2019	提出并验证 18 条 human-AI interaction guidelines。	支撑 RootLens 中 algorithmic outputs 应可解释、可检查、可修正，而不是直接作为最终答案。
可选	Sacha et al., Human-centered Machine Learning through Interactive Visualization, ESANN / Neurocomputing version, 2016–2017	讨论 interactive visualization 如何支持 human-centered machine learning 与用户反馈。	可作为 human-in-the-loop / model-steering 背景；若篇幅紧，可由 Endert + Amershi 覆盖。
核心	Hohman et al., Visual Analytics in Deep Learning, IEEE TVCG, 2019	综述 VA 如何支持 deep learning 的解释、调试、诊断与改进。	连接 upstream detectors 与 interactive inspection；说明 RootLens 面向的是检测结果之后的可视分析。
核心	Zhang et al., A Visual Analytics Approach for the Diagnosis of Heterogeneous and Multidimensional Machine Maintenance Data, IEEE PacificVis, 2021	面向 heterogeneous, multidimensional machine maintenance data 的诊断 VA 系统。	与 RootLens 最接近的工业 maintenance/diagnosis VA 系统之一；RootLens 进一步强调 KG path reasoning 与 source-grounded evidence。
核心	Liu et al., MTV: Visual Analytics for Detecting, Investigating, and Annotating Anomalies in Multivariate Time Series, PACM HCI / CSCW, 2022	支持 MTS anomaly detection、investigation、annotation 的 human-AI workflow。	可用于说明 VA 已支持 time-series anomaly investigation，但 RootLens 扩展到 KG、source trace 和多模态 evidence。
核心	Montambault et al., PIXAL: Anomaly Reasoning with Visual Analytics, arXiv, 2022 [VERIFY venue]	面向专业分析师的 anomaly reasoning VA 系统，支持 anomaly pattern、hypothesis、counterfactual / comparative analysis。	与“异常不是终点，reasoning / hypothesis 才是核心”的论点直接相关。
核心	Li et al., Knowledge Graphs in Practice: Characterizing their Users, Challenges, and Visualization Opportunities, IEEE VIS / TVCG, 2024	通过访谈 KG practitioners，总结 KG users、challenges 与 visualization opportunities。	支撑 RootLens 的 KG 管理、KG correction、不同用户角色与可视化机会。
核心	Yuan et al., KGScope: Interactive Visual Exploration of Knowledge Graphs with Embedding-Based Guidance, IEEE TVCG, 2024	将 KG 可视探索与 embedding-based guidance 结合，支持交互式 KG exploration。	支撑 KG path / graph exploration 的 visual analytics 背景；RootLens 的差异是把 KG exploration 嵌入工业 RCA evidence workflow。


这一节正文建议最终保留：Munzner + Sedlmair 作 design study；Ragan + Gotz/Heer 作 provenance；Endert + Amershi 作 human-AI/HITL；Zhang maintenance VA + MTV + PIXAL 作 diagnosis/anomaly VA；Li KG practice 或 KGScope 作 KG visualization。


---

4. 我建议的最终 Related Work 引用策略

正式正文不要把上面所有文献都写进去。建议每节正文这样压缩：

Subsection	正文核心引用数量	建议保留类型

Modality-Specific Industrial AD/RCA	8–10	TEP/FDD 经典综述 2–3；MTS AD/RCA 3–4；visual AD 2–3
Source-Grounded KG + LLM	7–9	KG survey 1–2；smart manufacturing KG 1–2；provenance 1–2；LLM/KG/IE 3
VA + Provenance + Human-AI	8–10	design study 2；provenance 2；human-AI 1–2；diagnosis/anomaly VA 2–3；KG visualization 1


核心写法应该围绕 gap，而不是按年份罗列：

> Existing detectors and RCA methods identify abnormal variables, regions, or candidate causes, but they rarely preserve heterogeneous evidence and source traces in a unified, inspectable workflow.
KG and LLM methods can construct and reason over industrial knowledge, but automatically generated triples require provenance, quality governance, and human correction.
VA systems support diagnosis, provenance, and human-AI decision making, but RootLens couples these ideas around source-grounded KG path reasoning for industrial RCA.



这与 handoff 中的安全边界一致：不要声称 RootLens “solves industrial RCA”，不要把 MVTec 写成 RCA benchmark，也不要把 LLM 抽取的 triples 当作可靠事实。

请先审核每篇的“保留 / 删除 / 替换”，下一步再进入 Related Work 正文草稿。