"""SNOMED CT International Edition, RF2 Snapshot.

Planned content:

* Concepts from ``sct2_Concept``; the name is the US-English preferred synonym
  (``der2_cRefset_Language``, refset 900000000000509007), the FSN and other
  active synonyms from ``sct2_Description``.
* Relations from the *inferred* ``sct2_Relationship`` file (characteristic type
  900000000000011006): ``ISA`` (116680003) and the attribute relationships, named
  after the attribute's preferred term; ``REPLACEDBY`` / ``SAMEAS`` / ... for
  inactive concepts from ``der2_cRefset_Association``.
* Mappings from ``der2_iisssccRefset_ExtendedMap`` (refset 447562003) to **WHO
  ICD-10** (``Vocabulary.ICD10``), keeping map group, priority, rule and advice;
  optionally ICD-O-3 from ``der2_sRefset_SimpleMap`` (refset 446608001).
"""

from collections.abc import Iterator

from clinical_graph.model import Concept, Mapping, Relation
from clinical_graph.vocabularies.base import VocabularyReader


class SnomedReader(VocabularyReader):
    """Reader for the SNOMED CT RF2 Snapshot."""

    source_key = "snomed"

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield SNOMED CT concepts."""
        raise NotImplementedError

    def iter_relations(self) -> Iterator[Relation]:
        """Yield inferred relationships and historical associations."""
        raise NotImplementedError

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the SNOMED CT -> ICD-10 (WHO) map."""
        raise NotImplementedError
