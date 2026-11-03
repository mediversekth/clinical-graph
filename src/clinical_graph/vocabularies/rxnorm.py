"""RxNorm full monthly release (NLM), with the ATC classification it carries.

RRF files: pipe-delimited, no quoting, one trailing ``|``. Only the RxNorm
concepts (``SAB=RXNORM``) and the ATC atoms (``SAB=ATC``) become nodes; the other
sources of the release (SNOMED CT US, DrugBank, Multum, ...) only provide
bindings or are not read.

* Concepts:

  - RxNorm (``Vocabulary.RXNORM``): every RXCUI with an RxNorm atom, current and
    obsolete (``active: false``, kept like SNOMED CT's history). One term type
    (``tty``) each: ingredient ``IN``, precise ingredient ``PIN``, multiple
    ingredients ``MIN``, clinical drug ``SCD`` and its component / form / dose form
    group (``SCDC``, ``SCDF``, ``SCDG``, ...), the branded counterparts (``BN``,
    ``SBD``, ``SBDC``, ...), packs (``GPCK``, ``BPCK``) and dose forms (``DF``,
    ``DFG``). The name is that atom's string; current NDCs (``ndc``, 11 digits)
    and strengths come from ``RXNSAT``.
  - ATC (``Vocabulary.ATC``): the WHO ATC codes in the release, all five levels,
    from the anatomical main group (``A``) to the chemical substance
    (``A10BA02``).

* Relations:

  - RxNorm: the concept-level relationships of ``RXNREL`` (``SAB=RXNORM``), one
    direction of each inverse pair, named after its RELA (``ISA``,
    ``HAS_INGREDIENT``, ``TRADENAME_OF``, ``CONSISTS_OF``, ``HAS_DOSE_FORM``, ...).
    A row reads "RXCUI2 <rela> RXCUI1". ``active`` is whether both ends are
    current; RXNREL itself has no status.
  - ATC: ``ISA`` from each code to the code of the level above (its prefix).

* Mappings:

  - RxNorm concept -> ATC code: the ATC 5th-level atoms on RxNorm concepts
    (mostly ingredients), ``relatedto``: an ATC code is a substance *for a
    therapeutic use*, so an ingredient can have several (mesna: ``R05CB05``,
    ``V03AF01``).
  - RxNorm concept -> SNOMED CT concept: the SNOMED CT US Edition atoms that
    RxNorm puts in an RxNorm concept, ``equivalent``. SNOMED CT concepts that are
    not in the loaded release (US-only drugs) match nothing in ``bind``.

Map targets naming a retired RXCUI resolve through ``RXNCUI`` to the concept it
was merged into (``match: remapped``).
"""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
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

CONSO = "rrf/RXNCONSO.RRF"
REL = "rrf/RXNREL.RRF"
SAT = "rrf/RXNSAT.RRF"
CUI_HISTORY = "rrf/RXNCUI.RRF"

ATC_PROVENANCE = "RxNorm: ATC codes of RxNorm concepts (SAB=ATC)"
SNOMED_PROVENANCE = "RxNorm: SNOMED CT US atoms of RxNorm concepts (SAB=SNOMEDCT_US)"

KINDS = {
    "IN": "ingredient",
    "PIN": "precise_ingredient",
    "MIN": "multiple_ingredients",
    "SCDC": "clinical_drug_component",
    "SCDF": "clinical_drug_form",
    "SCDFP": "clinical_drug_form_precise",
    "SCDG": "clinical_dose_form_group",
    "SCDGP": "clinical_dose_form_group_precise",
    "SCD": "clinical_drug",
    "BN": "brand_name",
    "SBDC": "branded_drug_component",
    "SBDF": "branded_drug_form",
    "SBDFP": "branded_drug_form_precise",
    "SBDG": "branded_dose_form_group",
    "SBD": "branded_drug",
    "BPCK": "branded_pack",
    "GPCK": "generic_pack",
    "DF": "dose_form",
    "DFG": "dose_form_group",
    "ET": "entry_term",
}
"""``kind`` of an RxNorm concept per term type of its main atom."""

SYNONYM_TTYS = {"SY", "TMSY", "PSN"}

RELATIONS = {
    "isa": "ISA",
    "has_ingredient": "HAS_INGREDIENT",
    "has_ingredients": "HAS_INGREDIENTS",
    "has_precise_ingredient": "HAS_PRECISE_INGREDIENT",
    "has_part": "HAS_PART",
    "has_boss": "HAS_BOSS",
    "tradename_of": "TRADENAME_OF",
    "consists_of": "CONSISTS_OF",
    "has_dose_form": "HAS_DOSE_FORM",
    "has_doseformgroup": "HAS_DOSEFORMGROUP",
    "form_of": "FORM_OF",
    "quantified_form_of": "QUANTIFIED_FORM_OF",
    "contains": "CONTAINS",
    "reformulated_to": "REFORMULATED_TO",
}
"""RELA kept (one per inverse pair) -> relationship type. ``has_boss``: the
basis of strength substance of a precise clinical drug form."""

ATC_KINDS = {
    1: "anatomical_group",
    2: "therapeutic_group",
    3: "pharmacological_group",
    4: "chemical_group",
    5: "substance",
}
_ATC_LEVEL = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}  # code length -> level
_ATC_PARENT_LENGTH = {7: 5, 5: 4, 4: 3, 3: 1}

ATTRIBUTES = {
    "RXN_STRENGTH": "strength",
    "RXN_AVAILABLE_STRENGTH": "available_strength",
}
"""Single-valued ``RXNSAT`` attributes copied to properties."""


def _rx(cui: str) -> str:
    return concept_id(Vocabulary.RXNORM, cui)


def _atc(code: str) -> str:
    return concept_id(Vocabulary.ATC, code)


@dataclass
class _RxConcept:
    """The RxNorm atoms of one RXCUI."""

    tty: str = ""
    name: str = ""
    suppress: str = ""
    synonyms: list[tuple[str, bool]] = field(
        default_factory=list[tuple[str, bool]]
    )  # (string, atom is current)
    prescribable_name: str | None = None
    current: bool = False


@dataclass
class _Conso:
    """What ``RXNCONSO`` contributes."""

    rxnorm: dict[str, _RxConcept] = field(default_factory=dict[str, _RxConcept])
    atc_names: dict[str, str] = field(default_factory=dict[str, str])
    atc_synonyms: defaultdict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    atc_of: defaultdict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )  # RXCUI -> ATC 5th-level codes
    snomed_of: defaultdict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )  # RXCUI -> SCTIDs


class RxNormReader(VocabularyReader):
    """Reader for the RxNorm full release: RxNorm and ATC."""

    source_key: ClassVar[str] = "rxnorm"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (
        Vocabulary.RXNORM,
        Vocabulary.ATC,
    )
    provenances: ClassVar[tuple[str, ...]] = (ATC_PROVENANCE, SNOMED_PROVENANCE)

    def _rrf(self, manifest_path: str) -> Iterator[list[str]]:
        """Yield the fields of each line of an RRF file."""
        with self.path(manifest_path).open(encoding="utf-8", newline="") as fh:
            for line in fh:
                yield line.rstrip("\r\n").split("|")

    @cached_property
    def _conso(self) -> _Conso:
        conso = _Conso()
        for f in self._rrf(CONSO):
            cui, sab, tty, code, text, suppress = (
                f[0],
                f[11],
                f[12],
                f[13],
                f[14],
                f[16],
            )
            if sab == "RXNORM":
                c = conso.rxnorm.setdefault(cui, _RxConcept())
                current = suppress == "N"
                c.current |= current
                if tty in KINDS:
                    # the current main atom wins over an obsolete one
                    if not c.tty or (current and c.suppress != "N"):
                        c.tty, c.name, c.suppress = tty, text, suppress
                elif tty in SYNONYM_TTYS:
                    c.synonyms.append((text, current))
                    if tty == "PSN" and current:
                        c.prescribable_name = text
            elif sab == "ATC":
                if tty in ("PT", "IN"):
                    conso.atc_names[code] = text
                else:
                    conso.atc_synonyms[code].add(text)
                if len(code) == 7:
                    conso.atc_of[cui].add(code)
            elif sab == "SNOMEDCT_US" and suppress == "N":
                conso.snomed_of[cui].add(code)
        return conso

    def _attributes(self) -> tuple[dict[str, list[str]], dict[str, dict[str, str]]]:
        """Current NDCs and single-valued attributes per RXCUI, from ``RXNSAT``."""
        ndc: defaultdict[str, set[str]] = defaultdict(set)
        values: defaultdict[str, dict[str, str]] = defaultdict(dict)
        for f in self._rrf(SAT):
            if f[9] != "RXNORM" or f[11] != "N":
                continue
            name, value = f[8], f[10]
            if name == "NDC":
                ndc[f[0]].add(value)
            elif name in ATTRIBUTES:
                values[f[0]][ATTRIBUTES[name]] = value
        return {cui: sorted(codes) for cui, codes in ndc.items()}, values

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield the RxNorm concepts, current and obsolete, and the ATC codes."""
        conso = self._conso
        ndc, values = self._attributes()
        for cui, c in conso.rxnorm.items():
            if not c.tty:  # synonyms only, no main atom
                continue
            # a current concept keeps its current synonyms; an obsolete one all
            synonyms = sorted(
                {s for s, cur in c.synonyms if cur or not c.current} - {c.name}
            )
            yield Concept(
                Vocabulary.RXNORM,
                cui,
                c.name,
                kind=KINDS[c.tty],
                active=c.current,
                synonyms=tuple(synonyms),
                properties={
                    "tty": c.tty,
                    "suppress": None if c.suppress == "N" else c.suppress,
                    "prescribable_name": c.prescribable_name,
                    "ndc": ndc.get(cui),
                    **values.get(cui, {}),
                },
            )
        for code, name in sorted(conso.atc_names.items()):
            level = _ATC_LEVEL.get(len(code))
            if level is None:
                continue
            yield Concept(
                Vocabulary.ATC,
                code,
                name,
                kind=ATC_KINDS[level],
                synonyms=tuple(sorted(conso.atc_synonyms.get(code, set()) - {name})),
                properties={"level": level},
            )

    @cached_property
    def _current(self) -> frozenset[str]:
        """RXCUIs of current RxNorm concepts."""
        return frozenset(
            cui for cui, c in self._conso.rxnorm.items() if c.tty and c.current
        )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield the RxNorm relationships and the ATC hierarchy."""
        current = self._current
        seen: set[tuple[str, str, str]] = set()
        for f in self._rrf(REL):
            if f[10] != "RXNORM" or f[2] != "CUI" or f[6] != "CUI":
                continue
            rel_type = RELATIONS.get(f[7])
            if rel_type is None:
                continue
            source, target = f[4], f[0]
            if (source, rel_type, target) in seen:
                continue
            seen.add((source, rel_type, target))
            yield Relation(
                _rx(source),
                rel_type,
                _rx(target),
                properties={"active": source in current and target in current},
            )
        codes = self._conso.atc_names
        for code in sorted(codes):
            parent_length = _ATC_PARENT_LENGTH.get(len(code))
            if parent_length is not None and code[:parent_length] in codes:
                yield Relation(_atc(code), "ISA", _atc(code[:parent_length]))

    @cached_property
    def _remapped(self) -> dict[str, str]:
        """Retired RXCUI -> the single current RXCUI it went to (``RXNCUI``)."""
        if not self.has(CUI_HISTORY):
            return {}
        targets: defaultdict[str, set[str]] = defaultdict(set)
        for f in self._rrf(CUI_HISTORY):
            old, new = f[0], f[4]
            if new and new != old:
                targets[old].add(new)
        return {old: next(iter(new)) for old, new in targets.items() if len(new) == 1}

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve a map target; a retired RXCUI goes to its successor (``remapped``).

        Returns:
            The concept id and how it matched, or ``None``.
        """
        found = super().match(vocabulary, code)
        if found is not None or vocabulary is not Vocabulary.RXNORM:
            return found
        successor = self._remapped.get(code.strip())
        if successor is not None and _rx(successor) in self.concept_ids:
            return _rx(successor), "remapped"
        return None

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield RxNorm concept -> ATC code and -> SNOMED CT concept."""
        conso = self._conso
        rxnorm = {cui for cui, c in conso.rxnorm.items() if c.tty}
        for cui in sorted(rxnorm & conso.atc_of.keys()):
            for code in sorted(conso.atc_of[cui]):
                yield Mapping(
                    _rx(cui),
                    _atc(code),
                    MappingEquivalence.RELATED,
                    ATC_PROVENANCE,
                )
        for cui in sorted(rxnorm & conso.snomed_of.keys()):
            for sctid in sorted(conso.snomed_of[cui]):
                yield Mapping(
                    _rx(cui),
                    concept_id(Vocabulary.SNOMED, sctid),
                    MappingEquivalence.EQUIVALENT,
                    SNOMED_PROVENANCE,
                )
