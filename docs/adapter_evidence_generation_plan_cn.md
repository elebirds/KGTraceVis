# Dataset Adapter 如何产出 Evidence JSON

状态：汇报用设计说明，面向 KGTraceVis 下一阶段 adapter 实现。

日期：2026-05-02。

本文回答一个核心问题：**每个数据集的 adapter 到底如何从现有模型/数据输出中产出统一
`Evidence JSON`，并交给 `KGTracePipeline` 做运行时推理？**

结论先行：

> Adapter 不是 root-cause predictor。Adapter 的职责是把模型输出、数据集标签、
> mask、变量贡献、日志事件等转换成带来源的 observed anomaly evidence items。
> `KGTracePipeline` 才基于这些 observations 做 entity linking、consistency checking、
> correction candidate generation 和 candidate RCA path ranking。

因此每个 adapter 都应遵守：

```text
raw data / model output
  -> dataset-specific adapter
  -> observations + raw_evidence + adapter metadata
  -> kg_analysis 初始为空
  -> KGTracePipeline runtime reasoning
```

禁止 adapter 输出：

```text
root_cause
top_k_paths
ranked_causes
kg_analysis.linked_entities
kg_analysis.correction_candidates
kg_analysis.top_k_paths
```

这些字段必须由运行时 KG pipeline 生成。

---

## 1. 统一 Adapter 输出合同

每个 adapter 输出一个 `Evidence` 对象，其中新一代主输入是 `observations`：

```json
{
  "case_id": "mvtec_0001",
  "dataset": "mvtec",
  "source": "image",
  "adapter": {
    "adapter_id": "mvtec_patchcore_ds_adapter",
    "adapter_version": "0.1.0",
    "produces_root_cause": false
  },
  "observations": [
    {
      "obs_id": "obs_mvtec_0001_morphology_001",
      "facet": "morphology",
      "name": "linear",
      "display_name": "Linear morphology",
      "value": "linear",
      "value_type": "categorical",
      "confidence": 0.85,
      "source_ref": "mask_geometry:eccentricity",
      "raw_ref": "raw_evidence.extra.mask_stats.eccentricity",
      "metadata": {
        "derived_from": "thresholded anomaly map / mask"
      }
    }
  ],
  "raw_evidence": {
    "description": "...",
    "extra": {}
  },
  "kg_analysis": {
    "linked_entities": [],
    "consistency_score": null,
    "inconsistent_fields": [],
    "correction_candidates": [],
    "top_k_paths": []
  }
}
```

推荐 facet 集合：

```text
object
anomaly_type / defect_type
location
morphology
severity
confidence
variable
variable_contribution
temporal_pattern
process_unit
spatial_pattern
log_event
alarm
operation_phase
```

每个 observation 必须尽量带：

- `obs_id`：稳定 ID，便于 linking、correction、feedback 指向它。
- `facet`：这个 observation 是什么类型的证据。
- `name`：KG linker 使用的规范候选字符串。
- `value`：数值、类别或描述值。
- `confidence`：来自模型 score、规则可信度或人工标注可信度。
- `source_ref`：这个 observation 从哪里来。
- `raw_ref`：如何回到原始证据。

---

## 2. MVTec / DS-MVTec Adapter

### 2.1 可用模型与数据来源

MVTec 原生适合工业视觉 anomaly detection / localization，不适合直接做真实 RCA。
因此 MVTec adapter 的目标是产出视觉观测证据：

```text
object
anomaly_type / defect_type
location
morphology
severity
confidence
description
```

推荐组合：

| 组件 | 作用 | 可产出 evidence |
| --- | --- | --- |
| Anomalib PatchCore | 经典视觉异常检测 baseline；输出 image-level score 和 localization map | `severity`、`confidence`、`image_region`、`heatmap_path` |
| Anomalib EfficientAD | 更快的 student-teacher anomaly detector，适合 demo 和实时感 | `severity`、`confidence`、`image_region`、`heatmap_path` |
| DefectSpectrum / DS-MVTec | 提供更丰富的缺陷语义、caption、mask | `anomaly_type`、`description`、`mask_path` |
| VLM caption/candidate parser | 可选弱证据组件；从整图、裁剪异常区域或 DefectSpectrum caption 生成描述和候选语义 | `description`、candidate `defect_type`、`location`/`morphology` hints |
| mask geometry rules | 从 mask/heatmap 区域计算形态和位置 | `location`、`morphology`、`severity` |

Anomalib 官方示例中，prediction 可以访问 `anomaly_map`、`pred_label` 和
`pred_score`。PatchCore 文档说明其通过 nearest-neighbor patch comparison 产生
anomaly scores，并保留 localization maps；EfficientAD 文档说明其使用 student-teacher
结构，适合快速 anomaly detection。DefectSpectrum 则提供语义丰富标注、caption、
mask/rgb_mask，适合补齐 defect type 和描述。

### 2.2 MVTec Adapter 流程

```text
image
  -> PatchCore / EfficientAD inference
  -> anomaly_map + pred_score
  -> threshold anomaly_map 得到 binary mask
  -> mask geometry feature extraction
  -> 结合 DS-MVTec label/caption
  -> 可选 VLM caption / candidate extraction
  -> observations
```

mask geometry 可计算：

| 几何特征 | observation |
| --- | --- |
| mask area ratio | `severity` |
| centroid near border | `location=edge` |
| centroid near center | `location=center` |
| object-specific area e.g. bottle body/neck | `location=surface/body/neck` |
| high eccentricity / elongated bbox | `morphology=linear` |
| compact connected component | `morphology=spot/blob` |
| many connected components | `morphology=scattered/multiple` |
| large coverage | `morphology=dense/region` |

### 2.3 可选 VLM 输出边界

VLM 可以作为 MVTec / DS-MVTec adapter 的可选语义辅助组件，但只能输出
needs-review 的弱 observation，不能作为工业事实或 RCA 来源。推荐使用场景：

- 对整张图或 cropped anomaly region 生成 caption / description。
- 从视觉描述中提取 candidate `defect_type`，例如 scratch、contamination、crack。
- 给出 `location` / `morphology` hint，例如 edge、surface、linear、spot-like。
- 辅助解析 DefectSpectrum caption，把自然语言 caption 转成候选 observation。

VLM 输出必须低权重、可追溯、可审核：

```json
{
  "obs_id": "obs_mvtec_0001_vlm_defect_type_001",
  "facet": "defect_type",
  "name": "scratch",
  "display_name": "VLM candidate scratch defect",
  "confidence": 0.45,
  "source_ref": "vlm_candidate:cropped_anomaly_region",
  "raw_ref": "raw_evidence.extra.vlm.caption",
  "metadata": {
    "annotation_type": "llm_candidate",
    "review_status": "auto",
    "model": "vlm_name_or_endpoint",
    "input_region": "cropped_anomaly_region",
    "derived_from": "image crop + DefectSpectrum caption"
  }
}
```

推荐映射规则：

| VLM 输出 | observation facet | 处理方式 |
| --- | --- | --- |
| caption / short description | `description` | 放入 `raw_evidence.description` 或 `observation.value`，不直接作为 KG 实体 |
| candidate defect name | `defect_type` / `anomaly_type` | 作为 `annotation_type=llm_candidate` 的候选，低 confidence |
| visual region phrase | `location` | 只作为 hint，优先级低于 mask geometry |
| shape phrase | `morphology` | 只作为 hint，优先级低于 mask geometry |
| root-cause phrase | 不产出 observation | 丢弃或记录为 rejected/untrusted raw note，不进入 RCA 字段 |

如果 VLM 与 mask geometry、DS label/caption 冲突，adapter 不应自动改写强来源证据；
冲突应保留给 `KGTracePipeline` 的 consistency/correction 逻辑和人工 review。

### 2.4 MVTec Adapter 输出示例

```json
{
  "adapter": {
    "adapter_id": "mvtec_patchcore_ds_adapter",
    "adapter_version": "0.1.0",
    "produces_root_cause": false
  },
  "observations": [
    {
      "obs_id": "obs_mvtec_0001_object_001",
      "facet": "object",
      "name": "bottle",
      "source_ref": "mvtec.category",
      "raw_ref": "raw_evidence.extra.category"
    },
    {
      "obs_id": "obs_mvtec_0001_anomaly_type_001",
      "facet": "anomaly_type",
      "name": "scratch",
      "display_name": "scratch defect",
      "confidence": 0.8,
      "source_ref": "defect_spectrum.caption_or_label",
      "raw_ref": "raw_evidence.description"
    },
    {
      "obs_id": "obs_mvtec_0001_location_001",
      "facet": "location",
      "name": "surface",
      "confidence": 0.75,
      "source_ref": "mask_geometry.centroid_region",
      "raw_ref": "raw_evidence.extra.mask_stats.centroid"
    },
    {
      "obs_id": "obs_mvtec_0001_morphology_001",
      "facet": "morphology",
      "name": "linear",
      "confidence": 0.85,
      "source_ref": "mask_geometry.eccentricity",
      "raw_ref": "raw_evidence.extra.mask_stats.eccentricity"
    },
    {
      "obs_id": "obs_mvtec_0001_severity_001",
      "facet": "severity",
      "name": "mask_area_ratio",
      "value": 0.034,
      "value_type": "score",
      "confidence": 0.9,
      "source_ref": "patchcore.anomaly_map",
      "raw_ref": "raw_evidence.extra.mask_stats.area_ratio"
    },
    {
      "obs_id": "obs_mvtec_0001_vlm_morphology_001",
      "facet": "morphology",
      "name": "linear",
      "display_name": "VLM candidate linear morphology",
      "confidence": 0.45,
      "source_ref": "vlm_candidate:cropped_anomaly_region",
      "raw_ref": "raw_evidence.extra.vlm.caption",
      "metadata": {
        "annotation_type": "llm_candidate",
        "review_status": "auto"
      }
    }
  ]
}
```

### 2.5 MVTec 不能产出的内容

MVTec adapter 不能输出：

```text
MechanicalContact
HandlingDamage
SurfaceWear
VLM-inferred root cause
root_cause
```

正确边界是：

```text
adapter:
  scratch + surface + linear + score + mask region

KGTracePipeline:
  ScratchDefect -> HAS_PLAUSIBLE_CAUSE -> MechanicalContact
```

也就是说，MVTec 只承担视觉 evidence normalization、consistency/correction 和
plausible explanation demo，不承担 verified factory RCA。

---

## 3. TEP Adapter

### 3.1 可用模型与数据来源

TEP 更适合作为主 RCA/path-ranking evaluation 场景，因为它天然有：

```text
time-series variables
measured variables / manipulated variables
fault number / fault type
process units
fault propagation
```

但 adapter 仍然不能把 `faultNumber` 作为 root-cause prediction 输出。`faultNumber`
应放在 reference/evaluation 文件中，用来评估 pipeline 的 candidate path 是否命中。

推荐组合：

| 组件 | 作用 | 可产出 evidence |
| --- | --- | --- |
| PCA / DPCA / RBC contribution | 经典过程监控；输出异常变量贡献 | `variable`、`variable_contribution`、`severity` |
| block PCA / process decomposition | 根据 process blocks 分析异常来源和传播 | `process_unit`、`temporal_pattern`、`variable_contribution` |
| DAE / VAE / LSTM autoencoder | reconstruction residual 作为变量异常分数 | `variable`、`variable_contribution`、`temporal_pattern` |
| classifier + SHAP/IG | 可选增强；给 fault-type probability 和变量 attribution | `fault_type_candidate` 只作为 weak observation，不作为 ground truth |

TEP 文献中常见做法是用 PCA/DPCA、contribution plot 或 reconstruction residual 找出
异常变量。近期 process decomposition + PCA 工作也强调 contribution map 可帮助识别
异常 measured variables 和 fault propagation。深度 anomaly detection 文献也把 TEP
视为长期标准 benchmark。

### 3.2 TEP Adapter 流程

```text
time-series window
  -> anomaly detector / PCA / autoencoder
  -> anomaly score by time
  -> variable contribution scores
  -> top-k abnormal variables
  -> trend detector
  -> optional variable-to-unit mapping
  -> observations
```

变量到 process unit 的映射可以有两种方式：

1. adapter 只输出 variable，KG 里通过 `XMEAS1 MEASURED_IN ReactorUnit` 推 unit。
2. adapter 根据官方变量表输出 process_unit observation，但必须标明来源：
   `source_ref=official_variable_table`。

第一种更干净，第二种更适合 demo 展示。

### 3.3 TEP Adapter 输出示例

```json
{
  "adapter": {
    "adapter_id": "tep_pca_contribution_adapter",
    "adapter_version": "0.1.0",
    "produces_root_cause": false
  },
  "observations": [
    {
      "obs_id": "obs_tep_0001_variable_001",
      "facet": "variable",
      "name": "XMEAS_1",
      "display_name": "A feed flow",
      "confidence": 0.92,
      "source_ref": "pca_contribution.top_variables",
      "raw_ref": "raw_evidence.variable_contributions.XMEAS_1"
    },
    {
      "obs_id": "obs_tep_0001_variable_contribution_001",
      "facet": "variable_contribution",
      "name": "XMEAS_1",
      "value": 0.31,
      "value_type": "score",
      "direction": "high",
      "confidence": 0.92,
      "source_ref": "pca_contribution.score",
      "raw_ref": "raw_evidence.variable_contributions.XMEAS_1"
    },
    {
      "obs_id": "obs_tep_0001_temporal_pattern_001",
      "facet": "temporal_pattern",
      "name": "increasing",
      "value": "increasing",
      "value_type": "categorical",
      "confidence": 0.78,
      "source_ref": "trend_detector.window_160_260",
      "raw_ref": "raw_evidence.extra.window"
    }
  ]
}
```

### 3.4 TEP 不能产出的内容

TEP adapter 不能输出：

```text
root_cause = FeedFlowDisturbance
fault_answer = IDV_6
top_k_paths
```

正确做法：

```text
adapter:
  XMEAS_1 abnormal, contribution=0.31, trend=increasing

reference file:
  case_id -> official/literature-supported fault reference

KGTracePipeline:
  XMEAS1 -> INDICATES -> ProcessFault -> HAS_PLAUSIBLE_CAUSE -> FeedFlowDisturbance
```

TEP 是最适合做主 path-ranking 量化的场景，但 fault labels 必须和 adapter 输出分开。

---

## 4. Wafer / WM-811K Adapter

### 4.1 可用模型与数据来源

公开 WM-811K 更适合 wafer map spatial pattern recognition 和 traceability demo，而不是
verified process RCA。公开资料显示，WM-811K 包含 811,457 wafer maps，其中一部分由
专家标注为 Center、Donut、Edge-Loc、Edge-Ring、Loc、Near-full、Random、Scratch、
None 等 pattern；但它不提供完整工艺日志和真实 process root cause。

推荐组合：

| 组件 | 作用 | 可产出 evidence |
| --- | --- | --- |
| CNN / ResNet / EfficientNet / lightweight CNN | wafer pattern classification | `spatial_pattern`、`confidence` |
| ViT / attention CNN | 处理 class imbalance 或增强 pattern recognition | `spatial_pattern`、`confidence`、saliency |
| classical spatial descriptors | 从 wafer map 直接提取空间形态 | `location`、`morphology`、`severity` |
| Grad-CAM / saliency / attention map | 可选解释模型关注区域 | `image_region`、`location` |
| log parser | 如果有私有或 demo logs | `log_event`、`alarm`、`operation_phase` |

对于公开 WM-811K，建议 adapter 主要产出：

```text
spatial_pattern
location
morphology
severity / defect_density
confidence
```

如果没有真实 log，不要伪装成 multimodal。可以用 demo-only synthetic log，但必须标：

```text
source_ref = synthetic_demo_log
annotation_type = demo_synthetic
```

### 4.2 Wafer Adapter 流程

```text
wafer map
  -> wafer pattern classifier
  -> class probability / spatial_pattern
  -> spatial descriptor extraction
  -> optional saliency / attention map
  -> optional log parser
  -> observations
```

空间 descriptor 可计算：

| descriptor | observation |
| --- | --- |
| defect density | `severity` |
| edge concentration | `location=edge` |
| center concentration | `location=center` |
| radial ringness | `morphology=ring-like` |
| long thin connected component | `morphology=linear/scratch-like` |
| global high coverage | `morphology=dense/near-full` |
| local cluster count | `morphology=clustered/local` |

### 4.3 Wafer Adapter 输出示例

```json
{
  "adapter": {
    "adapter_id": "wm811k_cnn_spatial_adapter",
    "adapter_version": "0.1.0",
    "produces_root_cause": false
  },
  "observations": [
    {
      "obs_id": "obs_wafer_0001_spatial_pattern_001",
      "facet": "spatial_pattern",
      "name": "nearfull",
      "display_name": "Near-full wafer map pattern",
      "confidence": 0.88,
      "source_ref": "cnn_classifier.predicted_class",
      "raw_ref": "raw_evidence.extra.pattern_logits"
    },
    {
      "obs_id": "obs_wafer_0001_location_001",
      "facet": "location",
      "name": "wafer_surface",
      "confidence": 0.82,
      "source_ref": "spatial_descriptor.coverage",
      "raw_ref": "raw_evidence.extra.defect_density_map"
    },
    {
      "obs_id": "obs_wafer_0001_morphology_001",
      "facet": "morphology",
      "name": "dense_particles",
      "confidence": 0.85,
      "source_ref": "spatial_descriptor.global_density",
      "raw_ref": "raw_evidence.extra.defect_density"
    },
    {
      "obs_id": "obs_wafer_0001_log_event_001",
      "facet": "log_event",
      "name": "ExampleAlarm",
      "confidence": 0.6,
      "source_ref": "synthetic_demo_log",
      "raw_ref": "raw_evidence.log_events[0]",
      "metadata": {
        "annotation_type": "demo_synthetic"
      }
    }
  ]
}
```

### 4.4 Wafer 不能产出的内容

公开 WM-811K adapter 不能输出：

```text
true_process_root_cause
equipment_failure
verified_recipe_issue
```

正确做法：

```text
adapter:
  nearfull pattern + dense morphology + wafer surface + optional log event

KGTracePipeline:
  NearfullDefect -> HAS_PLAUSIBLE_CAUSE -> GlueRemovalInsufficient

paper wording:
  candidate process issue explanation / traceability demo
```

只有在拿到私有 wafer process logs、lot history、tool/chamber records 和专家 review 后，
wafer 才能升级为正式 RCA evaluation。

---

## 5. 三类 Adapter 对比

| 数据集 | 最适合的模型/算法 | Adapter 可自动产出 | 需要规则/表格补充 | 不能产出 |
| --- | --- | --- | --- | --- |
| MVTec / DS-MVTec | PatchCore / EfficientAD + DS labels/captions；可选 VLM caption/candidate parser | anomaly score、heatmap/mask、defect label/caption、VLM weak candidates | mask geometry -> location/morphology；VLM hints must be reviewed | verified RCA / VLM root-cause |
| TEP | PCA/DPCA/RBC contribution、autoencoder residual | abnormal variables、contribution scores、trends | variable table / KG -> process unit | root cause answer / fault answer |
| Wafer / WM-811K | CNN/ResNet/EfficientNet/ViT classifier + spatial descriptors | spatial pattern、classification confidence、defect density | geometry rules -> location/morphology；log parser if available | verified process RCA |

---

## 6. 推荐实现优先级

### v0.1：汇报/演示可用

- 使用手工 demo records 或 DefectSpectrum-style metadata。
- adapter 生成 observation-first JSON。
- mask/spatial/time-series feature 可以先用规则或小样例模拟。
- FastAPI/未来 RootLens dashboard 展示 observations -> linking -> consistency -> correction -> path provenance。

### v0.2：MVTec 真实模型输出

- 接入 Anomalib PatchCore 或 EfficientAD。
- 保存 `anomaly_map` 和 `pred_score`。
- threshold anomaly_map 得到 mask。
- 加入 mask feature extractor。
- 使用 DefectSpectrum caption/label 补 defect type。
- 可选接入 VLM，对整图/裁剪异常区域和 DefectSpectrum caption 产出
  `annotation_type=llm_candidate`、`review_status=auto` 的弱 observation。

### v0.3：TEP 主实验

- 接入 PCA/DPCA contribution 或 autoencoder residual。
- 生成 top-k abnormal variables 和 contribution scores。
- 建立 TEP variable/unit/fault reference。
- 做 path hit/MRR 和 ablation。

### v0.4：Wafer traceability

- 接入 WM-811K pattern classifier 或使用已标注 pattern。
- 加入 spatial descriptors。
- 如无真实 logs，只做 pattern traceability；如有 logs，再做 multimodal case。

---

## 7. 汇报口径

可以这样讲：

> Adapter 的目标不是预测 root cause，而是把各类模型输出变成统一的 evidence items。
> 对 MVTec，PatchCore/EfficientAD 产生 anomaly map 和 score，DefectSpectrum/label/caption
> 提供 defect semantics，可选 VLM 只产生 caption、candidate defect type 和
> location/morphology hints，且必须标成 weak/needs-review evidence；mask geometry
> 规则产生 location 和 morphology。对 TEP，
> PCA/贡献图或 autoencoder residual 产生异常变量和贡献分数。对 wafer，CNN/ResNet/ViT
> 产生 spatial pattern 和 confidence，空间规则产生 location/morphology。所有这些
> observations 再交给 KGTracePipeline 进行运行时 KG 推理。

这能回答“JSON 怎么来的”，也能保护系统边界：

```text
model/adapter -> observed evidence
KGTracePipeline -> candidate explanation / candidate RCA paths
human review -> accepted/rejected feedback
```

---

## 8. References

- Anomalib getting started: <https://anomalib.readthedocs.io/en/v2.1.0/markdown/get_started/anomalib.html>
- Anomalib PatchCore docs: <https://anomalib.readthedocs.io/en/stable/markdown/guides/reference/models/image/patchcore.html>
- Anomalib EfficientAD docs: <https://anomalib.readthedocs.io/en/v2.0.0/markdown/guides/reference/models/image/efficient_ad.html>
- DefectSpectrum dataset page: <https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum>
- Defect Spectrum paper: <https://arxiv.org/abs/2310.17316>
- TEP process decomposition / PCA contribution map: <https://arxiv.org/abs/2409.11444>
- Deep anomaly detection on TEP: <https://arxiv.org/abs/2303.05904>
- WM-811K wafer pattern classes and imbalance discussion: <https://www.sciencedirect.com/science/article/abs/pii/S0925527324001324>
- Wafer defect pattern detection and classification discussion: <https://www.sciencedirect.com/science/article/abs/pii/S0957417423010461>
