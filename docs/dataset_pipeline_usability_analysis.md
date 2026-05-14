# KGTraceVis 原始数据样本管线可用性与结果合理性分析

本文记录一次面向当前实现的可复现实验：分别使用 MVTec/DS-MVTec、
WM811K 和 TEP 的原始数据样本，经 producer 生成 normalized records，
再由 adapter 生成 Evidence JSON，最后进入 `KGTracePipeline` 完成实体
链接、一致性检查、修正候选、RCA/top-k path 输出。

本文的 RCA/path 结论均按 KGTraceVis 当前边界表述为
candidate/plausible explanation。除 TEP fault label 可作为 benchmark
reference 外，MVTec 和 WM811K 不被表述为 verified process RCA 数据集。

## 结论摘要

当前系统已经具备三类数据的端到端 v0 闭环：

```text
raw dataset sample
-> producer record
-> Evidence adapter
-> validated Evidence JSON
-> KG entity linking
-> consistency / correction
-> top-k candidate paths
-> ranked_root_causes
```

本次实测结果：

| Dataset | Raw source | Producer | Adapter/Pipeline status | Main finding |
| --- | --- | --- | --- | --- |
| MVTec / DS-MVTec | `data/external/Defect_Spectrum/DS-MVTec` | official Amazon PatchCore capsule artifact | 3 cases complete | Evidence/path contract 可用；PatchCore 预测为 anomalous，并能从预测 mask 派生 surface/spot 或 surface/linear evidence |
| WM811K | `data/external/wm811k/test.pkl` | public ResNet34 checkpoint | 3 cases complete | Pattern classification 与 wafer Evidence 链路可用；Scratch case 触发一致性问题和修正候选，说明 KG 约束检查确实在工作 |
| TEP | `data/raw/tep/*.csv` | TEP RBC producer | raw CSV -> Evidence -> Root-KGD RCA complete | 当前 native TEP RCA 已迁移 TEP_KG Root-KGD 运行时 ranking；不读取预生成 ranking artifacts，fault label 仅作评价 reference |

TEP 的 KG RCA 推理由 `TepRootKgdRcaProvider` 执行。它实现
`reason_root_causes()`，作为
`KGTracePipeline.root_cause_reasoner` 注入；其输出 metadata 中的 reasoner
字符串和 scoring method 均指向 `tep_root_kgd`。

## 数据组织

用户 `~/Downloads` 中已有 DS-MVTec/Defect Spectrum 数据，本次已移动到项目：

```text
data/external/Defect_Spectrum/        # 1.5GB, ignored by Git
data/external/Defect_Spectrum/DS-MVTec/
```

`~/Downloads` 中未发现 WM811K 表格文件；项目此前已缓存 public WM811K
Hugging Face table，本次整理到：

```text
data/external/wm811k/test.pkl         # 18MB, ignored by Git
```

TEP raw CSV 已在项目中：

```text
data/raw/tep/TEP_FaultFree_Training.csv
data/raw/tep/TEP_Faulty_Training.csv
```

生成产物位于：

```text
runs/dataset_pipeline_analysis/
```

## 运行命令与产物

### MVTec / DS-MVTec

先从 DS-MVTec capsule 原始目录构建 MVTec-like eval root：

```python
from pathlib import Path
from kgtracevis.experiments.mvtec_patchcore import build_ds_mvtec_subset_input

input_root, manifest = build_ds_mvtec_subset_input(
    dataset_root=Path("data/external/Defect_Spectrum"),
    output_root=Path("runs/dataset_pipeline_analysis/mvtec_raw_ds_subset"),
    object_names=["capsule"],
    max_good=1,
    max_defect_per_label=1,
)
```

再使用当前已缓存的 official Amazon PatchCore capsule artifact 生成 producer records。
该后端需要把 `patchcore-inspection/src` 加到 `PYTHONPATH`：

```bash
PYTHONPATH=artifacts/third_party/patchcore-inspection/src \
uv run python scripts/build_dataset_records.py \
  --dataset mvtec \
  --input-root runs/dataset_pipeline_analysis/mvtec_raw_ds_subset/input_root \
  --output-jsonl runs/dataset_pipeline_analysis/mvtec_patchcore_raw_records.jsonl \
  --model-backend amazon-patchcore \
  --object-checkpoint-root artifacts/third_party/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models \
  --max-cases 3 \
  --max-per-label 1 \
  --threshold-config configs/mvtec_patchcore_thresholds.json \
  --device cpu \
  --overwrite
```

Producer 输出：

```text
record_count=3
labels={crack: 1, faulty_imprint: 1, poke: 1}
```

### WM811K

使用 public WM811K table 和 public ResNet34 checkpoint 生成 producer records：

```bash
uv run python scripts/build_dataset_records.py \
  --dataset wm811k \
  --input data/external/wm811k/test.pkl \
  --output-jsonl runs/dataset_pipeline_analysis/wm811k_raw_records.jsonl \
  --model-backend torch-resnet34 \
  --checkpoint runs/real_model_pipeline/assets/wm811k/checkpoints/best_radai_resnet.pt \
  --model-source-repo radai-agent/radai-wm811k-defect-detection \
  --model-source-file best_radai_resnet.pt \
  --max-cases 3 \
  --max-per-label 1 \
  --seed 7 \
  --device cpu \
  --overwrite
```

Producer 输出：

```text
record_count=3
labels={Center: 1, Near-full: 1, Scratch: 1}
```

### TEP

从 TEP raw CSV 生成一个 RBC producer record：

```bash
uv run python scripts/build_dataset_records.py \
  --dataset tep \
  --input-root data/raw/tep \
  --output-jsonl runs/dataset_pipeline_analysis/tep_rbc_sample.jsonl \
  --model-backend tep-rbc \
  --faults 1 \
  --tep-window-size 20 \
  --tep-max-runs-per-fault 1 \
  --tep-fault-free-max-rows 1000 \
  --tep-row-stride 200 \
  --max-cases 1 \
  --overwrite
```

Producer 输出：

```text
record_count=1
labels={1: 1}
```

### Adapter + KG Pipeline

三类 producer records 均通过同一 adapter pipeline 进入 KG 推理。本次为了避免
依赖本地 Neo4j 服务，显式加载 seed CSV KG：

```python
from pathlib import Path

from kgtracevis.core import KGTracePipeline
from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline

root = Path("runs/dataset_pipeline_analysis")
graph = KnowledgeGraph.from_default_paths()

run_adapter_pipeline(
    root / "mvtec_patchcore_raw_records.jsonl",
    root / "mvtec_patchcore_raw_adapter_pipeline",
    dataset="mvtec",
    top_k=3,
    overwrite=True,
    pipeline=KGTracePipeline(graph=graph),
)

run_adapter_pipeline(
    root / "wm811k_raw_records.jsonl",
    root / "wm811k_raw_adapter_pipeline",
    dataset="wafer",
    top_k=3,
    overwrite=True,
    pipeline=KGTracePipeline(graph=graph),
)

run_adapter_pipeline(
    root / "tep_rbc_sample.jsonl",
    root / "tep_adapter_pipeline",
    dataset="tep",
    top_k=3,
    overwrite=True,
    pipeline=build_pipeline(graph=graph),
)
```

主要产物：

| Dataset | Records | Summary | Evidence JSON |
| --- | --- | --- | --- |
| MVTec | `runs/dataset_pipeline_analysis/mvtec_patchcore_raw_records.jsonl` | `runs/dataset_pipeline_analysis/mvtec_patchcore_raw_adapter_pipeline/adapter_pipeline_summary.json` | `runs/dataset_pipeline_analysis/mvtec_patchcore_raw_adapter_pipeline/evidence/` |
| WM811K | `runs/dataset_pipeline_analysis/wm811k_raw_records.jsonl` | `runs/dataset_pipeline_analysis/wm811k_raw_adapter_pipeline/adapter_pipeline_summary.json` | `runs/dataset_pipeline_analysis/wm811k_raw_adapter_pipeline/evidence/` |
| TEP | `runs/dataset_pipeline_analysis/tep_rbc_sample.jsonl` | `runs/dataset_pipeline_analysis/tep_adapter_pipeline/adapter_pipeline_summary.json` | `runs/dataset_pipeline_analysis/tep_adapter_pipeline/evidence/` |

## MVTec / DS-MVTec 样本链路

### 原始样本

本次选取 DS-MVTec capsule 的真实原始图片和 mask，经 symlink/copy 组织成
MVTec-like input tree。示例：

| Label | Raw image | Raw mask |
| --- | --- | --- |
| `crack` | `data/external/Defect_Spectrum/DS-MVTec/capsule/image/crack/000.png` | `data/external/Defect_Spectrum/DS-MVTec/capsule/mask/crack/000_mask.png` |
| `faulty_imprint` | `data/external/Defect_Spectrum/DS-MVTec/capsule/image/faulty_imprint/000.png` | `data/external/Defect_Spectrum/DS-MVTec/capsule/mask/faulty_imprint/000_mask.png` |
| `poke` | `data/external/Defect_Spectrum/DS-MVTec/capsule/image/poke/000.png` | `data/external/Defect_Spectrum/DS-MVTec/capsule/mask/poke/000_mask.png` |

### Producer record

以 `crack` 样本为例，producer record 摘要如下：

```json
{
  "dataset": "mvtec",
  "case_id": "mvtec_capsule_test_crack_000",
  "object": "capsule",
  "defect_type": "crack",
  "image_path": "runs/dataset_pipeline_analysis/mvtec_raw_ds_subset/input_root/capsule/test/crack/000.png",
  "gt_mask_path": "runs/dataset_pipeline_analysis/mvtec_raw_ds_subset/input_root/capsule/ground_truth/crack/000_mask.png",
  "detector": {
    "backend": "amazon-patchcore",
    "checkpoint": "artifacts/third_party/patchcore-inspection/models/IM320_WR50_L2-3_P001_D1024-1024_PS-3_AN-1/models/mvtec_capsule",
    "pred_score": 2.5804691314697266,
    "pred_label": "anomalous"
  },
  "mask_stats": {
    "image_shape": [320, 320],
    "area": 353,
    "area_ratio": 0.003447265625,
    "component_count": 1,
    "bbox": [108, 64, 129, 85],
    "eccentricity": 0.48117838177663375
  }
}
```

注意：这里 `gt_mask_path` 来自 DS-MVTec 原始标注，但 producer 的
`mask_stats` 来自当前 PatchCore 预测 mask。PatchCore 对这组三个 DS capsule
defect 均输出 anomalous，并生成非空预测 mask，因此 adapter 能进一步派生
location、morphology 和 severity。

### Adapter 输出 Evidence

| Case | Object | Anomaly type | Location | Morphology | Severity | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| `mvtec_capsule_test_crack_000` | `capsule` | `crack` | `surface` | `spot` | `0.0034` | `1.0` |
| `mvtec_capsule_test_faulty_imprint_000` | `capsule` | `faulty_imprint` | `surface` | `linear` | `0.0096` | `1.0` |
| `mvtec_capsule_test_poke_000` | `capsule` | `poke` | `surface` | `spot` | `0.0553` | `1.0` |

Evidence schema 和 adapter contract 是可用的：对象、缺陷标签、模型输出、
ground-truth mask 路径、heatmap/mask artifact 路径均被保留在 Evidence
及 raw evidence extra 中。PatchCore 预测 mask 进一步使视觉几何字段进入
KG reasoning，可用于 location/morphology consistency。

### KG 推理结果

| Case | Linked entities | Consistency | Top paths / RCA |
| --- | --- | --- | --- |
| `crack` | `CapsuleObject`, `CrackDefect`, `SurfaceLocation`, `SpotMorphology` | `1.0` | `CrackDefect -> MaterialDefect` score `0.4635`; `CrackDefect -> PackagingPressure` score `0.4305` |
| `faulty_imprint` | `CapsuleObject`, `FaultyImprintDefect`, `SurfaceLocation`, `LinearMorphology` | `1.0` | `FaultyImprintDefect -> TextureIrregularity` score `0.4305`; `FaultyImprintDefect -> GenericVisualDefectMechanism` score `0.3865` |
| `poke` | `CapsuleObject`, `PokeDefect`, `SurfaceLocation`, `SpotMorphology` | `1.0` | `PokeDefect -> HandlingDamage` score `0.4305`; `PokeDefect -> MechanicalContact` score `0.4305`; two-hop path via `MechanicalContact -> HandlingDamage` score `0.4215` |

MVTec path 输出合理地从 defect label 出发，返回带 source edge provenance 的
plausible mechanism。PatchCore 默认链路能提供非空预测
mask，并把 surface/spot 或 surface/linear 等视觉观测纳入 Evidence 与 KG
一致性检查。需要注意的是，这些路径仍然是 MVTec plausible RCA candidates，
不是原始数据集提供的 verified factory RCA。

## WM811K 样本链路

### 原始样本

WM811K 原始表格位于：

```text
data/external/wm811k/test.pkl
```

本次 producer 从表格中抽取 3 个 native labeled rows：

| Case | Source row | Native label |
| --- | --- | --- |
| `wm811k_row_174905` | `174905` | `Scratch` |
| `wm811k_row_211955` | `211955` | `Center` |
| `wm811k_row_250250` | `250250` | `Near-full` |

### Producer record

以 `Near-full` 样本为例：

```json
{
  "case_id": "wm811k_row_250250",
  "source_table": "data/external/wm811k/test.pkl",
  "source_row_index": 250250,
  "native_failure_pattern": "Near-full",
  "predicted_pattern": "Near-full",
  "classification_confidence": 0.9807437062263489,
  "descriptor_stats": {
    "map_shape": [38, 38],
    "failed_die_count": 999,
    "defect_density": 0.6918282548476454,
    "derived_location": "wafer_surface",
    "derived_morphology": "dense_particles"
  }
}
```

Producer 使用 public ResNet34 checkpoint 做 pattern classification，同时用
wafer map feature extractor 生成 density、location、morphology 等稳定
观测字段。该 producer 明确 `produces_root_cause=false`。

### Adapter 输出 Evidence

| Case | Anomaly type | Location | Morphology | Severity | Confidence |
| --- | --- | --- | --- | --- | --- |
| `wm811k_row_174905` | `scratch` | `center` | `linear` | `0.0280` | `0.8608` |
| `wm811k_row_211955` | `center` | `center` | `clustered` | `0.0487` | `0.6105` |
| `wm811k_row_250250` | `nearfull` | `wafer_surface` | `dense_particles` | `0.6918` | `0.9807` |

### KG 推理结果

| Case | Linked entities | Consistency | Correction | Top paths / RCA |
| --- | --- | --- | --- | --- |
| `Scratch` | `WaferObject`, `WaferScratchDefect`, `WaferCenterLocation`, `WaferLinearMorphology` | `0.7` | 1 candidate | `WaferScratchDefect -> LinearScratchSignature -> HandlingScratch` score `0.4105`; `... -> WaferTransferMisalignment` score `0.4105` |
| `Center` | `WaferObject`, `CenterDefect`, `WaferCenterLocation`, `WaferClusteredMorphology` | `1.0` | 0 | `CenterDefect -> CenterClusterSignature -> ProcessInterruption` score `0.4105`; `... -> ProcessNonuniformity` score `0.4105` |
| `Near-full` | `WaferObject`, `NearfullDefect`, `WaferSurface`, `DenseParticles` | `1.0` | 0 | `NearfullDefect -> GlueRemovalInsufficient` score `0.4965`; `NearfullDefect -> NearFullDenseSignature -> ParticleContamination` score `0.427` |

WM811K 链路的可用性较强：原始 table row、classifier 输出、wafer-map
descriptor、Evidence observations、KG linking 和 top-k path 能连成完整链路。

`Scratch` case 的 `consistency_score=0.7` 且生成 1 个 correction candidate，
说明系统没有只做展示，而是在用 KG constraints 检查 pattern/location 的组合。
这类结果对 review queue 很有价值：它提示用户检查“center + scratch + linear”
是否符合当前 wafer KG 约束，或是否需要补充/修正 KG 边。

## TEP 样本链路

### 原始数据与 producer record

TEP 从 raw CSV 生成 RBC producer record，并通过当前 Root-KGD runtime
执行 RCA ranking。输入 raw data path：

```text
data/raw/tep/TEP_Faulty_Training.csv
```

当前 producer/evaluation 默认参数已对齐到 TEP_KG 风格：

| Field | Value |
| --- | --- |
| `window_size` | `100` |
| `row_stride` | `25` |
| `n_components` | `18` |
| `fault_free_max_rows` | `None` |
| `model_backend` | `tep-rbc` |

Fault number 来自 TEP benchmark label，可用于评价 reference；native RCA
scoring 使用变量贡献与 KG support paths，不直接用 fault label 打分。

### TEP reasoner 确认

当前 TEP native 路径由如下配置注入：

```python
build_pipeline(graph=graph)
```

实际对象：

```text
pipeline.root_cause_reasoner: TepRootKgdRcaProvider
has reason_root_causes: true
RcaReasoningResult.scoring_method: tep_root_kgd
RcaReasoningResult.metadata:
  reasoner: tep_root_kgd
  uses_fault_number_for_scoring: false
```

所以，如果文档中要命名类，应写 `TepRootKgdRcaProvider`。

### 与 TEP_KG / RootLens 的差异定位

用户指出 KGTraceVis 的 TEP 实现按理应与 `~/code/TEP_KG`、RootLens 一致。
本次对比后，KGTraceVis 默认 TEP producer/evaluation 参数已对齐到 TEP_KG
正式评估视角：

```text
window_size=100
row_stride=25
fault_free_max_rows=None / 10000 sampled rows
pca_rank=18
Root-KGD graph nodes=140, edges=252
```

用 TEP_KG 原生逻辑跑 fault 1/2/6 的第一个 run，Root-KGD top-1 均命中：

| Fault | TEP_KG default RBC top variables | TEP_KG Root-KGD top-1 |
| --- | --- | --- |
| 1 | `xmv_9`, `xmeas_19`, `xmeas_29`, `xmeas_20`, `xmeas_16` | `faultanchor:stream_4_ac_ratio` |
| 2 | `xmeas_30`, `xmeas_24`, `xmeas_34`, `xmeas_28`, `xmeas_16` | `faultanchor:stream_4_b_composition` |
| 6 | `xmeas_1`, `manipulated_variable_3_a_feed`, `xmeas_19`, `xmeas_20`, `xmeas_29` | `faultanchor:stream_1_a_feed_loss` |

KGTraceVis 默认 TEP producer/evaluation 参数已对齐到上述 TEP_KG 风格，并通过
`TepRootKgdRcaProvider` 在运行时调用移植后的 Root-KGD ranking。刚重新运行的
native 评估结果如下：

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir /tmp/kgtracevis_tep_sample_ZpxYQa \
  --raw-data-dir data/raw/tep \
  --faults 1,2,6 \
  --max-runs-per-fault 1 \
  --max-cases 3 \
  --top-k 5 \
  --overwrite
```

```text
summary_path = /tmp/kgtracevis_tep_sample_ZpxYQa/tep_rca_evaluation_summary.json
tep_rca_reasoner = "tep_root_kgd"
window_size=100, row_stride=25, n_components=18, top_k=5
fault_free_max_rows=None
```

当前 Root-KGD runtime 指标：

```text
case_count = 3
top1_root_cause_accuracy = 1.0000
top3_root_cause_accuracy = 1.0000
top5_root_cause_accuracy = 1.0000
MRR = 1.0000
path_hit_rate = 1.0000
```

当前逐 case 结果：

| Fault | Expected RCA | KGTraceVis native top-1 | Expected rank | Hit |
| --- | --- | --- | --- | --- |
| 01 | `faultanchor:stream_4_ac_ratio` | `faultanchor:stream_4_ac_ratio` | 1 | yes |
| 02 | `faultanchor:stream_4_b_composition` | `faultanchor:stream_4_b_composition` | 1 | yes |
| 06 | `faultanchor:stream_1_a_feed_loss` | `faultanchor:stream_1_a_feed_loss` | 1 | yes |

### TEP full fault-set evaluation

进一步检查 `data/raw/tep/TEP_Faulty_Training.csv` 后，当前本地 raw CSV 覆盖
fault 1-20，每个 fault 有 500 个 simulation runs；本地文件中没有 fault 21。
因此这里的 full fault-set 指当前 raw CSV 可评估的 20 个 fault。

单 run smoke：

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/tep_root_kgd_full_fault_set_20260514_220404 \
  --raw-data-dir data/raw/tep \
  --faults 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21 \
  --max-runs-per-fault 1 \
  --top-k 5 \
  --overwrite
```

```text
case_count = 20
top1_root_cause_accuracy = 0.8000
top3_root_cause_accuracy = 0.9000
top5_root_cause_accuracy = 0.9000
MRR = 0.8417
path_hit_rate = 0.9000
```

三 run smoke：

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/tep_root_kgd_fault_set_3runs_20260514_220500 \
  --raw-data-dir data/raw/tep \
  --faults 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20 \
  --max-runs-per-fault 3 \
  --top-k 5 \
  --overwrite
```

```text
case_count = 60
top1_root_cause_accuracy = 0.8667
top3_root_cause_accuracy = 0.9167
top5_root_cause_accuracy = 0.9167
MRR = 0.8889
path_hit_rate = 0.9167
```

三 run 按 fault 聚合：

| Fault | Cases | Top-1 hits | Top-5 hits | Observation |
| --- | ---: | ---: | ---: | --- |
| 1-9 | 27 | 27 | 27 | 全命中 |
| 10 | 3 | 2 | 3 | run 1 top-1 偏向 `faultanchor:stream_2_feed_temperature`，expected rank 3 |
| 11-14 | 12 | 12 | 12 | 全命中 |
| 15 | 3 | 1 | 3 | miss 时 top-1 偏向 `faultanchor:stream_2_feed_temperature`，expected rank 2 |
| 16-17 | 6 | 6 | 6 | 全命中 |
| 18 | 3 | 1 | 1 | miss 时 top-1 偏向 `faultanchor:stream_2_feed_temperature`，需要继续诊断 condenser family 竞争 |
| 19 | 3 | 3 | 3 | 全命中 |
| 20 | 3 | 0 | 0 | 当前 Root-KGD asset 中没有 fault 20 对应 anchor，evaluation fallback expected 为 `Fault20` |

因此，当前 TEP 结果应分层表述：

1. **三 case sanity**：fault 01/02/06 已 top-1 全命中，验证 producer ->
   Evidence -> Root-KGD runtime 链路成立。
2. **20 fault / 60 case smoke**：整体 top1=0.8667、top5=0.9167，说明迁移后的
   Root-KGD runtime 已具备可用 RCA 能力。
3. **剩余问题**：fault 10/15/18 是相邻 thermal/feed-temperature anchor 竞争；
   fault 20 是 KG asset/reference coverage 问题，不能简单算作模型排序错误。

当前 KGTraceVis TEP producer/evaluation 默认参数已对齐到上述 TEP_KG 风格：
`window_size=100`、`row_stride=25`、`n_components=18`、
`fault_free_max_rows=None`。当前 native evaluation 会通过
`TepRootKgdRcaProvider` 调用移植后的 Root-KGD `rank_scenario()`，并使用
`data/kg/tep_root_kgd/` 中的 graph、relation family 参数、trained edge weights、
anchor discriminators、dynamic feature signatures 和 anchor memory profiles。
可复现默认 evaluation 命令为：

```bash
uv run python scripts/evaluate_tep_rca.py \
  --output-dir runs/tep_rca_eval_native \
  --raw-data-dir data/raw/tep \
  --faults 1,2,6 \
  --max-runs-per-fault 1 \
  --overwrite
```

当前迁移后的结构是：

1. **TEP producer** 从 raw CSV 生成当前样本窗口的 PCA/RBC residual contribution，
   并写入 `channel_contributions`、`graph_contributions` 和
   `root_kgd_dynamic_features`。
2. **Evidence adapter** 只负责 schema 化，不直接写 root cause。
3. **KGTracePipeline RCA stage** 使用 `TepRootKgdRcaProvider` 从当前 Evidence
   读取 contributions/features，调用 Root-KGD runtime ranking。
4. **Top-k output** 将 Root-KGD ranking rows 转成统一的
   `ranked_root_causes` 和 `top_k_paths`，并保留 source edge/provenance 供前端和
   feedback 审阅。

Root-KGD runtime 使用：
   - `root_kgd.rank_scenario()`
   - propagation graph
   - relation family weights
   - trained edge weights
   - anchor discriminators
   - dynamic feature signatures
   - anchor memory profiles
   - candidate role/type bias 与多组 tie-break adjustments

因此，当前最准确的结论已更新为：

```text
RBC/producer 与 TEP_KG 风格参数对齐；
KGTraceVis native TEP RCA 现在通过 TepRootKgdRcaProvider 运行移植后的
Root-KGD ranking；
TEP_KG/RootLens 已生成的 ranking 文件只适合作为 parity fixture，不属于
producer -> adapter -> Evidence -> KG reasoning 的运行时输入。
```

## 横向可用性分析

| 能力 | MVTec / DS-MVTec | WM811K | TEP |
| --- | --- | --- | --- |
| 原始数据组织 | 已移动到 `data/external/Defect_Spectrum` | 已整理到 `data/external/wm811k/test.pkl` | 已在 `data/raw/tep` |
| Producer | official Amazon PatchCore 可运行，输出 anomalous score、预测 mask 和几何统计 | ResNet34 classifier 可运行，输出 pattern + confidence | RBC producer 可运行，输出变量贡献 |
| Adapter -> Evidence | 可用；保留 raw image/mask/producer artifacts | 可用；保持 `wm811k` -> `wafer` 边界 | 可用 |
| Entity linking | object/defect 可用 | pattern/location/morphology 可用 | process/fault/variables 可用但变量有歧义 |
| Consistency | 当前样本 1.0，且包含 PatchCore 派生 location/morphology | Center/Near-full 为 1.0；Scratch 为 0.7 且有 correction | 0.4，说明 TEP KG constraints 仍需补齐 |
| Top-k path | 可用，plausible visual mechanisms | 可用，plausible wafer mechanisms | 可用，Root-KGD support paths |
| RCA 合理性 | 只支持 plausible explanation；检测模型需校准 | 候选机制合理，可进入 review | Root-KGD runtime 已接入；需要用完整 fault set 做论文级统计 |

## 结果合理性分层

1. **Evidence-level validity**：三类 raw-derived records 都能生成 schema-valid
   Evidence，并保留 source path / source row / raw CSV provenance。
2. **Producer reliability**：MVTec official Amazon PatchCore、WM811K ResNet34
   与 TEP RBC producer 均能产出可进入 Evidence 的观测字段；MVTec 的
   PatchCore mask 还能补充 location/morphology evidence。
3. **KG-level consistency**：WM811K 展示出有效约束检查；TEP consistency 暴露
   KG/alias/constraint 不足；MVTec 当前 PatchCore 样本 consistency 表现稳定。
4. **RCA/path-level plausibility**：MVTec/WM811K paths 是可审阅候选机制；
   TEP path 输出来自 Root-KGD runtime ranking；对齐 TEP_KG 风格窗口后应继续用
   完整 fault set 做论文级统计。

## 建议后续工作

1. MVTec 默认使用 official Amazon PatchCore 后，建议继续对更多 DS-MVTec
   object 做 per-object threshold calibration 和 batch smoke，避免只看 capsule。
2. MVTec adapter/producer 可考虑在 analysis 文档中同时报告 `gt_mask_path`
   geometry 与 detector mask geometry，但必须明确哪个是标注、哪个是模型输出。
3. 对 WM811K Scratch consistency issue 追踪 correction candidate，检查是 KG
   约束太窄还是 descriptor 派生 location 需要更细。
4. TEP 默认评估参数已改为更接近 TEP_KG：`window_size=100`、
   `row_stride=25`、`n_components=18`、`fault_free_max_rows=None`。后续实验应
   继续扩展到完整 fault set。
5. 在后续前端/文档中统一写法：`TepRootKgdRcaProvider` 是唯一 TEP RCA
   实现类，`tep_root_kgd` 是 reasoner/scoring method。
