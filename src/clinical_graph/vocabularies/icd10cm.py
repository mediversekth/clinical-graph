"""ICD-10-CM and ICD-10-PCS, CMS release.

Planned content:

* Concepts: ICD-10-CM chapters, blocks and codes from ``icd10cm_tabular_<year>.xml``
  (codes with their published dot, e.g. ``E11.9``), titles from
  ``icd10cm_order_<year>.txt`` (header rows have ``billable=0``); ICD-10-PCS codes
  and table headers from ``icd10pcs_order_<year>.txt`` (``Vocabulary.ICD10PCS``).
* Relations: ``ISA`` child -> parent along chapter / block / code; the tabular
  notes as ``EXCLUDES1``, ``EXCLUDES2``, ``CODEFIRST``, ``CODEALSO``,
  ``USEADDITIONAL`` where the note names a resolvable code.
* Mappings: none in the CMS release. SNOMED CT -> ICD-10-CM comes from NLM's map
  (see docs/sources.md, "Not yet included").
"""

from collections.abc import Iterator

from clinical_graph.model import Concept, Mapping, Relation
from clinical_graph.vocabularies.base import VocabularyReader


class Icd10CmReader(VocabularyReader):
    """Reader for the CMS ICD-10-CM / ICD-10-PCS files."""

    source_key = "icd10cm"

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield ICD-10-CM and ICD-10-PCS concepts."""
        raise NotImplementedError

    def iter_relations(self) -> Iterator[Relation]:
        """Yield the hierarchy and tabular-note edges."""
        raise NotImplementedError

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: the CMS release contains no cross-vocabulary maps."""
        yield from ()
