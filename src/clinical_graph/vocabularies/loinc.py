"""LOINC release (terms, parts and accessory files).

Planned content:

* Concepts: terms from ``Loinc.csv`` (``kind="term"``), parts from ``Part.csv``
  (``kind="part"``), and optionally groups and answer lists.
* Relations: term -> part from ``LoincPartLink_Primary`` / ``_Supplementary``
  (relationship named after the part type: ``COMPONENT``, ``PROPERTY``,
  ``SYSTEM``, ...); ``ISA`` from ``ComponentHierarchyBySystem``; ``REPLACEDBY``
  from ``MapTo.csv``; ``INPANEL`` / ``INGROUP`` from the panel and group files.
* Mappings from ``PartRelatedCodeMapping.csv``: LOINC parts to SNOMED CT,
  RxNorm, ChEBI and other systems, with LOINC's own equivalence
  (``equivalent`` / ``narrower`` / ``wider`` / ``relatedto``).
"""

from collections.abc import Iterator

from clinical_graph.model import Concept, Mapping, Relation
from clinical_graph.vocabularies.base import VocabularyReader


class LoincReader(VocabularyReader):
    """Reader for the LOINC release."""

    source_key = "loinc"

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield LOINC terms and parts."""
        raise NotImplementedError

    def iter_relations(self) -> Iterator[Relation]:
        """Yield term-part links, the component hierarchy and replacements."""
        raise NotImplementedError

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield LOINC part -> external code mappings."""
        raise NotImplementedError
