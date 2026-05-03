"""Dataset adapters that output the unified evidence schema."""

from kgtracevis.adapters.batch import (
    BatchEvidenceSummary,
    evidence_from_records,
    load_records,
    summarize_evidence,
    write_evidence_files,
    write_evidence_jsonl,
)
from kgtracevis.adapters.ds_mvtec_adapter import (
    evidence_from_ds_mvtec_record,
    evidence_from_mvtec_record,
    from_ds_mvtec_record,
    from_mvtec_record,
)
from kgtracevis.adapters.tep_adapter import evidence_from_tep_record, from_tep_record
from kgtracevis.adapters.wafer_adapter import evidence_from_wafer_record, from_wafer_record
from kgtracevis.adapters.wm811k_adapter import evidence_from_wm811k_record, from_wm811k_record

__all__ = [
    "BatchEvidenceSummary",
    "evidence_from_ds_mvtec_record",
    "evidence_from_records",
    "evidence_from_mvtec_record",
    "evidence_from_tep_record",
    "evidence_from_wafer_record",
    "evidence_from_wm811k_record",
    "from_ds_mvtec_record",
    "from_mvtec_record",
    "from_tep_record",
    "from_wafer_record",
    "from_wm811k_record",
    "load_records",
    "summarize_evidence",
    "write_evidence_files",
    "write_evidence_jsonl",
]
