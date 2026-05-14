# brainstorm: analyze dataset pipeline usability

## Goal

形成一份面向 KGTraceVis 当前实现状态的分析文档，分别引用 MVTec、WM811K/wafer、TEP 的样本，从原始/producer 样本进入 adapter，生成 Evidence JSON，再经过 KGTracePipeline 的实体链接、一致性、修正候选、RCA/top-k path 输出，分析系统可用性与结果合理性。

## What I already know

* 用户希望覆盖 `mvtec`、`wm811k`、`tep` 三条链路。
* 分析需要从样本开始，串到 producer、adapter、Evidence JSON、KG reasoning、RCA/top-k path。
* 输出应是一份可追踪分析文档。
* 项目已有 `data/examples/records/mvtec_records.jsonl`、`data/examples/records/wm811k_records.jsonl`、`data/processed/records/tep_rbc_smoke.jsonl` 等可用于复现的样本记录。
* 核心管线入口是 `src/kgtracevis/core/pipeline.py`。

## Assumptions (temporary)

* 若完整外部原始数据集或模型权重不在仓库中，文档使用仓库内已保留的 producer-output sample 作为可复现样本，并明确这不是完整 benchmark。
* 文档聚焦系统工程可用性与推理合理性，不重新宣称 MVTec/wafer 有 verified RCA labels。

## Open Questions

* 无阻塞问题；先基于当前仓库可复现样本生成文档。

## Requirements (evolving)

* 覆盖 MVTec、WM811K/wafer、TEP 三个场景。
* 每个场景说明样本来源、producer 记录、adapter 输出 Evidence、KG 推理输出、RCA/top-k path 结果。
* 区分 observed evidence、candidate/plausible RCA、verified label。
* 给出系统可用性、结果合理性和当前限制。

## Acceptance Criteria (evolving)

* [x] 新增分析文档，路径位于现有允许的文档目录。
* [x] 文档包含三类数据样本的具体 case/sample 引用。
* [x] 文档记录可复现命令或生成产物路径。
* [x] 文档明确当前推理结果的合理性边界。

## Definition of Done (team quality bar)

* Docs/notes updated if behavior changes or analysis is added.
* Commands used for evidence generation are recorded.
* No unsupported industrial causal claims are introduced.
* Generated outputs are kept under ignored `runs/`/`outputs/`/`artifacts/` where applicable.

## Out of Scope (explicit)

* 不训练或重新标定模型。
* 不下载完整大型外部数据集。
* 不修改核心 pipeline 行为。
* 不把 candidate/plausible RCA 改写为 verified RCA。

## Technical Notes

* Need inspect `scripts/run_adapter_pipeline.py`, `scripts/build_dataset_records.py`, and example records.
* Need run or reuse adapter pipeline outputs for representative samples.
* Analysis document written to `docs/dataset_pipeline_usability_analysis.md`.
* Generated reproducibility artifacts under `runs/dataset_pipeline_analysis/`.
* DS-MVTec raw data was moved from `~/Downloads/Defect_Spectrum` to ignored project path `data/external/Defect_Spectrum`.
* WM811K public table was organized at ignored project path `data/external/wm811k/test.pkl`.
* Raw-derived producer records:
  * `runs/dataset_pipeline_analysis/mvtec_patchcore_raw_records.jsonl`
  * `runs/dataset_pipeline_analysis/wm811k_raw_records.jsonl`
  * `runs/dataset_pipeline_analysis/tep_rbc_sample.jsonl`
* MVTec default analysis uses official Amazon PatchCore via `amazon-patchcore` backend and `PYTHONPATH=artifacts/third_party/patchcore-inspection/src`.
* Runtime MVTec model preset defaults now prioritize PatchCore over EfficientAD/STFPM, and the API default model-asset download is `mvtec-patchcore`.
* TEP native RCA implementation is `TepNativeRcaProvider`; its result metadata reports `reasoner=tep_native_graph` and `scoring_method=tep_native_kg`.
