"""MED-RT (Medication Reference Terminology, VA): drugs and the diseases they treat.

MED-RT describes RxNorm ingredients by named associations to MeSH diseases
(indications, contraindications) and to its own classes (mechanism of action,
physiologic effect, established pharmacologic class). Only the drug-disease
associations are read; the MED-RT classes are not loaded.

* Concepts, relations, mappings: none. The MeSH records MED-RT names are loaded
  by the ``mesh`` source, which reads :meth:`MedRtReader.mesh_concepts` to load
  them whatever their tree.
* Associations: ``rxnorm:<RXCUI>`` -> ``mesh:<M...>``, one per MED-RT
  association, typed by :data:`TYPES` (``may_treat`` -> ``MAY_TREAT``, ...),
  with ``authority`` (who asserts it: ``MEDRT``, ``FMTSME``, ...) and the MED-RT
  name (``medrt_name``). MED-RT names MeSH *concepts* (``M0006155``), not
  records; ``bind`` resolves each to its descriptor or supplementary record
  (:meth:`MeshReader.match`), so the edges end on ``mesh:D003924``.
  Associations from MED-RT's own drug concepts (no RxNorm ingredient) are left
  out.
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from typing import ClassVar

from clinical_graph.model import (
    Association,
    Concept,
    Mapping,
    Relation,
    Vocabulary,
    concept_id,
)
from clinical_graph.vocabularies.base import VocabularyReader

XML = "Core_MEDRT_{v}_XML.xml"

MEDRT_PROVENANCE = "MED-RT"

TYPES = {
    "may_treat": "MAY_TREAT",
    "may_prevent": "MAY_PREVENT",
    "may_diagnose": "MAY_DIAGNOSE",
    "CI_with": "CONTRAINDICATED_WITH",
    "induces": "INDUCES",
}
"""MED-RT drug-disease association name -> relationship type."""

_RXNORM = "RxNorm"
_MESH = "MeSH"


@dataclass(frozen=True, slots=True)
class _Link:
    """One drug-disease association as published."""

    name: str
    rxcui: str
    mesh: str
    authority: tuple[str, ...]


class MedRtReader(VocabularyReader):
    """Reader for the MED-RT XML release: MeSH diseases and drug associations."""

    source_key: ClassVar[str] = "medrt"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = ()
    provenances: ClassVar[tuple[str, ...]] = (MEDRT_PROVENANCE,)
    association_types: ClassVar[tuple[str, ...]] = tuple(TYPES.values())

    @cached_property
    def _links(self) -> list[_Link]:
        """The RxNorm -> MeSH associations of :data:`TYPES`, in file order."""
        links: list[_Link] = []
        for _, elem in ET.iterparse(self.path(XML)):
            if elem.tag != "association":
                continue
            name = elem.findtext("name") or ""
            if (
                name in TYPES
                and elem.findtext("from_namespace") == _RXNORM
                and elem.findtext("to_namespace") == _MESH
            ):
                links.append(
                    _Link(
                        name,
                        (elem.findtext("from_code") or "").strip(),
                        (elem.findtext("to_code") or "").strip(),
                        tuple(
                            v
                            for q in elem.iter("qualifier")
                            if q.findtext("name") == "Authority"
                            and (v := (q.findtext("value") or "").strip())
                        ),
                    )
                )
            elem.clear()
        return links

    def mesh_concepts(self) -> frozenset[str]:
        """The MeSH concept UIs (``M...``) a drug-disease association points to."""
        return frozenset(link.mesh for link in self._links)

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield nothing: the MeSH records are the ``mesh`` source's."""
        yield from ()

    def iter_relations(self) -> Iterator[Relation]:
        """Yield nothing."""
        yield from ()

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: MeSH is bound to the other vocabularies by UMLS."""
        yield from ()

    def iter_associations(self) -> Iterator[Association]:
        """Yield one RxNorm -> MeSH edge per drug-disease association."""
        for link in self._links:
            yield Association(
                concept_id(Vocabulary.RXNORM, link.rxcui),
                TYPES[link.name],
                concept_id(Vocabulary.MESH, link.mesh),
                MEDRT_PROVENANCE,
                properties={
                    "medrt_name": link.name,
                    "authority": list(link.authority),
                },
            )
