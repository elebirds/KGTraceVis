# Reasoning Adapter / Reasoning Profile 改造计划（叙事对齐版）

## 文档状态

- 状态：草案
- 目的：为论文叙事和系统抽象提供一套更统一的说法
- 约束：**本计划优先服务于“把故事讲顺”，不是为了重写现有推理算法**
- 核心原则：**保留当前推理逻辑，新增的是包装层、注册层和配置层，不是算法替换层**

---

## 1. 为什么要做这份改造计划

当前 KGTraceVis 的主线已经比较清楚：

- 上游通过 adapter / producer 把多源数据规范化为统一 Evidence；
- 中间通过共享 KG 做 entity linking、consistency checking、correction；
- 下游通过 RCA reasoner 生成 `top_k_paths` 和 `ranked_root_causes`。

但在“论文故事”层面，目前 reasoning 部分仍然显得不够对称：

- TEP 有较强的领域特定推理逻辑（Root-KGD / Root-KGD runtime provider）；
- MVTec 和 Wafer 主要依赖 generic graph-path reasoning 或较轻的场景补充；
- 当前代码里 TEP provider 是一个现实且合理的特例，但如果直接写进论文，容易看起来像“框架中夹了一个 hard-coded 特判”。

因此，本计划的目标不是发明新算法，而是把现有事实重新组织为一个更容易解释、也更便于后续扩展的系统抽象：

> **知识构建（KG construction）与根因推理（RCA reasoning）解耦；**
> **不同工业场景可以挂接不同的 reasoning adapter；**
> **adapter 消费共享 KG 与外部 reasoning profile，输出统一 RCA 结果。**

这套说法可以自然解释：

1. 为什么 TEP 可以有专门的 Root-KGD 路线；
2. 为什么同一个数据集理论上可以切换不同推理方法；
3. 为什么系统统一的是输入输出合同，而不是所有数据集必须使用同一套推理公式。

---

## 2. 当前系统的真实现状（必须保留的事实基线）

在讨论改造前，必须先把当前系统的“事实基线”写清楚。后续叙事不能违背这些事实。

### 2.1 统一推理入口已经存在

当前统一推理入口已经由 `RcaReasoner` 合同提供：

```python
class RcaReasoner(Protocol):
    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        ...
```

因此，所谓“reasoning adapter”并不是凭空新造概念，而是对现有 `RcaReasoner` 扩展点的正式命名与系统化包装。

### 2.2 当前已有两个推理层级

当前代码已经体现了两类 reasoning：

1. **GenericGraphPathReasoner**
   - 默认通用路径排序器；
   - 面向共享 KG 的 relation-weighted path reasoning；
   - 可用于 MVTec、Wafer，也可作为 TEP 的 generic baseline。

2. **TepRootKgdRcaProvider**
   - 当前唯一正式支持的 TEP 原生 reasoner；
   - 使用 `data/kg/tep_root_kgd/` 下的静态资产进行运行时推理；
   - 输出合同与 generic reasoner 对齐。

### 2.3 当前 TEP provider 依赖的事实资产

当前 `TepRootKgdRcaProvider` 依赖以下静态资产（保持不变）：

- `data/kg/tep_root_kgd/nodes.jsonl`
- `data/kg/tep_root_kgd/edges.jsonl`
- `data/kg/tep_root_kgd/tep_variable_mapping.jsonl`
- `data/kg/tep_root_kgd/anchor_discriminators.json`
- `data/kg/tep_root_kgd/relation_family_params.json`
- `data/kg/tep_root_kgd/rca_edge_weights.jsonl`
- `data/kg/tep_root_kgd/anchor_memory_profiles.json`

这些资产当前就是 TEP runtime reasoning 的事实来源。**本计划不改变这些资产的语义，也不改变其默认读取逻辑。**

### 2.4 当前 TEP runtime 的边界

当前 TEP runtime 的边界也必须保留：

- TEP runtime 消费当前 `Evidence` 中的 `variable_contributions` / `graph_contributions` / `root_kgd_dynamic_features`；
- 它不是在 KGTraceVis 内重新训练 RBC；
- 它不读取外部每个场景预生成的 ranking 结果作为运行时输入；
- fault number 可以用于评估摘要，但**不能作为运行时打分输入**。

因此，未来如果引入 `reasoning profile`，也只能把这些“已存在的资产与参数”包装得更清楚，**不能趁机改变 TEP 推理的事实边界。**

---

## 3. 拟议的新叙事：Reasoning Adapter + Reasoning Profile

### 3.1 核心说法

建议把 reasoning 部分正式抽象成两层：

1. **Reasoning Adapter**：代码里的推理实现；
2. **Reasoning Profile**：外部提供的领域先验与推理配置。

两者关系如下：

```text
Evidence + KG
    -> Reasoning Adapter
    -> (loads Reasoning Profile)
    -> Unified RCA Output
```

### 3.2 这套说法想解决什么问题

这套抽象主要解决叙事层面的三个问题：

1. **把 TEP 从“特例硬编码”解释成“场景特定 reasoner”**；
2. **允许同一数据集存在多个可比较的 reasoning 方法**；
3. **把“配置”与“算法”分开：算法逻辑在 adapter，领域先验在 profile**。

### 3.3 推荐表述

推荐在文档/论文中使用如下表述：

> KGTraceVis separates knowledge construction from RCA reasoning through a unified reasoning-adapter interface. Shared Evidence and KG contracts are reused across scenarios, while domain-specific reasoning profiles provide external prior assets such as anchors, runtime overlays, statistical signal models, and scoring policies.

中文可表述为：

> KGTraceVis 将知识构建与根因推理解耦：前者提供统一、可追溯的 Evidence 与 KG，后者通过可插拔的 reasoning adapter 消费共享知识空间和领域特定的 reasoning profile，并生成统一 RCA 输出。

---

## 4. 术语约束：什么叫 adapter，什么叫 profile

这部分必须讲清楚，否则会造成过度承诺。

### 4.1 Reasoning Adapter

**Reasoning Adapter 是代码实现，不是 JSON。**

它负责：

- 解释某类 reasoning profile；
- 执行具体推理逻辑；
- 返回统一的 `RcaReasoningResult`；
- 保持与 `KGTracePipeline` 的对接稳定。

当前可映射为：

- `generic_graph_path` -> `GenericGraphPathReasoner`
- `tep_root_kgd` -> `TepRootKgdRcaProvider`

### 4.2 Reasoning Profile

**Reasoning Profile 是外部资产描述，不是算法本身。**

它负责提供：

- runtime overlay（可选）
- anchors / mappings
- 统计 profile（如 RBC 参数）
- scoring / policy 参数
- 资产清单与版本信息

### 4.3 不能说成什么

以下说法需要避免：

- “用户只要写一个 JSON 就能定义任意新推理算法。”
- “系统通过配置文件自动生成推理逻辑。”
- “所有数据集都拥有同等复杂度的领域推理器。”

更准确的表述应该是：

> 用户可以选择或提供某个 reasoning profile；系统据此加载兼容的 reasoning adapter，并执行该 adapter 已实现的推理逻辑。

---

## 5. 为什么这个故事能自然覆盖 TEP、MVTec 和 Wafer

### 5.1 TEP

TEP 是当前最强的领域特定推理场景。

其 reasoning profile 可以包含：

- TEP variable mapping
- RBC profile / reconstruction profile
- RFPA / propagation / relation-family 参数
- fault anchors
- anchor memory profiles
- discriminators
- reasoning-specific runtime overlay

对应 adapter 为：

- `tep_root_kgd`

### 5.2 MVTec

MVTec 当前并没有像 TEP 一样复杂的时序统计推理资产，因此它的 reasoning profile 可以很轻：

- 可直接使用 `generic_graph_path_default`
- 后续如需要，也可增加轻量的 visual RCA profile：
  - defect taxonomy prior
  - morphology/location weighting
  - plausible cause anchors

对应 adapter 初始可仍然是：

- `generic_graph_path`

### 5.3 Wafer

Wafer 的 profile 也可以从轻量级开始：

- pattern/location prior
- process-unit anchors
- spatial scoring policy

初始同样仍可保留：

- `generic_graph_path`

### 5.4 统一点

三者统一的是：

- Evidence contract
- KG contract
- RCA output contract

三者可不同的是：

- reasoner adapter
- reasoning profile
- 使用的先验资产复杂度

这样讲，既诚实，也更符合工程现实。

---

## 6. 本计划的硬约束（最重要的部分）

以下约束是本计划的硬边界，**任何后续实现都不能跨越**。

### 6.1 这是叙事层/包装层改造，不是算法重写

本计划的首要目标是：

- 让系统故事更完整；
- 让 reasoning 扩展点显式化；
- 让 TEP 特例在论文中更自然。

**本计划不是为了：**

- 换掉现有 TEP Root-KGD 算法；
- 改写 generic graph-path 算法；
- 引入新的默认评分公式；
- 改变当前 baseline 的结果表现。

### 6.2 默认行为必须保持不变

即使未来引入 profile/registry，默认 pipeline 行为也必须保持：

- 未显式指定 profile 时，非 TEP 仍走 generic graph path；
- TEP 默认仍走当前 `TepRootKgdRcaProvider`；
- 当前 `scoring_method` 保持兼容，例如：
  - `relation_weighted_path`
  - `tep_root_kgd`

### 6.3 不能把“算法”伪装成“配置”

Profile 只能外置：

- 资产路径
- 版本
- 参数
- overlay
- policy

**不能声称 JSON 本身定义了新算法。**

### 6.4 不能改变 TEP runtime 的事实边界

特别是：

- 不把 RBC 训练并入 KGTraceVis runtime 主链路；
- 不把外部预生成 ranking 文件作为 TEP runtime 输入；
- 不把 fault label 当作打分特征；
- 不让 reasoner 在推理时修改 KG。

### 6.5 不能把 reasoning profile 和 KG facts 混成一层

必须区分：

1. **可进入 KG 的静态知识**
   - variable nodes
   - fault anchors
   - runtime overlay edges

2. **不直接进入 KG 的推理资产**
   - RBC profile
   - anchor memory
   - RFPA / propagation params
   - scoring policy

前者可以成为 node/edge 或 overlay；后者应保持为 reasoning assets。

### 6.6 不能为了“圆故事”夸大论文 claim

建议明确写入：

- 这是框架层抽象，不是“发明通用推理 DSL”；
- 这是可插拔推理接口，不是“用户随便写 JSON 就能实现新算法”；
- 这是对现有系统事实的重新组织，不是对所有场景都已 fully productized 的承诺。

---

## 7. 建议的数据流叙事

建议统一画成如下数据流：

```text
Raw Data / Records / Evidence Sources
    -> Evidence Adapter
    -> Unified Evidence
    -> Shared KG Snapshot (+ optional runtime overlay)
    -> Reasoning Adapter
    -> (loads Reasoning Profile)
    -> top_k_paths + ranked_root_causes
```

对于 TEP，还可以补一个更细的场景图：

```text
TEP sequence window
    -> producer-derived contributions / dynamic features
    -> Unified Evidence
    -> tep_root_kgd adapter
    -> loads TEP reasoning profile
    -> Root-KGD runtime scoring
    -> unified RCA output
```

这个说法的好处是：

- 不需要说 KGTraceVis 负责训练 RBC；
- 不需要说 TEP 是“写死的特殊逻辑”；
- 可以自然解释 domain-specific reasoning assets。

---

## 8. Reasoning Profile 建议长什么样

### 8.1 推荐不要只做一个“大 JSON”

对论文叙事来说，可以把它称为 “reasoning profile JSON”；
但工程上更建议采用：

- 一个 `manifest.json`
- 加若干 linked artifacts

示意：

```text
configs/reasoning_profiles/
  tep_root_kgd_default/
    manifest.json
    overlay_nodes.jsonl
    overlay_edges.jsonl
    rbc_profile.json
    relation_family_params.json
    anchor_memory_profiles.json
    anchor_discriminators.json
    variable_mapping.jsonl
```

### 8.2 Manifest 中推荐包含的信息

```json
{
  "reasoning_profile_id": "tep_root_kgd_default",
  "dataset_scope": ["tep"],
  "reasoner_adapter": "tep_root_kgd",
  "version": "1.0.0",
  "required_evidence_fields": [
    "raw_evidence.variable_contributions",
    "raw_evidence.extra.graph_contributions",
    "raw_evidence.extra.root_kgd_dynamic_features"
  ],
  "runtime_overlay": {
    "nodes": "overlay_nodes.jsonl",
    "edges": "overlay_edges.jsonl"
  },
  "reasoning_assets": {
    "rbc_profile": "rbc_profile.json",
    "anchor_memory_profiles": "anchor_memory_profiles.json",
    "anchor_discriminators": "anchor_discriminators.json",
    "relation_family_params": "relation_family_params.json",
    "variable_mapping": "variable_mapping.jsonl"
  },
  "claim_boundary": "Profile config externalizes prior assets and policy; adapter code still defines runtime reasoning behavior."
}
```

### 8.3 重要说明

- `fault anchor` 可以作为 runtime overlay knowledge，也可以直接引用现有 TEP Root-KGD graph asset；
- `RBC profile`、`anchor memory`、`relation family params` 应被视为 reasoning assets；
- profile 是“描述与装配”，不是“算法编排脚本”。

---

## 9. 拟议的最小改造路径（必须尽量无行为变化）

### Phase 0：文档先行（本阶段）

目标：先把系统叙事、边界和术语写清楚。

输出：

- 本文档
- 后续如需要，可在 `README` / `project_design` / 论文 handoff 中补充一致表述

### Phase 1：引入 reasoning registry，但不改算法

建议最小引入：

- `ReasoningProfileManifest` 数据结构
- `ReasoningAdapterRegistry` / `resolve_reasoner(...)`
- 配置到 adapter 的映射逻辑

此阶段要求：

- `GenericGraphPathReasoner` 原样保留
- `TepRootKgdRcaProvider` 原样保留
- 默认行为不变

### Phase 2：把“当前事实”包装成 profile

先只包装现有逻辑：

- `generic_graph_path_default`
- `tep_root_kgd_default`

强调：

- 这是“现有逻辑的 profile 化包装”
- 不是“新算法上线”

### Phase 3：允许显式选择 profile，但默认不变

可选扩展到：

- workflow config
- script CLI
- service request

但默认必须保持当前行为：

- TEP -> `tep_root_kgd_default`
- 其他 -> `generic_graph_path_default`

### Phase 4：后续如有需要，再添加轻量 domain profile

如：

- `mvtec_visual_default`
- `wafer_pattern_default`

但这个阶段不是当前论文故事成立的必要条件。

**为了圆故事，不需要立刻发明三套复杂 reasoner；只需要把“不同场景允许不同推理配置”这个框架层抽象立住即可。**

---

## 10. 推荐的代码影响范围（规划，不是承诺）

以下是可能触达的代码区域，但本计划不要求一次性实现全部：

### 保持不动或仅做薄包装

- `src/kgtracevis/core/rca.py`
- `src/kgtracevis/core/pipeline.py`
- `src/kgtracevis/workflows/tep_root_kgd/*`
- `src/kgtracevis/kg/path_ranker.py`

### 可能新增的薄层

- `src/kgtracevis/core/reasoning_profile.py`
- `src/kgtracevis/workflows/reasoning_registry.py`
- `configs/reasoning_profiles/*`

### 可能调整的入口封装

- `src/kgtracevis/workflows/root_cause_provider_selection.py`

注意：

> `root_cause_provider_selection.py` 的职责应从“硬编码挑一个 provider”变成“根据默认规则或显式 profile 解析一个 provider”，但默认解析结果必须与当前一致。

---

## 11. 风险与对应控制

### 风险 1：包装层改造引发行为漂移

**控制：**

- 默认 profile 必须是 current behavior 的一比一封装；
- TEP 的资产文件和推理函数不改，只做指针式包装；
- 关键回归要看 `scoring_method`、`top_k_paths`、`ranked_root_causes` 是否一致。

### 风险 2：论文叙事过度承诺“可配置能力”

**控制：**

- 始终强调 adapter 负责算法，profile 负责先验与参数；
- 不使用“任意定义推理方法”这类措辞；
- 使用“select / provide a reasoning profile compatible with a registered adapter” 这类表述。

### 风险 3：把 KG facts 和 reasoning assets 混在一起

**控制：**

- 在 profile 中分区：`runtime_overlay` vs `reasoning_assets`；
- 不把 RBC/anchor-memory 误导成 KG edge；
- 文档中显式写出这条边界。

### 风险 4：为了 story，引入新的无验证 reasoner

**控制：**

- 当前阶段只包装现有 generic + TEP logic；
- MVTec/Wafer 可先保留 generic；
- 新 profile 不等于新 algorithm。

---

## 12. 论文/汇报中的推荐说法与禁忌说法

### 12.1 推荐说法

可以说：

- “The framework supports pluggable reasoning adapters under a unified Evidence/KG/output contract.”
- “Domain-specific reasoning profiles externalize prior assets and scoring policy.”
- “Different industrial scenarios may use different reasoning strategies while remaining comparable at the output layer.”
- “The current TEP route is one instantiated domain-specific reasoner.”

### 12.2 禁忌说法

不要说：

- “A JSON file fully defines the reasoning algorithm.”
- “Users can invent arbitrary new RCA algorithms by editing config only.”
- “All three datasets already have equally rich domain-specific reasoners.”
- “This refactor improves RCA accuracy by itself.”

### 12.3 对 TEP 的安全说法

推荐说：

- TEP uses a domain-specific Root-KGD reasoning adapter.
- The adapter consumes checked-in prior assets and current Evidence features.
- The system does not retrain the RBC model online inside the generic analysis path.

不要说：

- TEP reasoning is fully generated from config alone.
- KGTraceVis trains the Root-KGD statistical model as part of ordinary inference.

---

## 13. 最终结论

这次改造的定位应当非常明确：

> **这是一次“叙事对齐 + 包装层显式化”的改造。**
> **它服务于更自然地解释当前系统为何能够同时容纳 generic reasoning 与 TEP-specific reasoning。**
> **它不以修改现有推理逻辑为目标，也不应改变当前默认结果。**

如果后续要实施，最稳妥的路线是：

1. 先把 `RcaReasoner` 正式命名为 reasoning adapter 扩展点；
2. 再把现有 TEP / generic 行为包装成默认 reasoning profile；
3. 最后才考虑是否向 MVTec / Wafer 提供轻量 profile；
4. 全程坚持“默认行为不变、输出合同不变、算法逻辑不漂移”的约束。

用一句最简洁的话概括本计划：

> **我们不是为了新算法而重写推理层，而是为了把现有事实组织成一个更完整、更可解释、更便于论文表达的系统架构。**
