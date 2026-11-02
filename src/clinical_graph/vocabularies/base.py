"""Common interface of the vocabulary readers."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from clinical_graph.model import Concept, Mapping, Relation
from clinical_graph.sources.manifest import Source


class VocabularyReader(ABC):
    """Read one source release into concepts, relations and mappings.

    Subclasses set :attr:`source_key` to their ``sources.toml`` key and implement
    the three ``iter_*`` methods as generators, so a release never has to fit in
    memory at once.
    """

    source_key: str

    def __init__(self, source: Source, raw_dir: Path | None = None) -> None:
        """Bind the reader to a release on disk.

        Args:
            source: The manifest entry for this vocabulary.
            raw_dir: The raw data directory; defaults to :func:`paths.raw_dir`.

        Raises:
            ValueError: If ``source`` is not the source this reader handles.
        """
        if source.key != self.source_key:
            raise ValueError(
                f"{type(self).__name__} reads {self.source_key!r}, got {source.key!r}"
            )
        self.source = source
        self.raw_dir = raw_dir

    def path(self, manifest_path: str) -> Path:
        """Return the absolute path of a file listed in the manifest."""
        return self.source.file(manifest_path, self.raw_dir)

    @abstractmethod
    def iter_concepts(self) -> Iterator[Concept]:
        """Yield every concept of the release."""

    @abstractmethod
    def iter_relations(self) -> Iterator[Relation]:
        """Yield the edges between concepts of this vocabulary."""

    @abstractmethod
    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the bindings from this vocabulary to other vocabularies."""
