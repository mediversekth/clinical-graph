"""Readers that turn one source release into graph records.

Each module reads exactly one source from ``sources.toml`` and yields
:class:`~clinical_graph.model.Concept`, :class:`~clinical_graph.model.Relation` and
:class:`~clinical_graph.model.Mapping` records. Readers know nothing about the graph
backend; building and exporting the graph is a separate step.
"""

from clinical_graph.vocabularies.base import VocabularyReader
from clinical_graph.vocabularies.icd10cm import Icd10CmReader
from clinical_graph.vocabularies.loinc import LoincReader
from clinical_graph.vocabularies.snomed import SnomedReader

__all__ = [
    "READERS",
    "Icd10CmReader",
    "LoincReader",
    "SnomedReader",
    "VocabularyReader",
]

READERS: dict[str, type[VocabularyReader]] = {
    "snomed": SnomedReader,
    "loinc": LoincReader,
    "icd10cm": Icd10CmReader,
}
"""Reader class per ``sources.toml`` key."""
