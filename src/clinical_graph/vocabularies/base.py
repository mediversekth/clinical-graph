"""Common interface of the vocabulary readers."""

import csv
from abc import ABC, abstractmethod
from collections.abc import Iterator
from functools import cached_property
from pathlib import Path
from typing import ClassVar

from clinical_graph.model import Concept, Mapping, Relation, Vocabulary, concept_id
from clinical_graph.sources.manifest import Source


class VocabularyReader(ABC):
    """Read one source release into concepts, relations and mappings.

    Subclasses set :attr:`source_key` to their ``sources.toml`` key and
    :attr:`vocabularies` to the vocabularies their concepts belong to, and
    implement the three ``iter_*`` methods as generators.
    """

    source_key: ClassVar[str]
    vocabularies: ClassVar[tuple[Vocabulary, ...]]
    provenances: ClassVar[tuple[str, ...]] = ()
    """``provenance`` of the mappings :meth:`iter_mappings` yields; ``bind
    --replace`` deletes only the ``MAPS_TO`` edges with these."""
    extension: ClassVar[str | None] = None
    """Set by a reader of an extension to another reader's vocabulary (the SNOMED
    CT LOINC Extension): its nodes carry this as their ``extension`` property, and
    ``ingest --replace`` deletes only them; the base reader's (``None``) deletes
    only nodes without one."""
    supplementary: ClassVar[bool] = False
    """The reader's mappings join codes published by other sources (UMLS: codes
    sharing a CUI), so ``bind`` resolves both ends, accepts only exact or
    normalised matches (a broader code is not a synonym), and writes only pairs
    of concepts that no other map links yet. Bind it after the others."""

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

    @cached_property
    def concept_ids(self) -> frozenset[str]:
        """Ids of every concept this reader yields (reads the release once)."""
        return frozenset(c.id for c in self.iter_concepts())

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve a code published by another source (a map target) to a concept.

        The default accepts the code only as given; readers whose codes are
        published in variant forms override it.

        Returns:
            The concept id and how it matched (``"exact"``, ...), or ``None``.
        """
        cid = concept_id(vocabulary, code)
        return (cid, "exact") if cid in self.concept_ids else None

    @abstractmethod
    def iter_concepts(self) -> Iterator[Concept]:
        """Yield every concept of the release."""

    @abstractmethod
    def iter_relations(self) -> Iterator[Relation]:
        """Yield the edges between concepts of this vocabulary."""

    @abstractmethod
    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the bindings from this vocabulary to other vocabularies."""
