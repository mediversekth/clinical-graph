"""Readers that turn one source release into graph records.

Each module reads exactly one source from ``sources.toml`` and yields
:class:`~clinical_graph.model.Concept`, :class:`~clinical_graph.model.Relation` and
:class:`~clinical_graph.model.Mapping` records. Readers know nothing about the graph
backend; building and exporting the graph is a separate step.
"""

from clinical_graph.vocabularies.base import VocabularyReader
from clinical_graph.vocabularies.icd10 import Icd10Reader
from clinical_graph.vocabularies.icd10cm import Icd10CmReader
from clinical_graph.vocabularies.loinc import LoincReader
from clinical_graph.vocabularies.loinc_extension import LoincExtensionReader
from clinical_graph.vocabularies.rxnorm import RxNormReader
from clinical_graph.vocabularies.snomed import SnomedReader
from clinical_graph.vocabularies.snomed_icd10cm import SnomedIcd10CmMapReader

__all__ = [
    "READERS",
    "Icd10Reader",
    "Icd10CmReader",
    "LoincExtensionReader",
    "LoincReader",
    "RxNormReader",
    "SnomedIcd10CmMapReader",
    "SnomedReader",
    "VocabularyReader",
]

READERS: dict[str, type[VocabularyReader]] = {
    "snomed": SnomedReader,
    "loinc_extension": LoincExtensionReader,
    "loinc": LoincReader,
    "icd10cm": Icd10CmReader,
    "icd10": Icd10Reader,
    "rxnorm": RxNormReader,
    "snomed_icd10cm": SnomedIcd10CmMapReader,
}
"""Reader class per ``sources.toml`` key. Readers without ``vocabularies`` (maps
between vocabularies, such as ``snomed_icd10cm``) only matter to ``bind``."""
