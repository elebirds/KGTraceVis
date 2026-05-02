# 2026-05-02 组会 Demo 说明

这是一个基于手工整理 example evidence 和仓库内 CSV KG 的 v0 现场 demo。它的目标是展示 pipeline 的完整性，而不是提供 paper-grade 的数据集覆盖，也不是给出经过验证的工业 root-cause labels。

系统边界需要在演示时说清楚：adapters/manual demo annotations provide observed anomaly evidence only，例如 object、anomaly_type、location、morphology、variables、log_events。当前 canonical input 是 `observations`；top-level `anomaly_type` / `location` / `morphology` 和 `raw_evidence.variables` / `raw_evidence.log_events` 只保留为 legacy compatibility，方便旧 payload 继续跑 demo。example JSON 里的 `kg_analysis` 为空，root cause 也不是输入字段。`KGTracePipeline` computes linking/consistency/corrections/candidate RCA paths at runtime。

## Streamlit 演示流程

运行：

```bash
uv run streamlit run src/kgtracevis/app/streamlit_app.py
```

建议按下面的 case 顺序演示：

1. `MVTEC: mvtec_0001 - ds_mvtec_example.json` 输入只包含视觉缺陷 evidence。app 运行后展示 KG entity linking、一致性判断，以及 KGTracePipeline 计算出的 candidate RCA paths。MVTec demo RCA source edges 是 curated plausible references；不要把 displayed paths 说成预置 placeholders 或 MVTec 原生的 factory root-cause labels。
2. `MVTEC: mvtec_noisy_0001 噪声演示 - mvtec_noisy_morphology_demo.json` 输入只包含一个 intentionally noisy scratch evidence，把 morphology 设为 `surface`。consistency checker 应该标出 `anomaly_type` 和 `morphology`，然后基于 supporting KG edge 提出 `Linear morphology` correction candidate。
3. `TEP: tep_0001 - tep_example.json` 输入包含 time-series process variable evidence。pipeline 运行后展示 process-unit linking 和一条 candidate process-fault path。
4. `WAFER: wafer_0001 - wafer_example.json` 输入包含 multimodal image/log evidence。pipeline 运行后展示 morphology、location、log-event consistency，以及 wafer process provenance。

在 app 里，可以按 Step 0-6 的线性流水线展示：

- 输入边界与 observed evidence，
- adapter 输出和运行前为空的 `kg_analysis`，
- linked entities 和 candidate matches，
- consistency score、field-pair checks 和 inconsistent_fields，
- correction candidates 与 supporting KG edge，
- candidate top-k RCA paths 与 path source edge provenance，
- 最终带运行时分析结果的 evidence payload。

## Reproducibility Commands

```bash
uv run python scripts/run_examples.py
uv run python scripts/run_kg_qa.py --output outputs/kg_qa_report.json
uv run python scripts/run_path_ranking.py
uv run python scripts/run_path_ranking.py --evidence data/examples/mvtec_noisy_morphology_demo.json --write-json
uv run python scripts/run_noise_experiment.py
uv run python scripts/run_experiment_suite.py
```

`outputs/` 和 `runs/` 下生成的文件是 reproducibility artifacts。没有经过额外整理和验证之前，不应把它们展示为最终 paper experiment results。

## Reference / Provenance 边界

参考标签和 plausible RCA reference 单独放在 `data/references/`，不进入
adapter 输出的 evidence JSON。演示时可以强调：

- `data/examples/*.json` 是输入 evidence，`kg_analysis` 初始为空。
- `observations` 是 KG reasoning 的 canonical observed-evidence contract；legacy top-level fields 只作为兼容旧 JSON 的 fallback。
- `data/kg/*.csv` 是运行时 KG reasoning 使用的知识边。
- `data/references/*.csv` 是评估或演示边界材料，用来说明哪些 path/correction
  可以被视为 reference，但不是 adapter 偷塞进去的答案。
- MVTec 和 wafer reference 当前主要是 plausible/demo reference；TEP 是后续主
  RCA/path-ranking evaluation 的优先方向。
