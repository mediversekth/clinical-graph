"""LOINC release (terms, parts and accessory files).

* Concepts: terms of ``Loinc.csv`` (``kind="term"``, ``2345-7``; with their
  display, short and consumer names and ``RELATEDNAMES2`` as
  ``related_names``), parts of
  ``Part.csv`` (``part``, ``LP14635-4``), LP codes of the component hierarchy that
  are not parts (``hierarchy``), and groups / parent groups (``group``,
  ``parentgroup``, ``LG100-4``). Terms, LP and LG codes never collide.
* Relations:

  - term -> part, one type per axis: ``COMPONENT``, ``PROPERTY``, ``TIME``,
    ``SYSTEM``, ``SCALE``, ``METHOD``, ``CLASS``, ``ANALYTE``, ``ANALYTE_CORE``,
    ``SUPER_SYSTEM``, ``CHALLENGE``, ...; radiology and document ontology axes as
    ``RADIOLOGY`` / ``DOCUMENT`` with the axis in ``axis``. Search keywords and
    broad categories are left out.
  - ``ISA``: child -> parent in ``ComponentHierarchyBySystem`` (terms are leaves)
  - ``REPLACED_BY``: deprecated term -> replacement (``MapTo.csv``)
  - ``IN_GROUP``: term -> group, group -> parent group
  - ``IN_PANEL``: term -> the panel it is a direct member of (``PanelsAndForms``)

* Mappings: the SNOMED CT and RxNorm rows of ``PartRelatedCodeMapping.csv``,
  LOINC part -> SNOMED CT concept (``loinc:LP14635-4`` -> ``snomed:...``) or
  RxNorm concept (``rxnorm:<RXCUI>``, mostly ingredients), with the equivalence
  LOINC publishes (FHIR ConceptMap codes: ``narrower`` = the target is narrower
  than the part). LOINC terms have no map of their own; they reach SNOMED CT and
  RxNorm through their parts. The rows to ChEBI, HGNC, NCBI, RadLex, UNII,
  PubChem and ClinVar are not read: those vocabularies are not loaded.
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

LOINC = "LoincTable/Loinc.csv"
MAP_TO = "LoincTable/MapTo.csv"
PART = "AccessoryFiles/PartFile/Part.csv"
PART_LINKS = (
    "AccessoryFiles/PartFile/LoincPartLink_Primary.csv",
    "AccessoryFiles/PartFile/LoincPartLink_Supplementary.csv",
)
HIERARCHY = "AccessoryFiles/ComponentHierarchyBySystem/ComponentHierarchyBySystem.csv"
GROUP = "AccessoryFiles/GroupFile/Group.csv"
GROUP_TERMS = "AccessoryFiles/GroupFile/GroupLoincTerms.csv"
PARENT_GROUP = "AccessoryFiles/GroupFile/ParentGroup.csv"
PANELS = "AccessoryFiles/PanelsAndForms/PanelsAndForms.csv"
CONSUMER_NAME = "AccessoryFiles/ConsumerName/ConsumerName.csv"
PART_MAP = "AccessoryFiles/PartFile/PartRelatedCodeMapping.csv"

SNOMED_SYSTEM = "http://snomed.info/sct"
SNOMED_MAP_PROVENANCE = "LOINC part map to SNOMED CT (PartRelatedCodeMapping)"
RXNORM_SYSTEM = "http://www.nlm.nih.gov/research/umls/rxnorm"
RXNORM_MAP_PROVENANCE = "LOINC part map to RxNorm (PartRelatedCodeMapping)"
_TARGETS = {
    SNOMED_SYSTEM: (Vocabulary.SNOMED, SNOMED_MAP_PROVENANCE),
    RXNORM_SYSTEM: (Vocabulary.RXNORM, RXNORM_MAP_PROVENANCE),
}
"""``ExtCodeSystem`` -> target vocabulary and provenance, for the systems loaded."""
_CONTENT_ORIGIN = {"LN": "loinc", "Both": "loinc_snomed"}
"""``ContentOrigin``: made by LOINC, or jointly by LOINC and SNOMED International."""

_SKIPPED_LINKS = {("Search", "search"), ("Metadata", "category")}
_AXIS_TYPES = {"TIME_ASPCT": "TIME", "SCALE_TYP": "SCALE", "METHOD_TYP": "METHOD"}


def _lid(code: str) -> str:
    return concept_id(Vocabulary.LOINC, code)


def part_relation(link_property: str) -> tuple[str, str | None]:
    """Relationship type and axis of a term -> part link.

    Args:
        link_property: ``Property`` column, e.g. ``http://loinc.org/property/SYSTEM``.

    Returns:
        ``("SYSTEM", None)``, ``("ANALYTE_CORE", None)``, or for radiology and
        document axes ``("RADIOLOGY", "modality-type")``.
    """
    tail = link_property.rsplit("/", 1)[-1]
    for prefix, rel_type in (("rad-", "RADIOLOGY"), ("document-", "DOCUMENT")):
        if tail.startswith(prefix):
            return rel_type, tail.removeprefix(prefix)
    return _AXIS_TYPES.get(tail, tail.replace("-", "_").upper()), None


def _status(value: str) -> str:
    return value.strip().upper()


class LoincReader(VocabularyReader):
    """Reader for the LOINC release."""

    source_key: ClassVar[str] = "loinc"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.LOINC,)
    provenances: ClassVar[tuple[str, ...]] = (
        SNOMED_MAP_PROVENANCE,
        RXNORM_MAP_PROVENANCE,
    )

    def _consumer_names(self) -> dict[str, str]:
        """LOINC number -> consumer name, from ``ConsumerName.csv`` if present."""
        if not self.has(CONSUMER_NAME):
            return {}
        return {
            row["LoincNumber"]: row["ConsumerName"].strip()
            for row in self.read_csv(CONSUMER_NAME)
            if row["ConsumerName"].strip()
        }

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield LOINC terms, parts, hierarchy nodes and groups."""
        seen: set[str] = set()
        consumer_names = self._consumer_names()
        for row in self.read_csv(LOINC):
            seen.add(row["LOINC_NUM"])
            status = _status(row["STATUS"])
            yield Concept(
                vocabulary=Vocabulary.LOINC,
                code=row["LOINC_NUM"],
                name=row["LONG_COMMON_NAME"] or row["SHORTNAME"],
                kind="term",
                active=status != "DEPRECATED",
                properties={
                    "status": status,
                    "short_name": row["SHORTNAME"] or None,
                    "display_name": row["DisplayName"].strip() or None,
                    # ConsumerName.csv since 2.8x; the Loinc.csv column before
                    "consumer_name": consumer_names.get(row["LOINC_NUM"])
                    or row["CONSUMER_NAME"].strip()
                    or None,
                    "related_names": [
                        n
                        for n in dict.fromkeys(
                            n.strip() for n in row["RELATEDNAMES2"].split(";")
                        )
                        if n
                    ],
                    "class": row["CLASS"] or None,
                    "component": row["COMPONENT"] or None,
                    "property": row["PROPERTY"] or None,
                    "time_aspect": row["TIME_ASPCT"] or None,
                    "system": row["SYSTEM"] or None,
                    "scale": row["SCALE_TYP"] or None,
                    "method": row["METHOD_TYP"] or None,
                    "order_obs": row["ORDER_OBS"] or None,
                },
            )

        for row in self.read_csv(PART):
            seen.add(row["PartNumber"])
            status = _status(row["Status"])
            yield Concept(
                vocabulary=Vocabulary.LOINC,
                code=row["PartNumber"],
                name=row["PartName"],
                kind="part",
                active=status == "ACTIVE",
                properties={
                    "status": status,
                    "part_type": row["PartTypeName"],
                    "display_name": row["PartDisplayName"] or None,
                },
            )

        for row in self.read_csv(HIERARCHY):
            if row["CODE"] not in seen:
                seen.add(row["CODE"])
                yield Concept(
                    vocabulary=Vocabulary.LOINC,
                    code=row["CODE"],
                    name=row["CODE_TEXT"],
                    kind="hierarchy",
                )

        groups = (
            (PARENT_GROUP, "parentgroup", "ParentGroupId", "ParentGroup"),
            (GROUP, "group", "GroupId", "Group"),
        )
        for path, kind, code_col, name_col in groups:
            if not self.has(path):
                continue
            for row in self.read_csv(path):
                status = _status(row["Status"])
                yield Concept(
                    vocabulary=Vocabulary.LOINC,
                    code=row[code_col],
                    name=row[name_col],
                    kind=kind,
                    active=status == "ACTIVE",
                    properties={"status": status},
                )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield term-part links, hierarchy, replacements, groups and panels."""
        yield from self._part_links()

        seen: set[tuple[str, str]] = set()
        for row in self.read_csv(HIERARCHY):
            pair = (row["CODE"], row["IMMEDIATE_PARENT"])
            if all(pair) and pair not in seen:
                seen.add(pair)
                yield Relation(_lid(pair[0]), "ISA", _lid(pair[1]))

        for row in self.read_csv(MAP_TO):
            yield Relation(
                _lid(row["LOINC"]),
                "REPLACED_BY",
                _lid(row["MAP_TO"]),
                properties={"comment": row["COMMENT"] or None},
            )

        if self.has(GROUP_TERMS):
            for row in self.read_csv(GROUP_TERMS):
                yield Relation(
                    _lid(row["LoincNumber"]), "IN_GROUP", _lid(row["GroupId"])
                )
        if self.has(GROUP):
            for row in self.read_csv(GROUP):
                if row["ParentGroupId"]:
                    yield Relation(
                        _lid(row["GroupId"]), "IN_GROUP", _lid(row["ParentGroupId"])
                    )

        if self.has(PANELS):
            yield from self._panel_members()

    def _part_links(self) -> Iterator[Relation]:
        seen: set[tuple[str, str, str, str | None]] = set()
        for path in PART_LINKS:
            for row in self.read_csv(path):
                prop = row["Property"]
                if (row["LinkTypeName"], prop.rsplit("/", 1)[-1]) in _SKIPPED_LINKS:
                    continue
                rel_type, axis = part_relation(prop)
                edge = (row["LoincNumber"], row["PartNumber"], rel_type, axis)
                if edge in seen:
                    continue
                seen.add(edge)
                yield Relation(
                    _lid(edge[0]),
                    rel_type,
                    _lid(edge[1]),
                    key={"axis": axis} if axis else {},
                )

    def _panel_members(self) -> Iterator[Relation]:
        """Each row's ``ParentId`` is the row ``ID`` of its direct parent panel."""
        rows = list(self.read_csv(PANELS))
        row_loinc = {r["ID"]: r["Loinc"] for r in rows}
        best: dict[tuple[str, str], int | None] = {}
        for r in rows:
            panel = row_loinc.get(r["ParentId"], "")
            if r["ID"] == r["ParentId"] or not panel or panel == r["Loinc"]:
                continue
            seq = int(r["SEQUENCE"]) if r["SEQUENCE"].isdigit() else None
            pair = (r["Loinc"], panel)
            current = best.get(pair)
            if pair not in best or (
                seq is not None and (current is None or seq < current)
            ):
                best[pair] = seq
        for (member, panel), seq in best.items():
            yield Relation(
                _lid(member), "IN_PANEL", _lid(panel), properties={"sequence": seq}
            )

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield the LOINC part -> SNOMED CT and -> RxNorm concept mappings.

        At most one row per part and target, so no key is needed; a part can map
        to several targets.
        """
        for row in self.read_csv(PART_MAP):
            target = row["ExtCodeId"].strip()
            system = _TARGETS.get(row["ExtCodeSystem"])
            if system is None or not target:
                continue
            vocabulary, provenance = system
            origin = row["ContentOrigin"].strip()
            yield Mapping(
                source=_lid(row["PartNumber"]),
                target=concept_id(vocabulary, target),
                equivalence=MappingEquivalence(row["Equivalence"].strip()),
                provenance=provenance,
                properties={
                    "part_type": row["PartTypeName"] or None,
                    "content_origin": _CONTENT_ORIGIN.get(origin, origin or None),
                    "target_version": row["ExtCodeSystemVersion"] or None,
                },
            )
