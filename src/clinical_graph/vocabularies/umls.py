"""UMLS Metathesaurus (NLM): links between vocabularies through shared CUIs.

UMLS groups the codes of its source vocabularies into concepts (CUIs): codes in
one CUI mean the same thing. This reader turns every pair of codes of two loaded
vocabularies that share a CUI into a ``MAPS_TO`` edge, to fill the gaps the
official maps leave (WHO ICD-10 <-> ICD-10-CM, SNOMED CT <-> ICD-10-PCS, LOINC
<-> ICD-10-CM, ICD-9-CM <-> WHO ICD-10, ...).

* Concepts, relations: none; UMLS adds no nodes.
* Mappings: from ``MRCONSO.RRF``, the current atoms (``SUPPRESS=N``) of
  ICD9CM (codes and headers, ``PT`` / ``HT``), SNOMEDCT_US, LNC, RXNORM, ATC,
  ICD10CM, ICD10PCS, ICD10 (WHO), ICF and ICF-CY (both ``Vocabulary.ICF``). For
  each CUI, every pair of codes of two different vocabularies, ``equivalent``, keyed by
  the CUI. Each pair points one way, from the vocabulary earlier in
  :data:`ORDER` (ICD-9-CM, LOINC, RxNorm, SNOMED CT, ATC, ICD-10-CM, ICD-10-PCS,
  ICD-10, ICF),
  following the official maps' directions. UMLS-made codes (LOINC ``MTHU...``)
  and the ICD-10-PCS axis codes (4-6 characters) are left out.

The reader is ``supplementary``: ``bind`` resolves both codes against the
graphs (UMLS has its own source versions), accepts no broader-code fallback, and
writes only pairs that no other map links yet.
"""

from collections.abc import Iterator
from itertools import combinations, groupby, product
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

CONSO = "META/MRCONSO.RRF"

UMLS_PROVENANCE = "UMLS Metathesaurus (shared CUI)"

SOURCES = {
    "ICD9CM": Vocabulary.ICD9CM,  # first: its edges point to the successors
    "LNC": Vocabulary.LOINC,
    "RXNORM": Vocabulary.RXNORM,
    "SNOMEDCT_US": Vocabulary.SNOMED,
    "ATC": Vocabulary.ATC,
    "ICD10CM": Vocabulary.ICD10CM,
    "ICD10PCS": Vocabulary.ICD10PCS,
    "ICD10": Vocabulary.ICD10,
    "ICF": Vocabulary.ICF,
    "ICF-CY": Vocabulary.ICF,  # children and youth version, merged into ICF
}
"""UMLS source abbreviation (SAB) -> vocabulary."""

ORDER = list(SOURCES.values())
"""Edges point from the earlier vocabulary to the later one."""

_PCS_TTYS = {"PT", "HT"}  # codes and 3-character tables; not the axis codes (HX)
_ICD9CM_TTYS = {"PT", "HT"}  # codes and headers; not the abbreviations (AB)


def _keep(sab: str, tty: str, code: str) -> bool:
    if sab == "LNC":
        return not code.startswith("MTHU")
    if sab == "ICD10PCS":
        return tty in _PCS_TTYS
    if sab == "ICD9CM":
        return tty in _ICD9CM_TTYS
    return True


class UmlsReader(VocabularyReader):
    """Reader for the UMLS Metathesaurus; yields cross-vocabulary mappings only."""

    source_key: ClassVar[str] = "umls"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = ()
    provenances: ClassVar[tuple[str, ...]] = (UMLS_PROVENANCE,)
    supplementary: ClassVar[bool] = True

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield nothing: UMLS adds no concepts."""
        yield from ()

    def iter_relations(self) -> Iterator[Relation]:
        """Yield nothing: UMLS adds no relations within a vocabulary."""
        yield from ()

    def _atoms(self) -> Iterator[tuple[str, Vocabulary, str]]:
        """(CUI, vocabulary, code) of the kept atoms, in file (CUI) order."""
        with self.path(CONSO).open(encoding="utf-8", newline="") as fh:
            for line in fh:
                f = line.split("|", 17)
                vocabulary = SOURCES.get(f[11])
                if vocabulary is None or f[16] != "N":
                    continue
                if _keep(f[11], f[12], f[13]):
                    yield f[0], vocabulary, f[13]

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield one mapping per pair of codes of two vocabularies in a CUI.

        ``MRCONSO.RRF`` is sorted by CUI, so CUIs are read one at a time.
        """
        rank = {v: i for i, v in enumerate(ORDER)}
        for cui, atoms in groupby(self._atoms(), key=lambda a: a[0]):
            codes: dict[Vocabulary, set[str]] = {}
            for _, vocabulary, code in atoms:
                codes.setdefault(vocabulary, set()).add(code)
            if len(codes) < 2:
                continue
            for a, b in combinations(sorted(codes, key=rank.__getitem__), 2):
                for code_a, code_b in product(sorted(codes[a]), sorted(codes[b])):
                    yield Mapping(
                        concept_id(a, code_a),
                        concept_id(b, code_b),
                        MappingEquivalence.EQUIVALENT,
                        UMLS_PROVENANCE,
                        key=cui,
                        properties={"cui": cui},
                    )
