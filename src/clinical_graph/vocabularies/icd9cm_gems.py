"""CMS General Equivalence Mappings (GEMs) between ICD-9-CM and ICD-10-CM/PCS.

CMS published the GEMs for the ICD-10 transition until FY2018, the last edition.
Four maps, each its own ``provenance``:

* diagnoses, forward (``2018_I9gem.txt``): ``icd9cm`` -> ``icd10cm``
* diagnoses, backward (``2018_I10gem.txt``): ``icd10cm`` -> ``icd9cm``
* procedures, forward (``gem_i9pcs.txt``): ``icd9cm`` -> ``icd10pcs``
* procedures, backward (``gem_pcsi9.txt``): ``icd10pcs`` -> ``icd9cm``

* Concepts, relations: none; this source only links the vocabulary graphs.
* Mappings: one per row with a target (rows flagged *no map*, or whose
  target is a placeholder such as ``NoI9``, are left out).
  Codes are published without dots and dotted here (``25001`` -> ``250.01``,
  procedures ``4581`` -> ``45.81``; ``E119`` -> ``E11.9``). The five flags are
  kept: ``approximate``, ``combination`` (the source needs several targets
  together), ``scenario`` and ``choice_list`` (one target of each choice list
  of a scenario). A row that is neither approximate nor a combination is
  ``equivalent``, the others ``unspecified``. Combination rows are keyed by
  ``<scenario>.<choice list>``. The 2018 ICD-10 codes are resolved against the
  current release by ``bind`` (retired codes fall back to their parent); a
  backward row whose ICD-10 source code is retired is skipped.
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
from clinical_graph.vocabularies.icd9cm import dotted
from clinical_graph.vocabularies.icd10cm import display_code

DX_FORWARD = "diagnosis_gems_{v}/{v}_I9gem.txt"
DX_BACKWARD = "diagnosis_gems_{v}/{v}_I10gem.txt"
PCS_FORWARD = "pcs_gems_{v}/gem_i9pcs.txt"
PCS_BACKWARD = "pcs_gems_{v}/gem_pcsi9.txt"

DX_FORWARD_PROVENANCE = "CMS GEM ICD-9-CM -> ICD-10-CM (2018)"
DX_BACKWARD_PROVENANCE = "CMS GEM ICD-10-CM -> ICD-9-CM (2018)"
PCS_FORWARD_PROVENANCE = "CMS GEM ICD-9-CM -> ICD-10-PCS (2018)"
PCS_BACKWARD_PROVENANCE = "CMS GEM ICD-10-PCS -> ICD-9-CM (2018)"


def _icd9(code: str, *, procedure: bool) -> str:
    return concept_id(Vocabulary.ICD9CM, dotted(code, procedure=procedure))


def _icd10(code: str, *, procedure: bool) -> str:
    if procedure:
        return concept_id(Vocabulary.ICD10PCS, code)
    return concept_id(Vocabulary.ICD10CM, display_code(code, Vocabulary.ICD10CM))


class Icd9CmGemsReader(VocabularyReader):
    """Reader for the CMS 2018 GEMs; yields mappings only."""

    source_key: ClassVar[str] = "icd9cm_gems"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = ()
    provenances: ClassVar[tuple[str, ...]] = (
        DX_FORWARD_PROVENANCE,
        DX_BACKWARD_PROVENANCE,
        PCS_FORWARD_PROVENANCE,
        PCS_BACKWARD_PROVENANCE,
    )

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield nothing: the GEMs add no concepts."""
        yield from ()

    def iter_relations(self) -> Iterator[Relation]:
        """Yield nothing: the GEMs add no relations within a vocabulary."""
        yield from ()

    def _rows(self, manifest_path: str) -> Iterator[tuple[str, str, str]]:
        """(source, target, flags) of each line; the file is whitespace-separated."""
        with self.path(manifest_path).open(encoding="ascii") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 3:
                    yield parts[0], parts[1], parts[2]

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the rows of the four GEMs that have a target."""
        for path, provenance, forward, procedure in (
            (DX_FORWARD, DX_FORWARD_PROVENANCE, True, False),
            (DX_BACKWARD, DX_BACKWARD_PROVENANCE, False, False),
            (PCS_FORWARD, PCS_FORWARD_PROVENANCE, True, True),
            (PCS_BACKWARD, PCS_BACKWARD_PROVENANCE, False, True),
        ):
            for source, target, flags in self._rows(path):
                approximate, no_map, combination, scenario, choice = flags
                # 31 backward rows have the NoI9 placeholder without the flag
                if no_map == "1" or target.startswith("No"):
                    continue
                if forward:
                    source_id = _icd9(source, procedure=procedure)
                    target_id = _icd10(target, procedure=procedure)
                else:
                    source_id = _icd10(source, procedure=procedure)
                    target_id = _icd9(target, procedure=procedure)
                is_combination = combination == "1"
                exact = approximate == "0" and not is_combination
                yield Mapping(
                    source=source_id,
                    target=target_id,
                    equivalence=MappingEquivalence.EQUIVALENT
                    if exact
                    else MappingEquivalence.UNSPECIFIED,
                    provenance=provenance,
                    key=f"{scenario}.{choice}" if is_combination else None,
                    properties={
                        "approximate": approximate == "1",
                        "combination": is_combination,
                        "scenario": int(scenario) if is_combination else None,
                        "choice_list": int(choice) if is_combination else None,
                    },
                )
