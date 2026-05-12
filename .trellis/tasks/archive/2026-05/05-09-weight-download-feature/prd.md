# brainstorm: 增加权重下载功能

## Goal

为 KGTraceVis 增加可信公开模型权重的下载入口，让本地 demo 在缺少 MVTec / WM811K 默认权重时，可以通过命令行和 Web 工作台补齐所需资产，再继续运行真实模型 smoke pipeline。

## What I already know

* 用户要求“增加权重的下载功能”。
* 仓库已有未跟踪脚本 `scripts/download_model_assets.py`，包含 Hugging Face Hub 下载 MVTec STFPM OpenVINO tar 和 WM811K ResNet checkpoint 的雏形。
* Web 工作台已有 MVTec 模型 preset 列表接口 `/api/runs/mvtec-model-presets`，缺失权重时会显示“未配置”。
* MVTec 默认 STFPM checkpoint 解析路径是 `runs/real_model_pipeline/assets/mvtec/checkpoints/openvino_model/stfpm_capsule.xml`。
* 复用逻辑不应放在 scripts；scripts/app/service 应调用 `src/kgtracevis/` 下的核心模块。

## Assumptions (temporary)

* “权重”指模型权重/checkpoint，不是 KG edge 的 `weight` 字段。
* MVP 支持 MVTec 三个 preset 的下载入口：`mvtec-efficientad`、`mvtec-patchcore`、`mvtec-stfpm`；其中 STFPM 和 PatchCore 有内置可信默认源，EfficientAD 需要用户配置可信源。
* Web 工作台优先解决 MVTec 图片模式缺权重的问题，下载后刷新 preset 可用状态。

## Open Questions

* 是否以后要把 EfficientAD 的某个公开 checkpoint 固化为默认源？当前仓库只提供配置入口，不把未验证兼容性的组件权重写死为推理 checkpoint。

## Requirements (evolving)

* 将模型资产下载逻辑移入 `src/kgtracevis/` 可复用模块。
* 保留 CLI 下载方式，输出 JSON summary。
* 新增 Web API 下载入口，允许下载选定模型资产。
* React 图片模式中，当模型未配置时提供对应 preset 权重下载按钮，并在完成后刷新模型 preset。
* 下载 tar 时必须继续防路径穿越。
* 不把实际下载的大模型文件纳入 Git。

## Acceptance Criteria (evolving)

* [x] `uv run python scripts/download_model_assets.py --model mvtec-stfpm` 可下载或复用默认 STFPM 资产并输出 JSON。
* [x] CLI / API 白名单支持 `mvtec-efficientad`、`mvtec-patchcore`、`mvtec-stfpm` 三个 MVTec preset asset。
* [x] Makefile 默认下载目标不包含没有内置可信源的 EfficientAD，避免无参数下载失败。
* [x] Web API 暴露模型资产下载接口并返回 asset summary。
* [x] 前端可以触发下载，并下载后刷新 MVTec preset 状态。
* [x] API / 前端类型测试或现有测试更新通过。

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* 不为 EfficientAD 硬编码未经验证的公开源；除非用户提供可信 Hugging Face repo/file 或环境变量。
* 不实现异步任务队列或下载进度条；MVP 使用同步请求并显示状态。
* 不把下载权重提交到仓库。

## Technical Notes

* Inspected: `scripts/download_model_assets.py`, `src/kgtracevis/producers/mvtec_models.py`, `src/kgtracevis/service/api.py`, `src/kgtracevis/service/runs.py`, `web/src/App.tsx`, `web/src/lib/api.ts`, `web/src/types.ts`, `README.md`, `pyproject.toml`.
* Existing `download_model_assets.py` imports `huggingface_hub`, which is currently in the `ml` optional dependency group.
* Implemented reusable module `src/kgtracevis/producers/model_assets.py`; script, service API, and React client call through it.
* Extended MVTec download assets to `mvtec-efficientad`, `mvtec-patchcore`, and `mvtec-stfpm`; PatchCore now defaults to a capsule Anomalib Lightning checkpoint and uses the `anomalib-engine` backend.
* Verified with targeted pytest, ruff, mypy, web typecheck, and web build.
