"""SNOMED CT LOINC Extension (the LOINC Ontology), RF2, with its history.

Regenstrief and SNOMED International model LOINC terms as SNOMED CT concepts
(observable entities) in their own module, 11010000107, on top of the
International Edition. The files have the International layout, so this reader
is :class:`SnomedReader` on the extension's files (``_LO1010000_``).

* Concepts: every concept of the extension, active and inactive, as ``SNOMEDCT``
  nodes like the International ones, plus ``extension: "loinc"`` and, for those
  modelling a LOINC term, its ``loinc_code``. Besides the observable entities the
  extension adds the substances, qualifiers, ... they need (some with
  International-format ids). Concepts that are also in the loaded International
  release (re-published in the extension module, which is built on a newer
  International release) are skipped: the International node stays as it is.
* Relations: as for the International Edition: inferred relationships (``ISA``
  into the International hierarchy, ``COMPONENT``, ``PROPERTY``, ``DIRECT_SITE``,
  ``SCALE_TYPE``, ``TIME_ASPECT``, ``TECHNIQUE``, ``INHERES_IN``, ...) and
  historical associations. Their targets are mostly International concepts, so
  load the International Edition first; edges to International concepts newer
  than the loaded release are skipped.
* Mappings: ``sct2_Identifier``, the LOINC code of each concept (identifier scheme
  30051010000102): ``loinc:<code>`` -> ``snomed:<id>``, ``equivalent``, one to one.

Names of the International concepts the extension refers to (attribute types,
association refsets, inactivation reasons) come from the International release.
"""

import dataclasses
from collections.abc import Iterator
from functools import cached_property
from typing import ClassVar

from clinical_graph.model import (
    Concept,
    Mapping,
    MappingEquivalence,
    Vocabulary,
    concept_id,
)
from clinical_graph.sources import load_manifest
from clinical_graph.vocabularies.snomed import CONCEPT, SnomedReader

IDENTIFIER = "Snapshot/Terminology/sct2_Identifier_Snapshot_{e}_{v}.txt"

EXTENSION = "loinc"
LOINC_CODE_SCHEME = "30051010000102"
LOINC_PROVENANCE = "SNOMED CT LOINC Extension: LOINC code identifiers"


class LoincExtensionReader(SnomedReader):
    """Reader for the SNOMED CT LOINC Extension RF2 release."""

    source_key: ClassVar[str] = "loinc_extension"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.SNOMED,)
    extension: ClassVar[str | None] = EXTENSION
    provenances: ClassVar[tuple[str, ...]] = (LOINC_PROVENANCE,)
    edition: ClassVar[str] = "LO1010000"

    @cached_property
    def _international(self) -> SnomedReader:
        """The International Edition, for the names of its concepts."""
        return SnomedReader(load_manifest()["snomed"], self.raw_dir)

    def _name(self, sctid: str) -> str:
        if sctid in self._terms.fsn:
            return super()._name(sctid)
        return self._international._name(sctid)

    @cached_property
    def _international_ids(self) -> frozenset[str]:
        """SCTIDs of the International release's concepts (its Concept file only)."""
        intl = self._international
        return frozenset(row["id"] for row in intl.read_tsv(intl._rf2(CONCEPT)))  # pyright: ignore[reportPrivateUsage]

    @cached_property
    def _loinc_codes(self) -> dict[str, str]:
        """Concept id -> LOINC code, active identifiers."""
        return {
            row["referencedComponentId"]: row["alternateIdentifier"]
            for row in self.read_tsv(self._rf2(IDENTIFIER))
            if row["active"] == "1" and row["identifierSchemeId"] == LOINC_CODE_SCHEME
        }

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield the extension's own concepts, active and inactive."""
        codes, international = self._loinc_codes, self._international_ids
        for concept in super().iter_concepts():
            if concept.code in international:
                continue
            yield dataclasses.replace(
                concept,
                properties={
                    **concept.properties,
                    "loinc_code": codes.get(concept.code),
                },
            )

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield LOINC term -> extension concept, from the LOINC code identifiers.

        Inactive identifiers are included with ``active: false``.
        """
        for row in self.read_tsv(self._rf2(IDENTIFIER)):
            if row["identifierSchemeId"] != LOINC_CODE_SCHEME:
                continue
            yield Mapping(
                source=concept_id(Vocabulary.LOINC, row["alternateIdentifier"]),
                target=concept_id(Vocabulary.SNOMED, row["referencedComponentId"]),
                equivalence=MappingEquivalence.EQUIVALENT,
                provenance=LOINC_PROVENANCE,
                properties={
                    "active": row["active"] == "1",
                    "effective_time": row["effectiveTime"],
                },
            )
