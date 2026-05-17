"""Registry for reasoning adapters and reasoning profile manifests."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from kgtracevis.core.rca import GenericGraphPathReasoner, RcaReasoner
from kgtracevis.core.reasoning_profile import (
    ReasoningProfileManifest,
    ResolvedReasoningProfile,
    resolve_reasoning_profile_paths,
)
from kgtracevis.workflows.tep_root_kgd import TepRootKgdConfig, TepRootKgdRcaProvider

DEFAULT_REASONING_PROFILE_DIR = Path("configs/reasoning_profiles")
DEFAULT_GENERIC_REASONING_PROFILE_ID = "generic_graph_path_default"
DEFAULT_TEP_REASONING_PROFILE_ID = "tep_root_kgd_default"

ReasonerFactory = Callable[[ResolvedReasoningProfile], RcaReasoner]


class ReasoningAdapterRegistry:
    """Resolve reasoning profiles and instantiate registered adapters."""

    def __init__(self, profile_dir: str | Path = DEFAULT_REASONING_PROFILE_DIR) -> None:
        """Create an empty registry bound to one reasoning-profile directory."""
        self.profile_dir = Path(profile_dir)
        self._factories: dict[str, ReasonerFactory] = {}
        self._profile_cache: dict[str, ResolvedReasoningProfile] = {}
        self._reasoner_cache: dict[tuple[str, str], RcaReasoner] = {}

    def register_adapter(self, adapter_name: str, factory: ReasonerFactory) -> None:
        """Register one adapter factory under a stable adapter name."""
        name = str(adapter_name)
        if name in self._factories:
            raise ValueError(f"reasoning adapter already registered: {name}")
        self._factories[name] = factory

    def manifest_path_for(self, profile_id: str) -> Path:
        """Return the manifest path for one reasoning profile identifier."""
        return self.profile_dir / str(profile_id) / "manifest.json"

    def resolve_profile(self, profile_id: str) -> ResolvedReasoningProfile:
        """Load and cache one reasoning profile manifest plus resolved paths."""
        key = str(profile_id)
        cached = self._profile_cache.get(key)
        if cached is not None:
            return cached

        manifest_path = self.manifest_path_for(key)
        if not manifest_path.is_file():
            raise FileNotFoundError(f"reasoning profile manifest not found: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ReasoningProfileManifest.model_validate(payload)
        if manifest.reasoning_profile_id != key:
            raise ValueError(
                "reasoning profile manifest id mismatch: "
                f"expected {key}, got {manifest.reasoning_profile_id}"
            )
        resolved = resolve_reasoning_profile_paths(manifest, manifest_path.parent)
        self._profile_cache[key] = resolved
        return resolved

    def list_profiles(
        self,
        dataset: str | None = None,
    ) -> list[ResolvedReasoningProfile]:
        """Return all registered reasoning profiles, optionally filtered by dataset."""
        manifests = sorted(self.profile_dir.glob('*/manifest.json'))
        profiles = [self.resolve_profile(path.parent.name) for path in manifests]
        if dataset is None:
            return profiles
        return [
            profile for profile in profiles if self.profile_supports_dataset(profile, dataset)
        ]

    def profile_supports_dataset(
        self,
        profile: ResolvedReasoningProfile,
        dataset: str | None,
    ) -> bool:
        """Return whether one profile declares compatibility with a dataset."""
        dataset_name = str(dataset or '').strip().lower()
        if not dataset_name:
            return True
        declared = {item.strip().lower() for item in profile.dataset_scope if item.strip()}
        if not declared:
            return True
        return dataset_name in declared

    def validate_profile_for_dataset(
        self,
        profile_id: str,
        dataset: str | None,
    ) -> ResolvedReasoningProfile:
        """Resolve one profile and raise when it is incompatible with the dataset."""
        profile = self.resolve_profile(profile_id)
        if not self.profile_supports_dataset(profile, dataset):
            raise ValueError(
                "reasoning profile "
                f"{profile.reasoning_profile_id} is not compatible with dataset {dataset}"
            )
        return profile

    def build_reasoner(self, profile_id: str) -> RcaReasoner:
        """Instantiate and cache the adapter configured by one profile."""
        profile = self.resolve_profile(profile_id)
        cache_key = (profile.reasoner_adapter, profile.reasoning_profile_id)
        cached = self._reasoner_cache.get(cache_key)
        if cached is not None:
            return cached

        factory = self._factories.get(profile.reasoner_adapter)
        if factory is None:
            raise ValueError(
                f"reasoning adapter is not registered: {profile.reasoner_adapter}"
            )
        reasoner = factory(profile)
        self._reasoner_cache[cache_key] = reasoner
        return reasoner

    def resolve_reasoner(
        self,
        profile_id: str,
    ) -> tuple[ResolvedReasoningProfile, RcaReasoner]:
        """Return the resolved profile and its instantiated adapter."""
        profile = self.resolve_profile(profile_id)
        return profile, self.build_reasoner(profile.reasoning_profile_id)

    def default_profile_id_for_dataset(self, dataset: str | None) -> str:
        """Return the built-in default profile for one dataset."""
        return resolve_default_reasoning_profile_id(dataset)

    def resolve_default_reasoner(
        self,
        dataset: str | None,
    ) -> tuple[ResolvedReasoningProfile, RcaReasoner]:
        """Resolve the built-in default profile and adapter for one dataset."""
        return self.resolve_reasoner(self.default_profile_id_for_dataset(dataset))


def resolve_default_reasoning_profile_id(dataset: str | None) -> str:
    """Return the built-in reasoning profile id for one dataset string."""
    if str(dataset or '').strip().lower() == 'tep':
        return DEFAULT_TEP_REASONING_PROFILE_ID
    return DEFAULT_GENERIC_REASONING_PROFILE_ID


@lru_cache(maxsize=1)
def default_reasoning_registry() -> ReasoningAdapterRegistry:
    """Return the singleton registry for built-in reasoning adapters."""
    registry = ReasoningAdapterRegistry()
    registry.register_adapter('generic_graph_path', _build_generic_graph_path_reasoner)
    registry.register_adapter('tep_root_kgd', _build_tep_root_kgd_reasoner)
    return registry


def _build_generic_graph_path_reasoner(
    profile: ResolvedReasoningProfile,
) -> RcaReasoner:
    del profile
    return GenericGraphPathReasoner()


def _build_tep_root_kgd_reasoner(profile: ResolvedReasoningProfile) -> RcaReasoner:
    asset_dir = _shared_asset_dir(profile)
    return TepRootKgdRcaProvider(
        TepRootKgdConfig(
            asset_dir=asset_dir,
            source_name=profile.reasoner_adapter,
        )
    )


def _shared_asset_dir(profile: ResolvedReasoningProfile) -> Path:
    paths = profile.all_resolved_paths()
    if not paths:
        raise ValueError(
            f"reasoning profile has no resolved asset paths: {profile.reasoning_profile_id}"
        )
    asset_dir = paths[0].parent
    for path in paths[1:]:
        if path.parent != asset_dir:
            raise ValueError(
                'reasoning profile mixes asset directories: '
                f'{profile.reasoning_profile_id}'
            )
    return asset_dir
