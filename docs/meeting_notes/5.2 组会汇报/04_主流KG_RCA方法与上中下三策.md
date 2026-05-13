# 04 主流 KG+RCA 方法与上中下三策

## 主流 KG+RCA 方法类别

结合已有研究 brief、GPT Pro 讨论结论和当前仓库实现，KG+RCA（知识图谱辅助根因分析）大致可以分成几类。

### 1. Expert KG + rule/path reasoning

用专家知识、工艺文档、变量表、设备关系和故障说明构建 KG，再基于规则、约束或路径搜索进行解释。优点是可解释、可控、适合 source-constrained KG（来源约束知识图谱）；缺点是依赖人工整理和 review，覆盖面通常有限。

KGTraceVis 当前 v0 主要属于这一类：小型任务 KG + deterministic linking + consistency rules + relation-weighted path ranking。

### 2. Probabilistic graphical model

用 Bayesian Network（贝叶斯网络）、causal graph（因果图）或概率传播模型表达事件、变量和根因之间的不确定关系。优点是能表达概率和因果方向；缺点是结构学习和参数估计需要更强数据或专家支持，短期实现成本较高。

### 3. Temporal/process mining + KG

把时序变量、日志事件、工艺阶段、设备状态组织成 Online Evidence Graph（在线证据图）或动态事件图，再做时序传播和 RCA。优点是更贴近工业过程；缺点是对数据完整性要求高，公开 MVTec/WM-811K 很难支持。

TEP 是最接近这一方向的公开可控场景，因为变量、过程单元和 fault 类型更容易组织。

### 4. Representation learning / GNN

用 graph embedding、GNN（Graph Neural Network，图神经网络）或 temporal GNN 在图上学习故障传播和根因排序。优点是可扩展、可学习复杂模式；缺点是需要较多标注、训练/验证成本高，解释性和 source provenance 也更难维护。

### 5. Visual analytics + human-in-the-loop

把 KG 推理结果、source edges、候选修正和路径排序展示给专家，让专家接受、拒绝或修正。优点是适合研究 prototype 和工业审阅流程；缺点是论文评估需要把“系统性能”和“专家交互价值”分开说明。

KGTraceVis 的 UI 和 stable IDs 正适合这个方向。

## GPT Pro 讨论结论摘要

用户提供的 GPT Pro 讨论结论已经固化到 `docs/kgtracevis_revised_research_plan_cn.md`，核心建议可以概括为：

- 论文定位要从“自动 RCA”降到“knowledge-constrained evidence analysis and traceability”。
- MVTec/DS-MVTec 不应被说成 verified factory RCA benchmark，只能承担视觉 evidence、consistency/correction 和 plausible explanation。
- TEP 应作为主 RCA/path-ranking 量化方向，因为 fault labels、variables 和 process units 更容易映射。
- Wafer 在缺少私有 process logs 和专家 RCA labels 时，应定位为 multimodal traceability case study。
- Adapter-vs-KG boundary 必须写清楚：adapter 输出 observed evidence，KGTracePipeline runtime computes candidate paths。
- Evaluation 主表应优先放 schema validity、entity linking、consistency/correction、TEP path hit/MRR 和 relation-weighted ablation。

## 下策：强行包装成自动工业 RCA

做法：

- 把 MVTec/wafer 的人工 plausible reference 讲成真实根因标签。
- Adapter 或 example JSON 预置 root cause、top-k paths 或 `kg_analysis`。
- UI/API 主要展示静态 JSON，不强调 runtime recomputation。
- 论文 claim 写成“自动发现真实工业根因”。

问题：

- MVTec 缺少真实工厂流程和 verified root-cause labels，审稿风险很高。
- Adapter 预置答案会削弱 KGTracePipeline 的贡献。
- 数据和 KG 规模不足以支撑强 RCA claim。
- LLM/VLM 输出如果被当事实，会违反 source-constrained KG 边界。

结论：不建议。

## 中策：Source-constrained KG baseline + TEP 主量化

做法：

- 把 KGTraceVis 定位为统一 evidence + source-constrained KG reasoning + visual traceability。
- Adapter 只产出 observed evidence；`kg_analysis` 初始为空。
- KGTracePipeline runtime 计算 linking、consistency、corrections 和 candidate RCA paths。
- MVTec 做 visual evidence normalization、noise/correction 和 plausible explanation demo。
- TEP 做主 path-ranking evaluation，包括 top-k path hit、MRR 和 ablation。
- Wafer 做 image/log traceability case study；有私有标签后再升级 RCA evaluation。
- 每条 KG edge 和 reference 保留 source、evidence、confidence、review_status。

优点：

- 和当前仓库实现匹配，短期可落地。
- 论文 claim 克制但完整，不容易被“没有真实 RCA 标签”击穿。
- 可以用 TEP 做较可信的定量结果，用 MVTec/wafer 做系统覆盖和可视分析价值。
- 未来可自然升级到 Online Evidence Graph、probabilistic RCA 或 GNN。

结论：推荐。

## 上策：动态因果/概率 KG + 专家闭环

做法：

- 构建更完整的 source registry、review workflow 和 provenance sidecar。
- 在 TEP 或私有工业数据上构建 Online Evidence Graph，把时序变量、报警、设备状态和操作阶段纳入动态图。
- 引入 Bayesian Network、causal graph 或 temporal GNN 做概率 RCA/path ranking。
- 用专家反馈持续校准 confidence、edge weight 和 path ranking。

优点：

- 研究强度更高，更接近工业 RCA。
- 可以从 candidate path ranking 走向 probability-calibrated RCA。

问题：

- 需要更强数据、更多标签和专家 review。
- 当前组会和短期论文 v0 很难保证实现质量。
- 如果没有足够评估数据，复杂模型反而会降低可信度。

结论：可作为长期路线，不建议作为当前承诺。

## 推荐路线

推荐采用中策，并把上策作为 future work：

```text
当前论文/组会：
  unified evidence schema
  + source-constrained KG
  + runtime KGTracePipeline
  + TEP 主量化
  + MVTec/wafer 边界清晰 demo

后续扩展：
  Online Evidence Graph
  + probabilistic RCA / causal graph
  + expert feedback calibration
```

这样既能保留 KGTraceVis 的完整系统贡献，也避免过度承诺真实工业根因发现。

## References

- Knowledge Graphs in Manufacturing and Production survey: <https://arxiv.org/abs/2012.09049>
- Industrial RCA using Knowledge Graphs: <https://www.sciencedirect.com/science/article/pii/S1877050922003015>
- Interactive RCA with Bayesian Networks and Knowledge Graphs: <https://arxiv.org/abs/2402.00043>
- PIXAL anomaly reasoning visual analytics: <https://arxiv.org/abs/2205.11004>
- Tennessee Eastman process original reference: <https://users.abo.fi/~khaggblo/RS/Downs.pdf>
- Extended Tennessee Eastman dataset paper: <https://www.sciencedirect.com/science/article/pii/S0098135421000594>
