# KGTraceVis 前后端交接文档

本文面向 `web/` 前端开发者，目的是把当前后端已经实现的能力、接口契约、输入输出边界、联调方式和已知契约缺口一次说清楚。

文档依据的真实代码入口：

- 路由入口：`src/kgtracevis/service/api.py`
- 运行时 DTO：`src/kgtracevis/service/run_models.py`
- 分析结果补充字段：`src/kgtracevis/service/run_enrichment.py`
- 直接分析/what-if/feedback 请求：`src/kgtracevis/service/handlers.py`
- Source material library：`src/kgtracevis/service/kg_materials.py`
- KG Studio：`src/kgtracevis/service/kg_studio.py`
- Source-to-KG：`src/kgtracevis/service/kg_source_drafts.py`
- 构建/发布/评审：`src/kgtracevis/service/kg_construction.py`
- 前端现有类型：`web/src/api/contracts.ts`
- 前端 API client：`web/src/api/client.ts`
- 前端 KG Studio 页面：`web/src/features/kg-studio/KGStudioPages.tsx`
- 前端路由/Tab：`web/src/app/routes.tsx`

## 1. 先说结论

KGTraceVis 不是一个“纯 CRUD 后端项目”，而是一个：

- `FastAPI + React/Vite` 的研究型工作台
- 后端负责证据接入、KG 推理、RCA 候选排序、运行记录持久化、反馈持久化
- 前端负责上传、浏览、筛选、图谱与路径可视化、反馈提交

后端输出的 RCA 相关结果一律要按下面这条边界展示：

> `candidate/plausible explanation only; not a verified root-cause label`

前端不要把返回的 `ranked_root_causes` 或 `top_k_paths` 当成“已验证根因”。

## 2. 后端负责什么，前端负责什么

### 2.1 后端负责

1. 接收三类输入并转换为统一分析流程
   - `records`
   - `evidence`
   - `image`
2. 运行统一 KG 分析链路
   - entity linking
   - consistency checking
   - correction candidates
   - path ranking
   - unified RCA ranking (`ranked_root_causes`)
3. 生成前端可直接消费的派生字段
   - `evidence_summary`
   - `path_graph`
   - `source_edge_provenance`
   - `review_targets`
   - `visual_evidence`
4. 持久化运行记录和反馈
   - `GET /api/runs`
   - `GET /api/runs/{run_id}`
   - `POST /api/feedback`
5. 提供 KG Studio 和 Source-to-KG 相关接口
   - 读候选 KG
   - 管理 source material library
   - 对 material 做 extraction，生成 structured records
   - 把 selected materials 转成 construction build-ready sources
   - 生成 source draft
   - 触发 build / validate / publish / review

### 2.2 前端负责

1. 收集输入并调用 API
2. 展示运行历史和单次运行详情
3. 渲染证据、链路、候选根因、路径图、来源边信息
4. 维护当前选中的 case / path / review target
5. 提交 review feedback / KG draft / source draft / material extraction / construction build
6. 始终显示 candidate/plausible claim boundary

### 2.3 前端不要做的事

- 不要在前端复写 KG 推理逻辑
- 不要在前端自己推断 `path_graph`
- 不要把 `top_k_paths` 再二次计算成另一套 RCA 结果
- 不要把 feedback 直接当成 KG 已修改完成
- 不要把候选 RCA 说成 verified RCA

## 3. 本地联调方式

### 3.1 依赖

- Python 环境：`uv`
- 运行时数据库：`Postgres`
- 运行时 KG：`Neo4j`
- 前端：`Node + npm`

### 3.2 启动后端

```bash
uv sync --all-extras
uv run python scripts/run_web_api.py
```

后端地址：

- API: `http://127.0.0.1:8081`
- Swagger: `http://127.0.0.1:8081/docs`
- OpenAPI: `http://127.0.0.1:8081/openapi.json`

如果本地数据库未起，需要先启动 Neo4j / Postgres。项目 README 当前建议：

```bash
docker compose up -d neo4j postgres
```

### 3.3 启动前端

```bash
cd web
npm ci
npm run dev
```

前端地址：

- Vite: `http://127.0.0.1:5173`

### 3.4 联调时要注意

- `GET /api/runs`、`GET /api/runs/{run_id}`、`POST /api/feedback` 依赖 Postgres
- KG runtime 查询依赖 Neo4j
- `image` 模式依赖本地 MVTec 模型资产和 checkpoint
- 最稳定的 smoke path 是 `records` 和 `evidence`，不是 `image`

### 3.5 推荐用于前端联调的样例输入

- `data/examples/records/mvtec_records.jsonl`
- `data/examples/records/wm811k_records.jsonl`
- `data/examples/tep_example.json`
- `data/examples/mvtec_noisy_morphology_demo.json`
- `data/examples/wafer_example.json`

## 4. 后端主分析能力

### 4.1 支持的数据场景

- `mvtec`
- `tep`
- `wafer`

### 4.2 TEP RCA 的结论

后端已经有统一 RCA 输出，不是只有路径没有候选根因。

对前端来说，不需要区分“是不是 TEP 专用页面逻辑”，只需要统一消费：

- `top_k_paths`
- `ranked_root_causes`
- `review_targets`
- `path_graph`

如果是 TEP 场景，`ranked_root_causes[*].scoring_method` 可能是：

- `tep_root_kgd`
- `tep_artifact_bridge`
- 或回退的 `relation_weighted_path`

前端建议把 `scoring_method` 当成标签显示，但不要据此改动主渲染流程。

## 5. 核心接口总览

## 5.1 `GET /api/dashboard/bootstrap`

作用：给前端首页和上传页提供初始化元数据。

返回重点字段：

- `status`
- `api_version`
- `claim_boundary`
- `supported_datasets`
- `supported_feedback_targets`
- `supported_feedback_actions`
- `upload_modes`
- `mvtec_model_presets`
- `recent_runs`

前端用途：

- 初始化上传模式选项
- 初始化 dataset 选项
- 初始化 recent runs
- 初始化 image 模式的 preset 下拉

## 5.2 `POST /api/runs/upload`

作用：上传输入并生成一个持久化的运行记录，返回 `RunDetail`。

请求类型：`multipart/form-data`

表单字段：

- `file`: 必填
- `mode`: `records | evidence | image`
- `dataset`: 可选，`mvtec | tep | wafer`
- `object_name`: `image` 模式下使用
- `defect_type`: `image` 模式下使用
- `model_preset`: `image` 模式下使用
- `top_k`: 默认 5，范围 1-20

三种输入模式：

1. `records`
   - 接受 `.json` `.jsonl` `.csv`
   - 适合批量 case
   - 返回的 `RunDetail.cases[]` 会比较重要
2. `evidence`
   - 接受统一 evidence JSON
   - 适合单 case 直接分析
3. `image`
   - 仅支持 MVTec 图像
   - 依赖本地模型和 checkpoint

前端注意：

- 多 case 的 records 结果，应该优先使用 `RunDetail.cases[]`
- 顶层 `linked_entities`、`top_k_paths`、`review_targets` 更像聚合视图

## 5.3 `GET /api/runs`

作用：返回运行历史列表。

返回类型：`RunSummary[]`

主要字段：

- `run_id`
- `created_at`
- `mode`
- `source_filename`
- `top_k`
- `status`
- `dataset`
- `case_count`
- `evidence_count`
- `label`
- `model_preset`
- `model_backend`

前端用途：

- Analysis History 列表
- 首页 recent runs

## 5.4 `GET /api/runs/{run_id}`

作用：获取一个完整运行的详情。

返回类型：`RunDetail`

这是前端最重要的接口。

## 5.5 `GET /api/runs/{run_id}/artifacts/{artifact_name}`

作用：返回某个运行下的工件文件。

典型用途：

- 预览 image / mask / heatmap / wafer_map

前端建议：

- 如果 `visual_evidence[*].url` 已可直接用，优先用 `url`
- 不要拼接本地磁盘路径

## 5.6 `POST /api/analyze`

作用：做一次不落库的即时分析。

请求体：

```json
{
  "case_id": "optional-existing-case-id",
  "evidence": {
    "case_id": "optional-if-case_id-provided",
    "dataset": "mvtec",
    "source": "image",
    "object": "bottle",
    "anomaly_type": "scratch",
    "location": "body",
    "morphology": "linear",
    "severity": 0.7,
    "confidence": 0.8,
    "timestamp": null,
    "raw_evidence": {},
    "normalized_evidence": {},
    "kg_analysis": {}
  },
  "top_k": 5
}
```

规则：

- `case_id` 和 `evidence` 至少传一个
- 返回的是即时分析 envelope，不是 `RunDetail`

返回重点字段：

- `case`
- `evidence`
- `analysis`
- `evidence_with_analysis`
- `workflow_steps`
- `claim_boundary`

适合场景：

- 前端做临时分析
- 表单式 evidence 编辑后立即看结果
- 不想落库时的快速预览

## 5.7 `POST /api/what-if`

作用：基于已有 `case_id`，局部修改证据字段后重新跑分析。

请求体：

```json
{
  "case_id": "tep_case_0001",
  "anomaly_type": "reaction_instability",
  "location": "reactor",
  "morphology": "oscillatory",
  "variables": ["xmeas_1", "xmv_3"],
  "log_events": ["alarm_A"],
  "severity": 0.9,
  "confidence": 0.7,
  "top_k": 5
}
```

适合场景：

- Experiments 页的 what-if 编辑
- 前端做字段改写后的候选 RCA 对比

注意：

- 返回也是即时 envelope，不会自动生成新的 run history

## 5.8 `POST /api/feedback`

作用：提交 review feedback，后端写入 Postgres。

请求字段：

- `case_id` 或 `run_id` 至少一个
- `target_type`
- `action` 或兼容旧字段 `decision`
- `target_id`
- `note`
- `reviewer`
- `source`
- `metadata`

返回：

```json
{
  "status": "recorded",
  "record": {}
}
```

前端建议：

- 新代码统一用 `action`
- `source` 建议传具体页面来源，例如 `rootlens-analysis`

## 5.9 `GET /api/kg/studio`

作用：返回 KG Studio 所需的只读数据。

返回重点字段：

- `status`
- `claim_boundary`
- `candidate_dir`
- `nodes_path`
- `edges_path`
- `source_registry_path`
- `node_count`
- `edge_count`
- `scenario_counts`
- `review_status_counts`
- `source_counts`
- `confidence_summary`
- `validation_summary`
- `sources`
- `source_documents`
- `graph_nodes`
- `graph_edges`
- `review_targets`
- `note`

这不是“写 KG”的接口，而是“读候选 KG + 读评审目标”的接口。

## 5.10 `GET /api/kg/materials`

作用：返回 KG Studio 的 source material library。

返回重点字段：

- `status`
- `material_dir`
- `material_root`
- `count`
- `materials`
- `note`

`materials[*]` 是当前前端新增的重点合同，常用字段包括：

- `material_id`
- `title`
- `scenario`
- `source_type`
- `source_format`
- `path`
- `url`
- `uri`
- `filename`
- `processing_status`
- `extraction_status`
- `chunk_count`
- `page_count`
- `source_id`
- `notes`
- `created_at`
- `metadata`
- `extraction`

前端用途：

- KG Studio 的 Material Library 表格
- 选中 material 后右侧 metadata 面板
- 判断一个 material 是否已经 `extracted`，是否可进入 build-sources / build

## 5.11 `POST /api/kg/materials/upload`

作用：上传一个本地 source material 文件并注册到 material library。

请求类型：`multipart/form-data`

表单字段：

- `file`: 必填
- `title`: 可选
- `scenario`: 可选，默认 `shared`
- `source_type`: 可选，默认 `other`
- `notes`: 可选
- `metadata`: 可选，JSON string
- `material_id`: 可选
- `overwrite`: 可选

返回重点字段：

- `status`
- `material`
- `note`

注意：

- 这一步只是把 provenance material 纳入工作台，不会直接构建 KG
- 上传成功后，前端下一步通常是调用 extract

## 5.12 `POST /api/kg/materials/register-url`

作用：把一个远程 URL 注册成 source material，而不是上传文件。

请求体：

```json
{
  "url": "https://example.com/doc",
  "title": "optional title",
  "scenario": "shared",
  "source_type": "webpage",
  "notes": "optional note",
  "metadata": {},
  "material_id": "optional_id"
}
```

返回重点字段：

- `status`
- `material`
- `note`

前端用途：

- 收录网页、在线文档、公开资料链接
- 后续再对该 material 走 extraction

## 5.13 `POST /api/kg/materials/{material_id}/extract`

作用：把一个已注册的 material 解析为 text chunks，并运行 source-grounded candidate extraction，输出 `structured_records.jsonl`。

请求体字段：

- `provider`: 当前只支持 `openai`
- `max_chars`
- `overlap_chars`
- `source_format`: 当前必须是 `jsonl`
- `overwrite`

返回重点字段：

- `status`
- `material`
- `structured_records_path`
- `record_count`
- `claim_boundary`

前端用途：

- 把 source material 从“只是被登记”推进到“已经有结构化 candidate records”
- 让 material 进入下一步 `build-sources`

## 5.14 `POST /api/kg/materials/build-sources`

作用：把一组选中的 extracted materials 转成标准 `KGConstructionSourceInput[]`，相当于 material library 到 construction build 的桥接接口。

请求体：

```json
{
  "material_ids": ["mat_1", "mat_2"],
  "output_name": "material_library",
  "overwrite": false,
  "run_id": null,
  "source_type": "structured_records"
}
```

返回重点字段：

- `status`
- `material_root`
- `request`
- `materials`
- `sources`
- `construction_request`
- `claim_boundary`

前端用途：

- 先预览哪些 sources 会被送进 construction
- 再把 `construction_request` 直接喂给 `POST /api/kg/construction/build`

## 5.15 Material Library 相关补充接口

后端还额外实现了两条接口：

- `GET /api/kg/materials/{material_id}`
- `POST /api/kg/materials/register`

说明：

- 这两条是后端已实现能力
- 当前 `web/src/api/client.ts` 还没有对它们做封装
- 目前前端主要使用的是 `list / upload / register-url / extract / build-sources`

## 5.16 `POST /api/kg/source-draft`

作用：把结构化 source text 解析成候选 KG 边，不直接写 CSV。

请求体：

```json
{
  "source_id": "dashboard_source",
  "source_text": "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,MechanicalContact,mvtec,Scratch wording supports a candidate contact mechanism.",
  "provider": "heuristic",
  "default_scenario": "shared",
  "confidence": 0.55
}
```

返回重点字段：

- `provider`
- `source_id`
- `claim_boundary`
- `candidate_edges`
- `note`

`candidate_edges[*]` 主要字段：

- `edge_id`
- `head`
- `relation`
- `tail`
- `scenario`
- `source`
- `evidence`
- `confidence`
- `weight`
- `review_status`

## 5.17 `POST /api/kg/drafts`

作用：记录 KG edge draft adjustment，当前是 append-only，不直接修改 KG CSV。

请求体主要字段：

- `target_type`: 当前固定 `edge`
- `target_id`
- `target_key`
- `draft_action`: `keep | revise | reject | promote_later`
- `proposed_relation`
- `proposed_evidence`
- `proposed_confidence`
- `note`
- `reviewer`
- `source`
- `metadata`

返回：

- `status`
- `record`

## 5.18 KG Construction 相关接口

这组接口后端已经实现，前端可以按需接入。

已实现接口：

- `POST /api/kg/construction/build`
- `GET /api/kg/construction/builds`
- `GET /api/kg/construction/builds/{run_id}`
- `POST /api/kg/construction/builds/{run_id}/validate`
- `POST /api/kg/construction/builds/{run_id}/publish`
- `POST /api/kg/construction/builds/{run_id}/review`
- `GET /api/kg/construction/builds/{run_id}/review-queue`
- `GET /api/kg/construction/sources`
- `POST /api/kg/construction/sources/upload`

当前 `web/src/api/client.ts` 已封装：

- `POST /api/kg/construction/build`

后端已实现但当前前端 client 还没封装：

- `GET /api/kg/construction/builds`
- `GET /api/kg/construction/builds/{run_id}`
- `POST /api/kg/construction/builds/{run_id}/validate`
- `POST /api/kg/construction/builds/{run_id}/publish`
- `POST /api/kg/construction/builds/{run_id}/review`
- `GET /api/kg/construction/builds/{run_id}/review-queue`
- `GET /api/kg/construction/sources`
- `POST /api/kg/construction/sources/upload`

建议前端分阶段接入：

1. 先用 `build`
2. 再接 `builds` / `detail`
3. 再接 `validate`
4. 再接 `review-queue` / `review`
5. 最后接 `publish`

## 6. 前端最应该围绕什么数据结构开发

## 6.1 `RunDetail` 是主合同

后端 `RunDetail` 主要字段如下：

- `run`
- `workflow_steps`
- `claim_boundary`
- `evidence`
- `evidence_summary`
- `evidence_with_analysis`
- `analysis`
- `summary`
- `cases`
- `linked_entities`
- `correction_candidates`
- `top_k_paths`
- `ranked_root_causes`
- `path_graph`
- `source_edge_provenance`
- `review_targets`
- `artifacts`
- `visual_evidence`

设计上可以这样理解：

- 单 case：顶层字段即可直接渲染
- 多 case：优先使用 `cases[]` 中每个 case 的局部字段，顶层字段看成聚合摘要

## 6.2 `cases[]` 是 records 模式的主显示单元

`records` 模式下，一个上传可能有多个 case。

每个 `case` 行里已经带了前端需要的大部分字段：

- `case_id`
- `dataset`
- `generated_evidence`
- `generated_evidence_path`
- `linked_entities`
- `consistency_score`
- `inconsistent_fields`
- `correction_candidates`
- `top_k_paths`
- `ranked_root_causes`
- `source_edge_provenance`
- `path_graph`
- `review_targets`

前端建议：

- 详情页先选中一个 case
- 图、边来源、review queue 都跟着当前 case 切换
- 不要只盯顶层聚合字段

## 6.3 `ranked_root_causes[]` 是统一 RCA 输出

字段来源：`src/kgtracevis/core/result.py`

主要字段：

- `ranking_id`
- `rank`
- `candidate_id`
- `candidate_name`
- `candidate_label`
- `candidate_role`
- `score`
- `confidence`
- `evidence_match`
- `explanation_paths`
- `supporting_edges`
- `supporting_evidence`
- `scoring_method`
- `scoring_details`
- `source`
- `review_status`

前端建议展示：

- 排名
- 候选名称
- 分数
- `scoring_method`
- 展开后显示 supporting paths / edges / evidence

## 6.4 `path_graph` 是图谱视图现成输入

`path_graph` 不需要前端自己组装。

主要结构：

- `paths[]`
- `path_count`
- `node_count`
- `edge_count`

每条 path 包含：

- `path_id`
- `target_key`
- `source_entity_id`
- `target_entity_id`
- `score`
- `confidence`
- `supporting_evidence`
- `nodes[]`
- `edges[]`

图组件应直接围绕这个结构做 selection 和 hover。

## 6.5 `review_targets` 是统一反馈入口

后端已经把 path / edge / link / correction 等对象整理成统一 review target。

每条 target 至少有：

- `target_type`
- `target_id`
- `target_key`
- `label`

前端建议：

- 所有 review panel 统一按 `review_targets` 渲染
- UI 状态用 `target_key`，不要只用 `target_id`

## 6.6 `visual_evidence` 用于图片/掩码/热力图/wafer 图

结构字段：

- `artifact_id`
- `case_id`
- `dataset`
- `kind`
- `title`
- `source_key`
- `source_path`
- `url`
- `preview_path`
- `available`
- `note`
- `metadata`

前端建议：

- `available && url` 时直接展示
- 否则做 unavailable 占位，不要报错

## 7. 页面侧建议

## 7.1 Home

建议展示：

- API/KG 状态
- recent runs
- upload 模式简介
- next action

数据来源：

- `GET /api/dashboard/bootstrap`
- 可选 `GET /api/kg/studio`

## 7.2 Analysis

建议拆成三块：

1. Live Upload
   - 用 `bootstrap.upload_modes`
   - 用 `POST /api/runs/upload`
2. History
   - 用 `GET /api/runs`
3. Detail
   - 用 `GET /api/runs/{run_id}`
   - 渲染 evidence / links / corrections / RCA / graph / review

## 7.3 KG Studio

当前前端实际路由已经拆成 6 个 tab：

1. Overview
   - `GET /api/kg/studio`
   - 展示 KG 状态、validation、counts、artifact paths
2. Sources
   - `GET /api/kg/materials`
   - `POST /api/kg/materials/upload`
   - `POST /api/kg/materials/register-url`
   - `POST /api/kg/materials/{material_id}/extract`
   - `POST /api/kg/materials/build-sources`
   - `POST /api/kg/source-draft`
   - 当前 Sources tab 既包含 material library，也包含 heuristic source draft
3. Build
   - `POST /api/kg/construction/build`
   - 当前是手动 construction form + material-derived sources 的汇合点
4. Graph
   - `GET /api/kg/studio`
   - 展示 candidate graph 和 edge provenance
5. Review
   - `GET /api/kg/studio`
   - `POST /api/feedback`
   - 当前主要围绕 edge review target
6. Drafts
   - `POST /api/kg/drafts`

如果后续继续扩展，建议保持这个分层，不要再把 KG Studio 收缩成一个大杂烩页面。

## 7.4 Experiments

更适合承接：

- `POST /api/analyze`
- `POST /api/what-if`

因为这两个接口天然适合做临时对比，而不是运行历史管理。

## 8. 建议的前端接入顺序

1. 先接 `GET /api/dashboard/bootstrap`、`GET /api/runs`、`GET /api/runs/{run_id}`
2. 再接 `POST /api/runs/upload`
3. 再接 `POST /api/feedback`
4. 再接 `GET /api/kg/studio`
5. 再接 material library：
   - `GET /api/kg/materials`
   - `POST /api/kg/materials/upload`
   - `POST /api/kg/materials/register-url`
   - `POST /api/kg/materials/{material_id}/extract`
   - `POST /api/kg/materials/build-sources`
6. 再接 `POST /api/kg/source-draft` 和 `POST /api/kg/drafts`
7. 最后接 construction build / validate / review / publish

这样做的原因：

- 先把分析主链路跑通
- 再补评审
- 再把 material library 路径接通
- 最后再接候选 KG 构建工作台的高级流程

## 9. 已知契约缺口

这一节非常重要，前端接之前先看。

### 9.1 `root_cause_candidate` 枚举还没完全打通

后端 `review_targets` 里已经可能返回：

- `target_type = "root_cause_candidate"`

但当前存在 4 处不一致：

1. `src/kgtracevis/service/run_enrichment.py`
   - 会生成 `root_cause_candidate`
2. `web/src/api/contracts.ts`
   - `ReviewTargetType` 还没有这个值
3. `src/kgtracevis/service/dashboard.py`
   - `supported_feedback_targets` 还没有这个值
4. `src/kgtracevis/service/handlers.py`
   - `FeedbackRequest.target_type` 也还没接受这个值

另外，Postgres schema 和 store 已经支持 `root_cause_candidate`。

实际含义：

- 后端运行结果里已经有 RCA candidate review target
- 但当前 HTTP feedback 入参枚举还没有完全对齐

前端建议：

- 在契约统一前，不要直接提交 `root_cause_candidate` feedback
- 先把它当展示项渲染即可

### 9.2 前端 `RunDetail` 类型漏了 `ranked_root_causes`

后端 `RunDetail` 已包含：

- `ranked_root_causes`

但 `web/src/api/contracts.ts` 的 `RunDetail` 里当前没有这个字段。

前端建议尽快补上，否则：

- RCA 候选只能从别的字段间接推
- 容易把 path ranking 和 RCA ranking 混在一起

### 9.3 前端 `KGStudioPayload` 类型比后端少字段

后端 `KGStudioPayload` 还包含：

- `summary_path`
- `manifest_path`
- `construction_manifest`

当前前端 contract 未覆盖这几个字段。

如果 KG Studio 页面要展示 build artifact 元数据，这几个字段要补。

### 9.4 `cases[]` 目前在前端是弱类型

当前 `web/src/api/contracts.ts` 里：

- `cases: Array<Record<string, unknown>>`

这会让多 case 视图开发成本偏高，也容易把聚合字段和 case 局部字段混掉。

建议后续把 `cases[]` 升级为明确的 case detail 类型。

### 9.5 前端 API client 目前只封装了后端接口的一部分

当前 `web/src/api/client.ts` 已封装的重点接口包括：

- `bootstrap`
- `kgStudio`
- `listKGMaterials`
- `uploadKGMaterial`
- `registerKGMaterialUrl`
- `extractKGMaterial`
- `buildKGMaterialSources`
- `listRuns`
- `getRun`
- `uploadRun`
- `submitReview`
- `submitKGDraft`
- `generateKGSourceDraft`
- `buildKGConstruction`

后端已实现但当前 client 尚未封装的接口包括：

- `POST /api/analyze`
- `POST /api/what-if`
- `GET /api/kg/materials/{material_id}`
- `POST /api/kg/materials/register`
- `GET /api/kg/construction/builds`
- `GET /api/kg/construction/builds/{run_id}`
- `POST /api/kg/construction/builds/{run_id}/validate`
- `POST /api/kg/construction/builds/{run_id}/publish`
- `POST /api/kg/construction/builds/{run_id}/review`
- `GET /api/kg/construction/builds/{run_id}/review-queue`
- `GET /api/kg/construction/sources`
- `POST /api/kg/construction/sources/upload`

这意味着：

- 后端能力已经比当前前端封装更完整
- 交互设计时要区分“后端未实现”和“前端暂未接”

## 10. 对前端同学的直接建议

如果你只想尽快把主界面做起来，最小可行做法是：

1. 首页调 `GET /api/dashboard/bootstrap`
2. Analysis 上传页调 `POST /api/runs/upload`
3. History 调 `GET /api/runs`
4. Detail 调 `GET /api/runs/{run_id}`
5. Detail 页面只先渲染：
   - `evidence_summary`
   - `visual_evidence`
   - `linked_entities`
   - `correction_candidates`
   - `ranked_root_causes`
   - `path_graph`
   - `review_targets`
6. Review 暂时只支持：
   - `path`
   - `edge`
   - `entity_link`
   - `correction`
7. 如果你优先做 KG Studio，建议先把 material flow 做通：
   - list materials
   - upload / register-url
   - extract
   - build-sources
   - build candidate KG

等 `root_cause_candidate` 契约补齐以后，再把 RCA candidate feedback 打开。

## 11. 附：前端当前已有的参考实现位置

- API client：`web/src/api/client.ts`
- TS contracts：`web/src/api/contracts.ts`
- Analysis 页面：`web/src/features/analysis/AnalysisPages.tsx`
- KG Studio 页面：`web/src/features/kg-studio/KGStudioPages.tsx`
- Workbench 路由/Tab：`web/src/app/routes.tsx`
- 设计文档：`docs/rootlens_dashboard.md`
- KG construction 详细设计：`docs/kg_construction.md`

如果接口和页面不一致，以后端真实 DTO 和 OpenAPI 为准，不以后端 README 或旧页面文案为准。
