# brainstorm: 接入 TEP RCA 推理

## Goal

调研如何参考 `/Users/hhm/code/TEP_KG` 与 `/Users/hhm/code/RootLens`，把 TEP 数据集的 RCA 推理流程统一进当前 KGTraceVis 系统，并明确与另一个正在进行的 KG 建设统一工作的边界。

## What I Already Know

* 用户希望本轮先调研现状，不直接实现。
* 当前系统已经包含 KG、证据、路径排序、示例脚本、Neo4j/Postgres runtime 等模块。
* 另一个 Agent 正在接入和统一 KG 建设部分，因此本任务应聚焦 RCA 推理消费侧、数据接口和系统集成边界，避免改动 KG 构建流程。
* 当前 KGTraceVis 已有 `TepSemanticLiftExtractor` / `TepVariableMappingExtractor` 和 `scripts/build_source_kg.py`，KG 建设接入已开始成形。
* 当前 KGTraceVis 的 `data/kg/tep_nodes.csv` 与 `data/kg/tep_edges.csv` 仍为空壳，TEP route1/path ranking 需要 Neo4j 或 candidate overlay 才能产生有效结果。
* RootLens 的 route2 做法是离线消费 TEP_KG Root-KGD 产物，不在前端或 RootLens 内重算完整 Root-KGD。
* 本地 TEP_KG 的当前 ranking artifact 命名与 RootLens 脚本期望存在差异：RootLens 期望 `root_kgd_rankings.jsonl`，本地有 `root_cause_rankings.jsonl` 和 `outputs/rca/baseline_root_scores.csv`。
* 用户倾向将 TEP 流程统一到当前项目，而不是长期依赖外部 TEP_KG artifact。推荐目标态是把 TEP_KG 的流程迁入 KGTraceVis 的标准 Evidence/KG/workflow/service 边界，而不是保留外部仓库运行依赖。
* 用户进一步澄清：主干也应统一，TEP 不应表现成独立 `route2`。推荐改为统一 RCA Engine + scenario-specific scoring strategy；TEP 的过程传播逻辑作为评分策略，不作为第二条 pipeline。

## Assumptions (Temporary)

* TEP RCA 推理应复用当前系统已有的证据 schema、entity linking、consistency checking、path ranking 或 run service，而不是引入独立 schema。
* KG 建设统一 Agent 会负责 TEP KG 数据产物或导入链路；本任务需要定义 RCA 推理对这些产物的最小依赖。

## Open Questions

* TEP RCA 接入的首个 MVP 应偏向离线脚本/API，还是同时进入 Web 分析页？

## Requirements (Evolving)

* [x] 调研当前 KGTraceVis 中 TEP、RCA、路径推理相关模块和入口。
* [x] 调研 `/Users/hhm/code/TEP_KG` 中可复用的 TEP RCA 推理逻辑、数据格式和算法假设。
* [x] 调研 `/Users/hhm/code/RootLens` 中与 RCA 工作流、KG 查询、可视化或接口设计相关的实现。
* [x] 明确与 KG 建设统一工作的职责边界，避免重复构建 KG。
* [x] 输出接入建议、候选改动文件、风险和分阶段 MVP。
* [x] 形成把 TEP_KG 流程原生迁入 KGTraceVis 的分层实施方案。

## Acceptance Criteria (Evolving)

* [x] 形成现状调研结论，覆盖三个代码库。
* [x] 识别当前系统可复用入口和缺口。
* [x] 给出 RCA 推理接入建议和与 KG 建设工作的边界。
* [x] 如进入实现阶段，补充 implement/check context。
* [x] 实现统一 `ranked_root_causes` 输出，不再把 TEP 表达为独立 route2。
* [x] 保留 `top_k_paths` 兼容字段。
* [x] 提供 TEP artifact bridge，将 TEP_KG 风格 RCA artifacts 映射为统一 root-cause ranking。

## Definition of Done (Team Quality Bar)

* Tests added/updated if implementation follows.
* Lint / typecheck / CI green if implementation follows.
* Docs/notes updated if behavior changes.
* Rollout/rollback considered if risky.

## Out of Scope

* 本轮不实现代码。
* 本轮不合并或重写 KG 建设流程。
* 本轮不引入未经来源约束的 TEP 因果事实。

## Technical Notes

* Research note: `research/current-state.md`.
* Pipeline design note: `research/unified-pipeline-design.md`; it has been revised away from route1/route2 toward unified `ranked_root_causes`.
* Initial implementation shape: bridge provider maps configured TEP_KG artifacts into the unified RCA candidate/ranking contract.
* Target implementation shape: migrate TEP_KG's RBC, propagation graph, Root-KGD ranking, evaluation, and artifact export into KGTraceVis-native modules under the shared schema/config/run-service conventions.
* Implemented MVP slice:
  * `AnalysisResult.ranked_root_causes` plus `RankedRootCause` / `RcaRankingResult`.
  * existing path ranking projects into unified root-cause candidates via `ranked_root_causes_from_paths`.
  * `KGTracePipeline` accepts an optional `RootCauseProvider`.
  * `TepRcaArtifactProvider` reads bridge-mode TEP ranking/contribution artifacts without hard-coded external paths.
  * service/run enrichment and Postgres payloads expose `ranked_root_causes` and `root_cause_candidate` review targets.
* Follow-up implementation slice:
  * `TepScenarioSelector` now derives explicit TEP artifact matching keys from KGTraceVis `Evidence`.
  * `TepRcaArtifactProvider` can match opaque TEP_KG `scenario_id` rows by observed `fault_number` + `simulation_run` metadata.
  * unscoped/global ranking rows are no longer attached to every TEP case unless explicitly enabled via config.
* Verification passed:
  * `uv run --extra dev pytest`
  * `uv run python scripts/run_examples.py`
  * `uv run --extra dev mypy src tests scripts`
  * `uv run --extra dev ruff check .`
