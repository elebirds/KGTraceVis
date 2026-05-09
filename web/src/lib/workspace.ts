import type { Evidence } from "../types";

export function casePathCount(item: Record<string, unknown>) {
  const paths = item.top_k_paths;
  return Array.isArray(paths) ? paths.length : null;
}

export function fieldsFromEvidence(evidence: Evidence) {
  return {
    anomaly_type: evidence.anomaly_type ?? "",
    location: evidence.location ?? "",
    morphology: evidence.morphology ?? "",
    variables: evidence.raw_evidence.variables.join("\n"),
    log_events: evidence.raw_evidence.log_events.join("\n"),
    severity: evidence.severity === null || evidence.severity === undefined ? "" : String(evidence.severity),
    confidence:
      evidence.confidence === null || evidence.confidence === undefined
        ? ""
        : String(evidence.confidence),
  };
}

export function splitLines(value: string) {
  return value
    .replaceAll(",", "\n")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

export function displayUploadMode(value: string) {
  if (value === "records") {
    return "记录包";
  }
  if (value === "evidence") {
    return "Evidence JSON";
  }
  if (value === "image") {
    return "图片模式";
  }
  return value;
}

export function displayRunStatus(value: string) {
  if (value === "completed") {
    return "已完成";
  }
  if (value === "failed") {
    return "失败";
  }
  return value;
}

export function displayDataset(value: string | null | undefined) {
  if (!value || value === "auto") {
    return "自动";
  }
  return value;
}

export function displaySourceKind(value: string) {
  if (value === "real_model_pipeline") {
    return "真实模型输出";
  }
  if (value === "checked_in_example") {
    return "内置示例";
  }
  if (value === "external_evidence") {
    return "外部 Evidence";
  }
  return value;
}

export function displayFeedbackTarget(value: string) {
  if (value === "path") {
    return "候选路径";
  }
  if (value === "case") {
    return "样本";
  }
  if (value === "link") {
    return "实体链接";
  }
  if (value === "correction") {
    return "修正候选";
  }
  return value;
}

export function displayFeedbackDecision(value: string) {
  if (value === "accept") {
    return "接受";
  }
  if (value === "reject") {
    return "拒绝";
  }
  if (value === "comment") {
    return "备注";
  }
  return value;
}

export function displayWorkflowTitle(value: string) {
  const titles: Record<string, string> = {
    "Upload sample": "上传样本",
    "Upload sample bundle": "上传样本包",
    "Validate evidence": "校验 Evidence",
    "Run pipeline": "运行 pipeline",
    "Run KGTracePipeline": "运行 KGTracePipeline",
    "Convert records to evidence": "记录转换为 Evidence",
    "Load evidence case": "加载 Evidence 样本",
    "Upload image": "上传图片",
    "Run MVTec predictor": "运行 MVTec 模型",
    "Build evidence": "构建 Evidence",
  };
  return titles[value] ?? value;
}

export function displayWorkflowSummary(value: string) {
  return value
    .replace(/^Received /, "已接收 ")
    .replace(/^Validated /, "已校验 ")
    .replace(/^Loaded (.+) from /, "已从路径加载 $1：")
    .replace(/^Generated anomaly prediction and geometry outputs$/, "已生成异常预测和几何特征输出")
    .replace(/^Converted the image sample into unified evidence JSON$/, "已将图片样本转换为统一 Evidence JSON")
    .replace("Evidence schema and observed fields are ready for analysis", "Evidence schema 和观测字段已准备好分析")
    .replace(/ evidence files written$/, " 个 Evidence 文件已写入")
    .replace(/ linked entities, /, " 个实体链接，")
    .replace(/ candidate explanation cases ready$/, " 个候选解释样本已就绪")
    .replace(/ paths$/, " 条路径")
    .replace(/ candidate paths$/, " 条候选路径");
}

export function displayArtifactKey(value: string) {
  const labels: Record<string, string> = {
    run_dir: "运行目录",
    input_path: "输入路径",
    output_dir: "输出目录",
    summary_path: "摘要路径",
    table_path: "表格路径",
    claim_boundary: "结论边界",
  };
  return labels[value] ?? value;
}

export function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "发生了未预期的错误";
}
