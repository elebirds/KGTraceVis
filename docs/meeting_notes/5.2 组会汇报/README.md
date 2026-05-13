# 5.2 组会汇报材料导航

本目录把 KGTraceVis 近期讨论、GPT Pro 讨论结论和已有中文文档整理成一套可直接用于组会汇报的材料。核心口径是：KGTraceVis 不再训练一个新的异常检测模型，而是把图像、时间序列和日志异常输出转换成统一 evidence，再用 source-constrained KG（来源约束知识图谱）做可解释的一致性检查、修正候选和 RCA（Root Cause Analysis，根因分析）候选路径排序。

## 文件导航

- [01_论文定位与总体路线.md](01_论文定位与总体路线.md)：论文定位、四阶段路线、三个数据集分工、贡献边界。
- [02_Adapter如何产出EvidenceJSON.md](02_Adapter如何产出EvidenceJSON.md)：MVTec/DS-MVTec、TEP、Wafer adapter 如何从模型或规则输出 observation-first 的 Evidence JSON。
- [03_KGTracePipeline推理机制与不足.md](03_KGTracePipeline推理机制与不足.md)：当前 pipeline 的实际实现、为什么它仍是 keyword/entity linking + graph search baseline，以及下一步要升级什么。
- [04_主流KG_RCA方法与上中下三策.md](04_主流KG_RCA方法与上中下三策.md)：主流 KG+RCA 方法类别、GPT Pro 讨论结论、下策/中策/上策比较，并推荐中策。
- [05_组会汇报讲稿.md](05_组会汇报讲稿.md)：5-10 分钟中文汇报讲稿。

## 5-10 分钟汇报故事线

1. **研究问题**：工业异常检测输出很分散，图像、过程变量和日志各说各话；我们想解决的是异常之后的 evidence organization、knowledge-constrained reasoning 和 traceability review，而不是替代异常检测模型。
2. **总体方案**：adapter 把不同数据源转换成统一 Evidence JSON；KGTracePipeline 在运行时完成 entity linking、一致性检查、修正候选和候选 RCA 路径排序；FastAPI backend 负责把证据、推理链和 provenance 暴露给未来 RootLens dashboard。
3. **关键边界**：adapter 只产出 observed evidence，不产出 root cause；`kg_analysis` 初始为空；candidate paths 由 pipeline 运行时计算。
4. **数据集分工**：MVTec/DS-MVTec 做视觉 evidence normalization、consistency/correction 和 plausible explanation；TEP 是主 RCA/path-ranking 量化方向；wafer 做 image/log traceability case study，除非后续有私有 RCA 标签。
5. **当前实现**：已有 `KGTracePipeline` 串起 linker、checker、correction generator 和 path ranker；当前是可运行 v0 baseline，不是 paper-grade causal model。
6. **下一阶段策略**：推荐中策，即在 source-constrained KG + relation-weighted path ranking 基础上增强 TEP 量化、noise experiment、annotation taxonomy 和 provenance review，而不是夸大 MVTec RCA。

## 必须保持的边界

- MVTec 不提供 verified factory RCA ground truth；只能说 curated plausible references 或 candidate explanations。
- Adapter/manual annotation 不能把 root cause、top-k paths、ranked causes 写入输入 evidence。
- KGTracePipeline 的输出是 candidate/plausible RCA paths，不是最终事实断言。
- TEP 是最适合做定量 RCA/path-ranking 的方向；wafer 在缺少可靠标签时以 traceability/case-study 为主。
- LLM/VLM 只能作为 candidate adapter，不是工业事实 authority。
