"""Base protocol and registry for KG construction extractors."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource


class KGSourceExtractor(Protocol):
    """Protocol implemented by source-to-DraftKG extractor plugins."""

    name: str
    version: str
    supported_source_types: tuple[str, ...]

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Extract draft KG rows from one source."""


class ExtractorRegistry:
    """Registry for source-type-specific KG extractors."""

    def __init__(self, extractors: Iterable[KGSourceExtractor] = ()) -> None:
        self._extractors_by_source_type: dict[str, KGSourceExtractor] = {}
        for extractor in extractors:
            self.register(extractor)

    def register(self, extractor: KGSourceExtractor) -> None:
        """Register an extractor for each supported source type."""
        for source_type in extractor.supported_source_types:
            self._extractors_by_source_type[source_type] = extractor

    def extractor_for(self, source_type: str) -> KGSourceExtractor:
        """Return the extractor registered for a source type."""
        extractor = self._extractors_by_source_type.get(source_type)
        if extractor is None:
            raise ValueError(f"no KG source extractor registered for source_type={source_type}")
        return extractor

    @property
    def source_types(self) -> tuple[str, ...]:
        """Return registered source types."""
        return tuple(sorted(self._extractors_by_source_type))
