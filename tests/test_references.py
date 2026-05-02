import csv
from pathlib import Path

REFERENCE_DIR = Path("data/references")
REFERENCE_FILES = [
    REFERENCE_DIR / "mvtec_plausible_rca_reference.csv",
    REFERENCE_DIR / "tep_rca_reference.csv",
    REFERENCE_DIR / "wafer_plausible_reference.csv",
]

REQUIRED_COLUMNS = {
    "reference_id",
    "case_id",
    "dataset",
    "label_scope",
    "target_type",
    "target_id",
    "path_node_sequence",
    "annotation_type",
    "source",
    "evidence",
    "confidence",
    "review_status",
    "evaluation_eligible",
    "notes",
}


def test_reference_files_have_required_columns_and_rows() -> None:
    for path in REFERENCE_FILES:
        rows = _read_rows(path)
        assert rows, f"{path} should contain at least one reference row"
        assert REQUIRED_COLUMNS.issubset(rows[0]), f"{path} is missing required columns"


def test_demo_references_do_not_claim_verified_mvtec_or_wafer_rca() -> None:
    paths = (
        REFERENCE_DIR / "mvtec_plausible_rca_reference.csv",
        REFERENCE_DIR / "wafer_plausible_reference.csv",
    )
    for path in paths:
        for row in _read_rows(path):
            assert row["annotation_type"] != "native_ground_truth"
            assert row["evaluation_eligible"].lower() == "false"
            claim_text = " ".join(row.values()).lower()
            assert "verified factory" not in claim_text


def test_primary_eligible_references_are_not_llm_candidates() -> None:
    for path in REFERENCE_FILES:
        for row in _read_rows(path):
            if row["evaluation_eligible"].lower() == "true":
                assert row["annotation_type"] != "llm_candidate"
                assert row["source"]
                assert row["evidence"]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
