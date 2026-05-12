"""Reusable experiment automation helpers."""

from kgtracevis.experiments.adapter_pipeline import (
    AdapterPipelineOutput,
    adapter_pipeline_table_rows,
    run_adapter_pipeline,
    write_adapter_pipeline_table,
)
from kgtracevis.experiments.mvtec_patchcore import (
    PatchCoreObjectRunConfig,
    batch_row_from_object_summary,
    discover_ds_mvtec_object_dirs,
    run_patchcore_object,
    summarize_records,
)
from kgtracevis.experiments.paper_tables import (
    PaperTablesOutput,
    build_paper_tables,
)
from kgtracevis.experiments.suite import (
    ExperimentCommandResult,
    ExperimentSuiteResult,
    build_default_command_specs,
    run_experiment_suite,
)

__all__ = [
    "AdapterPipelineOutput",
    "ExperimentCommandResult",
    "ExperimentSuiteResult",
    "PaperTablesOutput",
    "PatchCoreObjectRunConfig",
    "adapter_pipeline_table_rows",
    "batch_row_from_object_summary",
    "build_paper_tables",
    "build_default_command_specs",
    "discover_ds_mvtec_object_dirs",
    "run_adapter_pipeline",
    "run_experiment_suite",
    "run_patchcore_object",
    "summarize_records",
    "write_adapter_pipeline_table",
]
