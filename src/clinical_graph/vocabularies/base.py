"""Common interface of the vocabulary readers."""

import csv
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from clinical_graph.model import Concept, Mapping, Relation, Vocabulary
from clinical_graph.sources.manifest import Source


class VocabularyReader(ABC):
    """Read one source release into concepts, relations and mappings.

    Subclasses set :attr:`source_key` to their ``sources.toml`` key and
    :attr:`vocabularies` to the vocabularies their concepts belong to, and
    implement the three ``iter_*`` methods as generators.
    """

    source_key: ClassVar[str]
    vocabularies: ClassVar[tuple[Vocabulary, ...]]

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
        """Return the absolute path of a file listed in the manifest.

        Args:
            manifest_path: The path as in ``sources.toml``; ``{v}`` is replaced by
                the source's ``version``, so readers need no release dates.
        """
        return self.source.file(
            manifest_path.format(v=self.source.version), self.raw_dir
        )

    def has(self, manifest_path: str) -> bool:
        """Whether a (typically optional) manifest file is present on disk."""
        return self.path(manifest_path).is_file()

    def read_csv(self, manifest_path: str) -> Iterator[dict[str, str]]:
        """Yield the rows of a comma-separated manifest file as dicts."""
        with self.path(manifest_path).open(encoding="utf-8-sig", newline="") as fh:
            yield from csv.DictReader(fh)

    def read_tsv(self, manifest_path: str) -> Iterator[dict[str, str]]:
        """Yield the rows of an unquoted tab-separated manifest file (RF2) as dicts."""
        with self.path(manifest_path).open(encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)

    @abstractmethod
    def iter_concepts(self) -> Iterator[Concept]:
        """Yield every concept of the release."""

    @abstractmethod
    def iter_relations(self) -> Iterator[Relation]:
        """Yield the edges between concepts of this vocabulary."""

    @abstractmethod
    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the bindings from this vocabulary to other vocabularies."""
