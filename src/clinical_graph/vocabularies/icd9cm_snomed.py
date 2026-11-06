"""NLM ICD-9-CM to SNOMED CT maps (diagnoses and procedures).

NLM maps the ICD-9-CM codes that cover most US use to the SNOMED CT US Edition
(December releases, on the September US Edition). Two files per volume: codes
mapped to one SNOMED CT concept (``1TO1``, ``1T1``) and codes needing several
(``1TOM``, ``1TM``, each target narrower than the code). The graph keeps the
International Edition, so US-only targets match no node and ``bind`` skips them.

* Concepts, relations: none; this source only links ICD-9-CM to SNOMED CT.
* Mappings: ``icd9cm:<code>`` -> ``snomed:<id>`` for every row with a target;
  ``equivalent`` from the one-to-one files, ``narrower`` from the one-to-many
  files (keyed ``1to1`` / ``1tom``). Kept: ``one_to_one``, ``is_current_icd``,
  NLM's usage statistics (``ip_usage``, ``op_usage``: share of inpatient /
  outpatient use, percent) and, for diagnoses, ``is_nec`` and ``in_core``
  (target in the CORE problem list subset).
"""

import csv
from collections.abc import Iterator
from typing import ClassVar

from clinical_graph.model import (
    Concept,
    Mapping,
    MappingEquivalence,
    PropertyValue,
    Relation,
    Vocabulary,
    concept_id,
)
from clinical_graph.vocabularies.base import VocabularyReader

DX_1TO1 = "ICD9CM_SNOMED_MAP_diagnosis_{v}/ICD9CM_SNOMED_MAP_1TO1_{v}.txt"
DX_1TOM = "ICD9CM_SNOMED_MAP_diagnosis_{v}/ICD9CM_SNOMED_MAP_1TOM_{v}.txt"
SG_1TO1 = "ICD9CMV3_SNOMED_MAP_Procedure_{v}/ICD9CMV3_SNOMED_MAP_1T1_{v}.txt"
SG_1TOM = "ICD9CMV3_SNOMED_MAP_Procedure_{v}/ICD9CMV3_SNOMED_MAP_1TM_{v}.txt"

ICD9CM_SNOMED_PROVENANCE = "NLM ICD-9-CM to SNOMED CT map"


def _value(row: dict[str, str], column: str) -> str | None:
    value = (row.get(column) or "").strip()
    return None if value in {"", "NULL"} else value


def _number(row: dict[str, str], column: str) -> float | None:
    value = _value(row, column)
    return float(value) if value is not None else None


def _flag(row: dict[str, str], column: str) -> bool | None:
    value = _value(row, column)
    return value == "1" if value is not None else None


class Icd9CmSnomedMapReader(VocabularyReader):
    """Reader for the NLM ICD-9-CM -> SNOMED CT maps; yields mappings only."""

    source_key: ClassVar[str] = "icd9cm_snomed"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = ()
    provenances: ClassVar[tuple[str, ...]] = (ICD9CM_SNOMED_PROVENANCE,)

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield nothing: the maps add no concepts."""
        yield from ()

    def iter_relations(self) -> Iterator[Relation]:
        """Yield nothing: the maps add no relations within a vocabulary."""
        yield from ()

    def _read(self, manifest_path: str) -> Iterator[dict[str, str]]:
        """Rows of a map file: tab-separated, UTF-8 with BOM, ``NULL`` for empty."""
        with self.path(manifest_path).open(encoding="utf-8-sig", newline="") as fh:
            yield from csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the rows of the four map files that have a SNOMED CT target."""
        for path, one_to_one in (
            (DX_1TO1, True),
            (DX_1TOM, False),
            (SG_1TO1, True),
            (SG_1TOM, False),
        ):
            for row in self._read(path):
                code, target = _value(row, "ICD_CODE"), _value(row, "SNOMED_CID")
                if code is None or target is None:
                    continue
                properties: dict[str, PropertyValue] = {
                    "one_to_one": one_to_one,
                    "is_current_icd": _flag(row, "IS_CURRENT_ICD"),
                    "ip_usage": _number(row, "IP_USAGE"),
                    "op_usage": _number(row, "OP_USAGE"),
                    "is_nec": _flag(row, "IS_NEC"),
                    "in_core": _flag(row, "IN_CORE"),
                }
                yield Mapping(
                    source=concept_id(Vocabulary.ICD9CM, code),
                    target=concept_id(Vocabulary.SNOMED, target),
                    equivalence=MappingEquivalence.EQUIVALENT
                    if one_to_one
                    else MappingEquivalence.NARROWER,
                    provenance=ICD9CM_SNOMED_PROVENANCE,
                    key="1to1" if one_to_one else "1tom",
                    properties={k: v for k, v in properties.items() if v is not None},
                )
