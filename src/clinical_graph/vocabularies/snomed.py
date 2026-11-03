"""SNOMED CT International Edition, RF2, with its history.

The Snapshot gives every component ever published in its latest state, inactive
ones included; the optional Full files add when each concept and relationship was
first active. Nothing is filtered on ``active``: it is a property instead, so
codes and hierarchies of older records (EHRs, annotations) stay in the graph.

* Concepts: every concept of ``sct2_Concept`` (``active``, ``first_active``,
  ``inactivation_reason``). The name is the US-English preferred term (language
  refset 900000000000509007); the FSN, semantic tag, the other US-acceptable
  synonyms and the retired terms (``inactive_terms``) are kept alongside.
* Relations: every *inferred* relationship of ``sct2_Relationship``, active or
  not, plus the retired *additional* ones (old ``PART_OF``) - ``ISA`` (116680003)
  and one type per attribute, named after the attribute's FSN (``FINDING_SITE``,
  ``HAS_ACTIVE_INGREDIENT``). The relationship id is the edge's identity, since a
  retired and a current edge can join the same concepts in the same role group.
  And every row of ``der2_cRefset_Association`` between two concepts
  (``REPLACED_BY``, ``SAME_AS``, ``POSSIBLY_EQUIVALENT_TO``,
  ``ANATOMY_STRUCTURE_AND_PART``, ...), keyed by the refset member id.
* Mappings: every row of ``der2_iisssccRefset_ExtendedMap`` refset 447562003,
  the map to **WHO ICD-10** (not ICD-10-CM), active and inactive, keyed by the
  refset member id. A concept can have several rows: one per map group (each
  group is one target code; dagger/asterisk pairs use two) and, within a group,
  alternatives in ``map_priority`` order chosen by ``map_rule`` (``TRUE``, or a
  condition on sex or age). Rows without a target (the concept cannot be
  classified) are skipped. ICD-O-3 (``der2_sRefset_SimpleMap``) is not read yet.
"""

import re
from collections import defaultdict
from collections.abc import Iterator
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

# RF2 file name templates: ``{e}`` is the edition (``INT``; an extension's
# namespace, ``LO1010000``), ``{v}`` the release version.
CONCEPT = "Snapshot/Terminology/sct2_Concept_Snapshot_{e}_{v}.txt"
DESCRIPTION = "Snapshot/Terminology/sct2_Description_Snapshot-en_{e}_{v}.txt"
TEXT_DEFINITION = "Snapshot/Terminology/sct2_TextDefinition_Snapshot-en_{e}_{v}.txt"
LANGUAGE = "Snapshot/Refset/Language/der2_cRefset_LanguageSnapshot-en_{e}_{v}.txt"
RELATIONSHIP = "Snapshot/Terminology/sct2_Relationship_Snapshot_{e}_{v}.txt"
ASSOCIATION = "Snapshot/Refset/Content/der2_cRefset_AssociationSnapshot_{e}_{v}.txt"
ATTRIBUTE_VALUE = (
    "Snapshot/Refset/Content/der2_cRefset_AttributeValueSnapshot_{e}_{v}.txt"
)
CONCEPT_FULL = "Full/Terminology/sct2_Concept_Full_{e}_{v}.txt"
RELATIONSHIP_FULL = "Full/Terminology/sct2_Relationship_Full_{e}_{v}.txt"
ASSOCIATION_FULL = "Full/Refset/Content/der2_cRefset_AssociationFull_{e}_{v}.txt"
EXTENDED_MAP = "Snapshot/Refset/Map/der2_iisssccRefset_ExtendedMapSnapshot_{e}_{v}.txt"
EXTENDED_MAP_FULL = "Full/Refset/Map/der2_iisssccRefset_ExtendedMapFull_{e}_{v}.txt"

FSN = "900000000000003001"
SYNONYM = "900000000000013009"
US_ENGLISH = "900000000000509007"
PREFERRED = "900000000000548007"
ISA = "116680003"
INFERRED = "900000000000011006"
ADDITIONAL = "900000000000227009"
CHARACTERISTIC = {INFERRED: "inferred", ADDITIONAL: "additional"}
CONCEPT_INACTIVATION = "900000000000489007"
ICD10_MAP = "447562003"
ICD10_MAP_PROVENANCE = "SNOMED CT International map to ICD-10 (refset 447562003)"
DEFINED = "900000000000073002"

_SEMANTIC_TAG = re.compile(r"\s*\(([^()]+)\)$")
_NOT_NAME = re.compile(r"[^A-Za-z0-9]+")
_REFSET_SUFFIX = re.compile(r"\s+(?:concept\s+)?association reference set$", re.I)


def is_concept_id(sctid: str) -> bool:
    """Whether an SCTID identifies a concept (partition digit ``0``)."""
    return len(sctid) > 2 and sctid[-2] == "0"


def relation_type(name: str) -> str:
    """UPPER_SNAKE_CASE relationship type from a SNOMED CT name.

    ``"Procedure site - Indirect"`` -> ``"PROCEDURE_SITE_INDIRECT"``.
    """
    return _NOT_NAME.sub("_", name).strip("_").upper()


def split_fsn(fsn: str) -> tuple[str, str | None]:
    """Split an FSN into its term and semantic tag.

    ``"Diabetes mellitus (disorder)"`` -> ``("Diabetes mellitus", "disorder")``.
    """
    match = _SEMANTIC_TAG.search(fsn)
    if not match:
        return fsn, None
    return fsn[: match.start()], match.group(1)


def _sid(code: str) -> str:
    return concept_id(Vocabulary.SNOMED, code)


class _Terms:
    """US-English terms per concept."""

    def __init__(self) -> None:
        self.fsn: dict[str, str] = {}
        self.preferred: dict[str, str] = {}
        self.synonyms: defaultdict[str, list[str]] = defaultdict(list)
        self.inactive: defaultdict[str, list[str]] = defaultdict(list)
        """Retired FSNs and synonyms, any language refset."""


class SnomedReader(VocabularyReader):
    """Reader for the SNOMED CT RF2 Snapshot."""

    source_key: ClassVar[str] = "snomed"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.SNOMED,)
    provenances: ClassVar[tuple[str, ...]] = (ICD10_MAP_PROVENANCE,)
    edition: ClassVar[str] = "INT"
    """The edition part of the RF2 file names (``{e}`` in the templates)."""

    def _rf2(self, template: str) -> str:
        """Manifest path of an RF2 file of this edition (``{v}`` left to ``path``)."""
        return template.replace("{e}", self.edition)

    @cached_property
    def _terms(self) -> _Terms:
        preferred: set[str] = set()
        acceptable: set[str] = set()
        for row in self.read_tsv(self._rf2(LANGUAGE)):
            if row["active"] == "1" and row["refsetId"] == US_ENGLISH:
                target = (
                    preferred if row["acceptabilityId"] == PREFERRED else acceptable
                )
                target.add(row["referencedComponentId"])

        terms = _Terms()
        for row in self.read_tsv(self._rf2(DESCRIPTION)):
            did, cid, term = row["id"], row["conceptId"], row["term"]
            if row["active"] != "1":
                terms.inactive[cid].append(term)
                continue
            if row["typeId"] == FSN:
                if did in preferred or cid not in terms.fsn:
                    terms.fsn[cid] = term
            elif did in preferred:
                terms.preferred[cid] = term
            elif did in acceptable:
                terms.synonyms[cid].append(term)
        return terms

    def _definitions(self) -> dict[str, str]:
        if not self.has(self._rf2(TEXT_DEFINITION)):
            return {}
        return {
            row["conceptId"]: row["term"]
            for row in self.read_tsv(self._rf2(TEXT_DEFINITION))
            if row["active"] == "1"
        }

    def _inactivation_reasons(self) -> dict[str, str]:
        """Concept id -> why it was inactivated (``Duplicate component``, ...)."""
        if not self.has(self._rf2(ATTRIBUTE_VALUE)):
            return {}
        return {
            row["referencedComponentId"]: self._name(row["valueId"])
            for row in self.read_tsv(self._rf2(ATTRIBUTE_VALUE))
            if row["active"] == "1" and row["refsetId"] == CONCEPT_INACTIVATION
        }

    def _first_active(self, full_path: str) -> dict[str, str]:
        """Component id -> earliest effective time at which it was active.

        Read from a Full file; empty when the Full release is not on disk.
        """
        full_path = self._rf2(full_path)
        if not self.has(full_path):
            return {}
        first: dict[str, str] = {}
        for row in self.read_tsv(full_path):
            if row["active"] == "1":
                cid, time = row["id"], row["effectiveTime"]
                if cid not in first or time < first[cid]:
                    first[cid] = time
        return first

    def _name(self, sctid: str) -> str:
        """The FSN without semantic tag, falling back to the id."""
        return split_fsn(self._terms.fsn.get(sctid, sctid))[0]

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield every SNOMED CT concept, active and inactive."""
        terms = self._terms
        definitions = self._definitions()
        reasons = self._inactivation_reasons()
        first_active = self._first_active(CONCEPT_FULL)
        for row in self.read_tsv(self._rf2(CONCEPT)):
            cid = row["id"]
            active = row["active"] == "1"
            fsn = terms.fsn.get(cid)
            term, tag = split_fsn(fsn) if fsn else (cid, None)
            name = terms.preferred.get(cid, term)
            synonyms = sorted(set(terms.synonyms.get(cid, ())))
            current = {name, fsn, *synonyms}
            inactive_terms = sorted(set(terms.inactive.get(cid, ())) - current)
            yield Concept(
                vocabulary=Vocabulary.SNOMED,
                code=cid,
                name=name,
                active=active,
                synonyms=tuple(synonyms),
                properties={
                    "fsn": fsn,
                    "semantic_tag": tag,
                    "definition_status": (
                        "defined"
                        if row["definitionStatusId"] == DEFINED
                        else "primitive"
                    ),
                    "definition": definitions.get(cid),
                    "module_id": row["moduleId"],
                    # None removes it: the node belongs to the International Edition
                    "extension": self.extension,
                    "effective_time": row["effectiveTime"],
                    "first_active": first_active.get(cid),
                    "inactivation_reason": None if active else reasons.get(cid),
                    "inactive_terms": inactive_terms,
                },
            )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield inferred relationships and associations, active and inactive.

        ``active`` is ``False`` on retired edges; ``effective_time`` is when the
        edge last changed (for a retired edge, when it was retired).
        """
        types: dict[str, str] = {ISA: "ISA"}
        first_active = self._first_active(RELATIONSHIP_FULL)
        for row in self.read_tsv(self._rf2(RELATIONSHIP)):
            characteristic = CHARACTERISTIC.get(row["characteristicTypeId"])
            if characteristic is None:
                continue
            rid, type_id = row["id"], row["typeId"]
            if type_id not in types:
                types[type_id] = relation_type(self._name(type_id))
            yield Relation(
                source=_sid(row["sourceId"]),
                type=types[type_id],
                target=_sid(row["destinationId"]),
                key={"id": rid},
                properties={
                    "active": row["active"] == "1",
                    "effective_time": row["effectiveTime"],
                    "first_active": first_active.get(rid),
                    "group": int(row["relationshipGroup"]),
                    "type_id": type_id,
                    "characteristic": characteristic,
                },
            )

        refsets: dict[str, str] = {}
        first_active = self._first_active(ASSOCIATION_FULL)
        for row in self.read_tsv(self._rf2(ASSOCIATION)):
            source, target = row["referencedComponentId"], row["targetComponentId"]
            if not (is_concept_id(source) and is_concept_id(target)):
                continue
            refset = row["refsetId"]
            if refset not in refsets:
                refsets[refset] = relation_type(
                    _REFSET_SUFFIX.sub("", self._name(refset))
                )
            yield Relation(
                source=_sid(source),
                type=refsets[refset],
                target=_sid(target),
                key={"id": row["id"]},
                properties={
                    "active": row["active"] == "1",
                    "effective_time": row["effectiveTime"],
                    "first_active": first_active.get(row["id"]),
                    "refset_id": refset,
                },
            )

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the SNOMED CT -> WHO ICD-10 map rows, active and inactive.

        The target id holds the code as published; the binding step resolves it
        against the ICD-10 graph (see ``Icd10Reader.match``).
        """
        first_active = self._first_active(EXTENDED_MAP_FULL)
        names: dict[str, str] = {}

        def name(sctid: str) -> str:
            if sctid not in names:
                names[sctid] = self._name(sctid)
            return names[sctid]

        for row in self.read_tsv(self._rf2(EXTENDED_MAP)):
            target = row["mapTarget"].strip()
            if row["refsetId"] != ICD10_MAP or not target:
                continue
            yield Mapping(
                source=_sid(row["referencedComponentId"]),
                target=concept_id(Vocabulary.ICD10, target),
                equivalence=MappingEquivalence.UNSPECIFIED,
                provenance=ICD10_MAP_PROVENANCE,
                key=row["id"],
                properties={
                    "active": row["active"] == "1",
                    "effective_time": row["effectiveTime"],
                    "first_active": first_active.get(row["id"]),
                    "refset_id": row["refsetId"],
                    "map_group": int(row["mapGroup"]),
                    "map_priority": int(row["mapPriority"]),
                    "map_rule": row["mapRule"] or None,
                    "map_advice": row["mapAdvice"] or None,
                    "map_category": name(row["mapCategoryId"]),
                    "correlation": name(row["correlationId"]),
                },
            )
