"""NLM SNOMED CT to ICD-10-CM map, human-readable release.

The map is published by NLM with the SNOMED CT US Edition (ICD-10-CM complex map
reference set 6011000124106). The graph keeps the International Edition, so only
this map file is read: its rows whose source concept is US-only or newer than the
loaded release match no node and are skipped by ``bind``.

* Concepts, relations: none; this source only links the SNOMED CT and ICD-10-CM
  graphs.
* Mappings: every row with a target, ``snomed:<id>`` -> ``icd10cm:<code>``, keyed
  by the refset member id. Like the WHO ICD-10 map: one target per map group,
  alternatives in ``map_priority`` order chosen by ``map_rule``. A target ending
  in ``?`` (``S72.001?``) leaves the 7th character (encounter: initial,
  subsequent, sequela) to the coder; it resolves to the code it extends. The
  human-readable file holds active rows only.
"""

from collections.abc import Iterator
from typing import ClassVar

from clinical_graph.model import (
    Concept,
    Mapping,
    MappingEquivalence,
    Relation,
    Vocabulary,
    concept_id,
)
from clinical_graph.vocabularies.base import VocabularyReader

MAP = "tls_Icd10cmHumanReadableMap_US1000124_{v}.tsv"

ICD10CM_MAP = "6011000124106"
ICD10CM_MAP_PROVENANCE = "NLM SNOMED CT map to ICD-10-CM (refset 6011000124106)"

CORRELATION = {
    "447561005": "SNOMED CT source code to target map code correlation not specified",
}
"""Preferred terms of the correlation ids (the file gives ids only)."""


class SnomedIcd10CmMapReader(VocabularyReader):
    """Reader for the NLM SNOMED CT -> ICD-10-CM map; yields mappings only."""

    source_key: ClassVar[str] = "snomed_icd10cm"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = ()
    provenances: ClassVar[tuple[str, ...]] = (ICD10CM_MAP_PROVENANCE,)

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield nothing: the map adds no concepts."""
        yield from ()

    def iter_relations(self) -> Iterator[Relation]:
        """Yield nothing: the map adds no relations within a vocabulary."""
        yield from ()

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the SNOMED CT -> ICD-10-CM map rows that have a target.

        The target id holds the code as published (``?`` included); the binding
        step resolves it against the ICD-10-CM graph (``Icd10CmReader.match``).
        """
        for row in self.read_tsv(MAP):
            target = row["mapTarget"].strip()
            if row["refsetId"] != ICD10CM_MAP or not target:
                continue
            correlation = row["correlationId"]
            yield Mapping(
                source=concept_id(Vocabulary.SNOMED, row["referencedComponentId"]),
                target=concept_id(Vocabulary.ICD10CM, target),
                equivalence=MappingEquivalence.UNSPECIFIED,
                provenance=ICD10CM_MAP_PROVENANCE,
                key=row["id"],
                properties={
                    "active": row["active"] == "1",
                    "effective_time": row["effectiveTime"],
                    "refset_id": row["refsetId"],
                    "map_group": int(row["mapGroup"]),
                    "map_priority": int(row["mapPriority"]),
                    "map_rule": row["mapRule"] or None,
                    "map_advice": row["mapAdvice"] or None,
                    # Upper-cased in this file; the SNOMED CT term is sentence case.
                    "map_category": row["mapCategoryName"].capitalize() or None,
                    "correlation": CORRELATION.get(correlation, correlation),
                },
            )
