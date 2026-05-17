"""Reasoning profile manifests for RCA adapter resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ReasoningProfileManifest(BaseModel):
    """External reasoning profile manifest compatible with one adapter."""

    model_config = ConfigDict(extra="forbid")

    reasoning_profile_id: str
    dataset_scope: list[str] = Field(default_factory=list)
    reasoner_adapter: str
    version: str
    required_evidence_fields: list[str] = Field(default_factory=list)
    runtime_overlay: dict[str, str] = Field(default_factory=dict)
    reasoning_assets: dict[str, str] = Field(default_factory=dict)
    claim_boundary: str


@dataclass(frozen=True)
class ResolvedReasoningProfile:
    """Reasoning profile with manifest-relative paths resolved."""

    manifest: ReasoningProfileManifest
    root_dir: Path
    runtime_overlay: dict[str, Path] = field(default_factory=dict)
    reasoning_assets: dict[str, Path] = field(default_factory=dict)

    @property
    def reasoning_profile_id(self) -> str:
        """Return the stable profile identifier from the manifest."""
        return self.manifest.reasoning_profile_id

    @property
    def reasoner_adapter(self) -> str:
        """Return the registered adapter name required by this profile."""
        return self.manifest.reasoner_adapter

    @property
    def dataset_scope(self) -> tuple[str, ...]:
        """Return the declared dataset scope as an immutable tuple."""
        return tuple(self.manifest.dataset_scope)

    @property
    def required_evidence_fields(self) -> tuple[str, ...]:
        """Return required evidence field selectors as an immutable tuple."""
        return tuple(self.manifest.required_evidence_fields)

    def all_resolved_paths(self) -> tuple[Path, ...]:
        """Return every resolved overlay and reasoning-asset path."""
        return (
            *tuple(self.runtime_overlay.values()),
            *tuple(self.reasoning_assets.values()),
        )


def resolve_reasoning_profile_paths(
    manifest: ReasoningProfileManifest,
    root_dir: str | Path,
) -> ResolvedReasoningProfile:
    """Resolve manifest-relative runtime overlay and asset paths."""
    resolved_root = Path(root_dir).resolve()
    return ResolvedReasoningProfile(
        manifest=manifest,
        root_dir=resolved_root,
        runtime_overlay=_resolve_path_map(manifest.runtime_overlay, resolved_root),
        reasoning_assets=_resolve_path_map(manifest.reasoning_assets, resolved_root),
    )


def _resolve_path_map(entries: dict[str, str], root_dir: Path) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for key, value in entries.items():
        path = Path(value)
        if not path.is_absolute():
            path = (root_dir / path).resolve()
        resolved[str(key)] = path
    return resolved
