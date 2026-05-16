"""Download small MVTec source artifacts for KG construction provenance."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_MVTEC_SOURCE_DIR = Path("docs/sources/mvtec_source_bundle")


@dataclass(frozen=True)
class DownloadableSource:
    """One source file to download or record for MVTec KG provenance."""

    source_id: str
    title: str
    url: str
    filename: str
    source_type: str
    used_for: str
    binary: bool = False


DEFAULT_MVTEC_SOURCES: tuple[DownloadableSource, ...] = (
    DownloadableSource(
        source_id="mvtec_ad_official_page",
        title="MVTec AD official dataset page",
        url="https://www.mvtec.com/research-teaching/datasets/mvtec-ad",
        filename="mvtec_ad_official_page.html",
        source_type="official_dataset_page",
        used_for="Dataset scope, categories, defect-free train/test defect split, annotations",
    ),
    DownloadableSource(
        source_id="mvtec_ad_paper_pdf",
        title="MVTec AD CVPR dataset paper PDF",
        url=(
            "https://openaccess.thecvf.com/content_CVPR_2019/papers/"
            "Bergmann_MVTec_AD_--_A_Comprehensive_Real-World_Dataset_for_"
            "Unsupervised_Anomaly_CVPR_2019_paper.pdf"
        ),
        filename="raw/mvtec_ad_cvpr_2019.pdf",
        source_type="official_dataset_paper",
        used_for="MVTec AD benchmark and industrial inspection context",
        binary=True,
    ),
    DownloadableSource(
        source_id="visual_defect_survey_html",
        title="Visual-based defect detection and classification survey",
        url="https://www.mdpi.com/1424-8220/20/5/1459",
        filename="visual_defect_survey_mdpi.html",
        source_type="industrial_visual_defect_survey",
        used_for=(
            "Industrial visual defect taxonomy, surface-defect categories, and "
            "inspection context"
        ),
    ),
    DownloadableSource(
        source_id="injection_molding_root_causes_pdf",
        title="Identifying possible root causes of defects for injection molding",
        url=(
            "https://pub-mediabox-storage.rxweb-prd.com/exhibitor/document/"
            "exh-ac965eb8-1f7e-4577-9ffa-6bad7499d9de/"
            "bf787ad1-f74c-4a00-a5fa-2b0e66adda3e.pdf"
        ),
        filename="raw/injection_molding_root_causes.pdf",
        source_type="manufacturing_defect_root_cause_paper",
        used_for=(
            "Process-level cause candidates for cracks, contamination, burn marks, "
            "and injection-molding visual defects"
        ),
        binary=True,
    ),
    DownloadableSource(
        source_id="injection_molding_defects_chart_pdf",
        title="Plastic injection molding defects chart",
        url=(
            "https://upmold.com/wp-content/uploads/Data-center/"
            "Plastic-Injection-Molding-Defects-Chart.pdf"
        ),
        filename="raw/plastic_injection_molding_defects_chart.pdf",
        source_type="manufacturing_defect_cause_table",
        used_for=(
            "Defect-to-cause table for contamination, cracking, deformation, "
            "surface appearance, and process remedies"
        ),
        binary=True,
    ),
    DownloadableSource(
        source_id="patchcore_arxiv_abs",
        title="PatchCore arXiv abstract page",
        url="https://arxiv.org/abs/2106.08265",
        filename="patchcore_arxiv_abs.html",
        source_type="method_paper_page",
        used_for="PatchCore anomaly detection and localization evidence boundary",
    ),
    DownloadableSource(
        source_id="patchcore_arxiv_pdf",
        title="PatchCore paper PDF",
        url="https://arxiv.org/pdf/2106.08265",
        filename="raw/patchcore_2106_08265.pdf",
        source_type="method_paper",
        used_for="PatchCore anomaly detection and localization evidence boundary",
        binary=True,
    ),
)


def download_mvtec_source_bundle(
    output_dir: str | Path = DEFAULT_MVTEC_SOURCE_DIR,
    *,
    sources: Sequence[DownloadableSource] = DEFAULT_MVTEC_SOURCES,
    overwrite: bool = False,
    include_binary: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    """Download MVTec source files and write a manifest."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    raw_dir = destination / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    records: list[dict[str, object]] = []
    for source in sources:
        output_path = destination / source.filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        status = "exists"
        byte_count = output_path.stat().st_size if output_path.exists() else 0
        error = ""
        if source.binary and not include_binary:
            status = "skipped_binary"
            byte_count = 0
        elif overwrite or not output_path.exists():
            try:
                content = _fetch_url(source.url, timeout_seconds=timeout_seconds)
            except (OSError, URLError) as exc:
                status = "failed"
                error = str(exc)
            else:
                output_path.write_bytes(content)
                status = "downloaded"
                byte_count = len(content)
        records.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "type": source.source_type,
                "url": source.url,
                "path": str(output_path),
                "used_for": source.used_for,
                "binary": source.binary,
                "status": status,
                "bytes": byte_count,
                "error": error,
            }
        )

    manifest: dict[str, object] = {
        "artifact_type": "mvtec_source_bundle_v0",
        "artifact_scope": "source_provenance_for_candidate_kg",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(destination),
        "sources": records,
        "note": (
            "HTML sources are downloaded by default. Raw PDFs are optional local "
            "provenance files; pass include_binary/--include-binary to download them. "
            "KG edges should cite source IDs and concise evidence summaries."
        ),
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_readme(destination, manifest)
    return manifest


def _fetch_url(url: str, *, timeout_seconds: int) -> bytes:
    request = Request(url, headers={"User-Agent": "KGTraceVis-source-bundler/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read()


def _write_readme(destination: Path, manifest: dict[str, object]) -> None:
    lines = [
        "# MVTec Source Bundle",
        "",
        "Downloaded provenance files for coverage-first MVTec candidate KG construction.",
        "Raw PDFs are optional, stored under `raw/`, and ignored by Git.",
        "",
        "Run `uv run python scripts/download_mvtec_sources.py --include-binary` when "
        "local PDF copies are needed for offline review.",
        "",
        "## Sources",
        "",
    ]
    sources = manifest.get("sources", [])
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            lines.append(
                f"- `{source['source_id']}`: {source['title']} -> `{source['path']}`"
            )
    lines.append("")
    (destination / "README.md").write_text("\n".join(lines), encoding="utf-8")
