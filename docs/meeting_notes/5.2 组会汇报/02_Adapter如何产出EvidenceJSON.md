# 02 Adapter 如何产出 Evidence JSON

## 一句话结论

Adapter 不是 root-cause predictor。Adapter 的职责是把模型输出、数据集标签、mask、变量贡献、日志事件等转换成带来源的 observed anomaly evidence items；`KGTracePipeline` 才基于这些 observations 做 runtime KG reasoning（运行时知识图谱推理）。

推荐数据流：

```text
raw data / model output
  -> dataset-specific adapter
  -> observations + raw_evidence + adapter metadata
  -> kg_analysis 初始为空
  -> KGTracePipeline runtime reasoning
```

Adapter 禁止输出：

```text
root_cause
top_k_paths
ranked_causes
kg_analysis.linked_entities
kg_analysis.correction_candidates
kg_analysis.top_k_paths
```

## 统一输出合同

每个 adapter 输出一个统一 Evidence JSON。当前建议以 `observations` 作为 canonical observed-evidence contract（规范观测证据合同），同时保留 legacy top-level fields 供旧 payload 和 demo fallback 使用。

每个 observation 尽量包含：

- `obs_id`：稳定 ID，便于 linking、correction 和 feedback 指向它。
- `facet`：证据类型，例如 object、anomaly_type、location、morphology、variable、log_event。
- `name`：KG linker 使用的候选字符串。
- `value`：数值、类别或描述。
- `confidence`：来自模型 score、规则、人工标注或弱语义组件。
- `source_ref`：observation 从哪里来。
- `raw_ref`：如何回到原始证据字段。

推荐 facet：

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

## MVTec / DS-MVTec Adapter

MVTec 原生适合 anomaly detection / localization（异常检测与定位），不适合直接做真实工厂 RCA。它应产出视觉观测证据：

```text
object
anomaly_type / defect_type
location
morphology
severity
confidence
description
```

可用组件：

| 组件 | 作用 | 可产出 evidence |
| --- | --- | --- |
| Anomalib PatchCore | 图像异常检测 baseline，输出 score 和 localization map | severity、confidence、image_region、heatmap_path |
| Anomalib EfficientAD | 更快的 student-teacher detector，适合 demo | severity、confidence、image_region、heatmap_path |
| DefectSpectrum / DS-MVTec | 更丰富的缺陷语义、caption、mask | anomaly_type、description、mask_path |
| mask geometry rules | 从 mask/heatmap 计算形态和位置 | location、morphology、severity |
| VLM caption/candidate parser | 可选弱证据；从图像或裁剪区域生成描述和候选语义 | description、candidate defect_type、location/morphology hints |

建议流程：

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

Mask geometry 可以把 area ratio 映射到 severity，把 centroid 映射到 center/edge/surface，把 eccentricity 映射到 linear，把 compact component 映射到 spot/blob，把多连通区域映射到 scattered/multiple。

VLM（Vision-Language Model，视觉语言模型）只能产出低置信、可审核的弱 observation。若 VLM 生成 root-cause phrase，应丢弃或仅记录为 untrusted raw note，不能进入 RCA 字段。

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

## TEP Adapter

TEP 更适合作为主 RCA/path-ranking evaluation 场景，因为它有 time-series variables、fault type、process units 和 fault propagation 语义。Adapter 仍然不能把 `faultNumber` 作为 root-cause prediction 输出；fault reference 应放到 evaluation/reference 文件中。

可用组件：

| 组件 | 作用 | 可产出 evidence |
| --- | --- | --- |
| PCA / DPCA / RBC contribution | 经典过程监控，输出异常变量贡献 | variable、variable_contribution、severity |
| block PCA / process decomposition | 根据 process blocks 分析异常来源和传播 | process_unit、temporal_pattern、variable_contribution |
| DAE / VAE / LSTM autoencoder | reconstruction residual 作为变量异常分数 | variable、variable_contribution、temporal_pattern |
| classifier + SHAP/IG | 可选增强，给 fault-type probability 和变量 attribution | fault_type_candidate 作为 weak observation |

建议流程：

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

TEP adapter 不能输出：

```text
root_cause = FeedFlowDisturbance
fault_answer = IDV_6
top_k_paths
```

正确边界是：

```text
adapter:
  XMEAS_1 abnormal, contribution=0.31, trend=increasing

reference file:
  case_id -> official/literature-supported fault reference

KGTracePipeline:
  XMEAS1 -> INDICATES -> ProcessFault -> HAS_PLAUSIBLE_CAUSE -> FeedFlowDisturbance
```

## Wafer / WM-811K Adapter

公开 WM-811K 更适合 wafer map spatial pattern recognition（晶圆图空间模式识别）和 traceability demo，不提供完整工艺日志和 verified process root cause。

可用组件：

| 组件 | 作用 | 可产出 evidence |
| --- | --- | --- |
| CNN / ResNet / EfficientNet / lightweight CNN | wafer pattern classification | spatial_pattern、confidence |
| ViT / attention CNN | 处理 class imbalance 或增强 pattern recognition | spatial_pattern、confidence、saliency |
| classical spatial descriptors | 从 wafer map 提取空间形态 | location、morphology、severity |
| Grad-CAM / saliency / attention map | 可选解释模型关注区域 | image_region、location |
| log parser | 如果有私有或 demo logs | log_event、alarm、operation_phase |

如果没有真实 log，不要伪装成 multimodal。可以用 demo-only synthetic log，但必须标记 `source_ref=synthetic_demo_log` 和 `annotation_type=demo_synthetic`。

Wafer adapter 不能输出：

```text
true_process_root_cause
equipment_failure
verified_recipe_issue
```

只有在拿到私有 wafer process logs、lot history、tool/chamber records 和专家 review 后，wafer 才能升级为正式 RCA evaluation。

## 三类 Adapter 对比

| 数据集 | 最适合的模型/算法 | Adapter 可自动产出 | 需要规则/表格补充 | 不能产出 |
| --- | --- | --- | --- | --- |
| MVTec / DS-MVTec | PatchCore / EfficientAD + DS labels/captions；可选 VLM | anomaly score、heatmap/mask、defect label/caption、VLM weak candidates | mask geometry -> location/morphology | verified RCA / VLM root-cause |
| TEP | PCA/DPCA/RBC contribution、autoencoder residual | abnormal variables、contribution scores、trends | variable table / KG -> process unit | root cause answer / fault answer |
| Wafer / WM-811K | CNN/ResNet/EfficientNet/ViT classifier + spatial descriptors | spatial pattern、classification confidence、defect density | geometry rules -> location/morphology；log parser if available | verified process RCA |

## 组会可用表述

> Adapter 的目标不是预测 root cause，而是把各类模型输出变成统一 evidence items。对 MVTec，PatchCore/EfficientAD 产生 anomaly map 和 score，DefectSpectrum/label/caption 提供 defect semantics，mask geometry 规则产生 location 和 morphology；可选 VLM 只产生 weak/needs-review evidence。对 TEP，PCA/贡献图或 autoencoder residual 产生异常变量和贡献分数。对 wafer，CNN/ViT 产生 spatial pattern，空间规则产生 location/morphology。所有 observations 再交给 KGTracePipeline 做运行时 KG 推理。

## References

- Anomalib getting started: <https://anomalib.readthedocs.io/en/v2.1.0/markdown/get_started/anomalib.html>
- Anomalib PatchCore docs: <https://anomalib.readthedocs.io/en/stable/markdown/guides/reference/models/image/patchcore.html>
- Anomalib EfficientAD docs: <https://anomalib.readthedocs.io/en/v2.0.0/markdown/guides/reference/models/image/efficient_ad.html>
- DefectSpectrum dataset page: <https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum>
- Defect Spectrum paper: <https://arxiv.org/abs/2310.17316>
- TEP process decomposition / PCA contribution map: <https://arxiv.org/abs/2409.11444>
- Deep anomaly detection on TEP: <https://arxiv.org/abs/2303.05904>
- WM-811K wafer pattern classes and imbalance discussion: <https://www.sciencedirect.com/science/article/abs/pii/S0925527324001324>
- Wafer defect pattern detection and classification discussion: <https://www.sciencedirect.com/science/article/abs/pii/S0957417423010461>
