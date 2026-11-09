"""MeSH (NLM): the disease trees, and every MeSH record MED-RT links a drug to.

MeSH is the NLM's subject vocabulary for indexing the literature; most of it
(anatomy, organisms, chemicals, techniques, geography, ...) is covered better by
the other vocabularies here, so only part of it is loaded:

* Concepts: the descriptors (``mesh:D003924``, kind ``descriptor``) with a tree
  number in C (Diseases) or F03 (Mental Disorders), and every other descriptor
  or supplementary concept record (``mesh:C562385``, kind ``supplementary``)
  that has a concept MED-RT links a drug to (read from the ``medrt`` source if it
  is on disk). ``name`` is the record's name, ``synonyms`` its entry terms
  without the permuted ones (``Diabetes Mellitus, Adult-Onset`` but not
  ``Adult-Onset Diabetes Mellitus``); properties ``tree_numbers`` (descriptors)
  and ``scope_note`` (the preferred concept's scope note; the record's note for
  supplementary records).
* Relations: ``ISA`` from the tree numbers (``C18.452.394.750.149`` under
  ``C18.452.394.750``), between loaded descriptors; and from a supplementary
  record to the descriptors it is mapped to (``HeadingMappedTo``), with
  ``heading_mapped_to: true``.
* Mappings: none; UMLS binds MeSH to the other vocabularies.

Records are named by their UI (``D...``, ``C...``). MED-RT names MeSH *concepts*
(``M...``); :meth:`MeshReader.match` resolves a concept to its record: ``exact``
for the record's preferred concept (``M0006155`` of ``D003924`` *Diabetes
Mellitus, Type 2*), ``entry_concept`` for one of its narrower concepts.
"""

import gzip
import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import ClassVar

from clinical_graph.model import (
    Concept,
    Mapping,
    PropertyValue,
    Relation,
    Vocabulary,
    concept_id,
)
from clinical_graph.sources import load_manifest
from clinical_graph.vocabularies.base import VocabularyReader
from clinical_graph.vocabularies.medrt import XML as MEDRT_XML
from clinical_graph.vocabularies.medrt import MedRtReader

log = logging.getLogger(__name__)

DESCRIPTORS = "desc{v}.gz"
SUPPLEMENTARY = "supp{v}.gz"

MEDRT_SOURCE = "medrt"

TREES = ("C", "F03")
"""Tree number prefixes loaded in full: Diseases, Mental Disorders."""


@dataclass(frozen=True, slots=True)
class _Record:
    """One MeSH descriptor or supplementary concept record, as loaded."""

    ui: str
    name: str
    kind: str
    synonyms: tuple[str, ...]
    tree_numbers: tuple[str, ...]
    headings: tuple[str, ...]  # supplementary: the descriptors it is mapped to
    scope_note: str | None
    concepts: tuple[tuple[str, bool], ...]  # (concept UI, preferred)


def _text(elem: ET.Element, path: str) -> str:
    return " ".join((elem.findtext(path) or "").split())


def _record(elem: ET.Element, kind: str) -> _Record:
    """Read a ``DescriptorRecord`` or ``SupplementalRecord`` element."""
    supplementary = kind == "supplementary"
    ui = _text(elem, "SupplementalRecordUI" if supplementary else "DescriptorUI")
    name = _text(
        elem,
        "SupplementalRecordName/String" if supplementary else "DescriptorName/String",
    )
    concepts: list[tuple[str, bool]] = []
    terms: list[str] = []
    scope_note = _text(elem, "Note") if supplementary else ""
    for concept in elem.iter("Concept"):
        preferred = concept.get("PreferredConceptYN") == "Y"
        concepts.append((_text(concept, "ConceptUI"), preferred))
        if preferred and not supplementary:
            scope_note = _text(concept, "ScopeNote")
        for term in concept.iter("Term"):
            if term.get("IsPermutedTermYN") != "Y":
                terms.append(_text(term, "String"))
    seen = {name.lower()}
    synonyms: list[str] = []
    for term in terms:
        if term and term.lower() not in seen:
            seen.add(term.lower())
            synonyms.append(term)
    return _Record(
        ui=ui,
        name=name,
        kind=kind,
        synonyms=tuple(synonyms),
        tree_numbers=tuple((t.text or "").strip() for t in elem.iter("TreeNumber")),
        headings=tuple(
            _text(h, "DescriptorReferredTo/DescriptorUI").lstrip("*")
            for h in elem.iter("HeadingMappedTo")
        ),
        scope_note=scope_note or None,
        concepts=tuple(concepts),
    )


def _records(path: Path, tag: str, kind: str) -> Iterator[_Record]:
    """The records of one gzipped MeSH XML file, one at a time."""
    with gzip.open(path) as fh:
        for _, elem in ET.iterparse(fh):
            if elem.tag == tag:
                yield _record(elem, kind)
                elem.clear()


class MeshReader(VocabularyReader):
    """Reader for the MeSH XML release: disease descriptors and MED-RT targets."""

    source_key: ClassVar[str] = "mesh"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.MESH,)

    @cached_property
    def _medrt_concepts(self) -> frozenset[str]:
        """The MeSH concept UIs MED-RT links a drug to; empty if not on disk."""
        try:
            reader = MedRtReader(load_manifest()[MEDRT_SOURCE], self.raw_dir)
        except KeyError:
            reader = None
        if reader is None or not reader.has(MEDRT_XML):
            log.warning("MED-RT not found: MeSH loaded without its extra records")
            return frozenset()
        return reader.mesh_concepts()

    def _wanted(self, record: _Record) -> bool:
        return any(t.startswith(TREES) for t in record.tree_numbers) or any(
            ui in self._medrt_concepts for ui, _ in record.concepts
        )

    @cached_property
    def _loaded(self) -> dict[str, _Record]:
        """The loaded records by UI: descriptors first, then supplementary ones."""
        records: dict[str, _Record] = {}
        for record in _records(
            self.path(DESCRIPTORS), "DescriptorRecord", "descriptor"
        ):
            if self._wanted(record):
                records[record.ui] = record
        found = {ui for r in records.values() for ui, _ in r.concepts}
        if self._medrt_concepts - found:
            for record in _records(
                self.path(SUPPLEMENTARY), "SupplementalRecord", "supplementary"
            ):
                if any(ui in self._medrt_concepts for ui, _ in record.concepts):
                    records[record.ui] = record
        return records

    @cached_property
    def _concepts(self) -> dict[str, tuple[str, bool]]:
        """Concept UI -> (record UI, preferred concept of it), loaded records only."""
        return {
            ui: (record.ui, preferred)
            for record in self._loaded.values()
            for ui, preferred in record.concepts
        }

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield every loaded descriptor and supplementary record."""
        for record in self._loaded.values():
            properties: dict[str, PropertyValue] = {"scope_note": record.scope_note}
            if record.tree_numbers:
                properties["tree_numbers"] = list(record.tree_numbers)
            yield Concept(
                Vocabulary.MESH,
                record.ui,
                record.name,
                kind=record.kind,
                synonyms=record.synonyms,
                properties=properties,
            )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield ``ISA`` from the tree numbers and the heading mappings."""
        loaded = self._loaded
        by_tree = {t: r.ui for r in loaded.values() for t in r.tree_numbers}
        for record in loaded.values():
            parents: list[str] = []
            for tree in record.tree_numbers:
                parent = by_tree.get(tree.rpartition(".")[0])
                if parent is not None and parent != record.ui:
                    parents.append(parent)
            for parent in dict.fromkeys(parents):
                yield Relation(
                    concept_id(Vocabulary.MESH, record.ui),
                    "ISA",
                    concept_id(Vocabulary.MESH, parent),
                )
            for heading in dict.fromkeys(record.headings):
                if heading in loaded:
                    yield Relation(
                        concept_id(Vocabulary.MESH, record.ui),
                        "ISA",
                        concept_id(Vocabulary.MESH, heading),
                        properties={"heading_mapped_to": True},
                    )

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: MeSH is bound to the other vocabularies by UMLS."""
        yield from ()

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve a record UI, or a concept UI (``M...``, as MED-RT names them).

        Returns:
            The record's concept id and how it matched (``exact``, or
            ``entry_concept`` for a concept that is not the record's preferred
            one), or ``None``.
        """
        found = super().match(vocabulary, code)
        if found is not None or vocabulary is not Vocabulary.MESH:
            return found
        hit = self._concepts.get(code.strip())
        if hit is None:
            return None
        ui, preferred = hit
        return concept_id(
            Vocabulary.MESH, ui
        ), "exact" if preferred else "entry_concept"
