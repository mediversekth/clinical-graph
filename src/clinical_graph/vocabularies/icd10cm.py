"""ICD-10-CM and ICD-10-PCS, CMS release.

* Concepts:

  - ICD-10-CM (``Vocabulary.ICD10CM``): chapters (``icd10cm:chapter:4``), blocks
    (tabular ``<section>``, ``icd10cm:block:E08-E13``) and every code of the order
    file, headers and 7-character codes included, with the published dot
    (``icd10cm:E11.9``). Inclusion terms of the tabular become synonyms; the
    entries of the alphabetic index that point to a code, if the index is
    present, its ``index_terms`` (subterms joined to their parents: ``Diabetes,
    diabetic type 2 with ketoacidosis``).
  - ICD-10-PCS (``Vocabulary.ICD10PCS``): tables (first three characters,
    ``icd10pcs:table:001``) and codes.

* Relations:

  - ``ISA``: code -> parent code, block or table; block -> chapter. Codes that
    are not in the tabular nesting (7-character codes) go to the longest prefix
    that is a code.
  - ``EXCLUDES1``, ``EXCLUDES2``, ``CODE_FIRST``, ``CODE_ALSO``,
    ``USE_ADDITIONAL``: the tabular instructional notes, from the chapter, block
    or code the note sits on to each code it references; ``notes`` holds the texts.

* Mappings: none in the CMS release.
"""

import logging
import re
import xml.etree.ElementTree as ET  # nosec B405 - trusted CMS release files
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import ClassVar

from clinical_graph.model import Concept, Mapping, Relation, Vocabulary, concept_id
from clinical_graph.vocabularies.base import VocabularyReader

log = logging.getLogger(__name__)

CM_ORDER = "{v}-code-descriptions-tabular-order/Code Descriptions/icd10cm_order_{v}.txt"
CM_TABULAR = "{v}-code-tables-tabular-index/Table and Index/icd10cm_tabular_{v}.xml"
CM_INDEX = "{v}-code-tables-tabular-index/Table and Index/icd10cm_index_{v}.xml"
PCS_ORDER = "{v}-icd-10-pcs-order-file-long-abbreviated-titles/icd10pcs_order_{v}.txt"

NOTE_TYPES = {
    "excludes1": "EXCLUDES1",
    "excludes2": "EXCLUDES2",
    "codeFirst": "CODE_FIRST",
    "codeAlso": "CODE_ALSO",
    "useAdditionalCode": "USE_ADDITIONAL",
}
_CODE = r"[A-Z]\d[0-9A-Z](?:\.[0-9A-Z]{0,4})?"
# A code reference inside a note's parentheses: E11.9, E08.-, T39.9-, E08-E13
_REF = re.compile(rf"({_CODE})(?:\s*-\s*({_CODE})|\.?-)?")
_PARENS = re.compile(r"\(([^()]*)\)")
_CHAPTER_RANGE = re.compile(r"\(([A-Z][0-9A-Z]{2}-[A-Z][0-9A-Z]{2})\)\s*$")


@dataclass(frozen=True, slots=True)
class OrderRow:
    """One line of a CMS order file."""

    code: str  # without dot, as in the file
    billable: bool
    short_title: str
    long_title: str


def display_code(code: str, vocabulary: Vocabulary) -> str:
    """``"E119"`` -> ``"E11.9"`` for ICD-10-CM; ICD-10-PCS codes have no dot."""
    if vocabulary is Vocabulary.ICD10CM and len(code) > 3:
        return f"{code[:3]}.{code[3:]}"
    return code


def _cm(key: str) -> str:
    return concept_id(Vocabulary.ICD10CM, key)


def _parent(code: str, codes: set[str]) -> str | None:
    """Longest proper prefix of ``code`` that is a code.

    ``S72.001A`` -> ``S72.001``; ``O32.1XX0`` -> ``O32.1``.
    """
    prefix = code[:-1]
    while prefix:
        if prefix in codes:
            return prefix
        prefix = prefix[:-1]
    return None


def _title_text(title: ET.Element | None) -> str:
    """An index title without its ``<nemod>`` (nonessential modifier) parts."""
    if title is None:
        return ""
    parts = [title.text or ""] + [child.tail or "" for child in title]
    return " ".join(" ".join(parts).split())


def _walk_index(
    term: ET.Element, path: tuple[str, ...], terms: defaultdict[str, list[str]]
) -> None:
    """Collect the text of ``term`` and its subterms under the code each gives."""
    path = (*path, _title_text(term.find("title")))
    code = (term.findtext("code") or "").strip()
    if code and "-" not in code:  # a complete code, not E11.- or S72.001-
        terms[code].append(" ".join(p for p in path if p))
    for child in term.findall("term"):
        _walk_index(child, path, terms)


@dataclass
class _Tabular:
    """What the ICD-10-CM tabular XML contributes."""

    chapters: list[tuple[str, str, str]] = field(
        default_factory=list[tuple[str, str, str]]
    )  # (number, range, title)
    blocks: list[tuple[str, str, str]] = field(
        default_factory=list[tuple[str, str, str]]
    )  # (range, chapter number, title)
    inclusion: defaultdict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    isa: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    in_tabular: set[str] = field(default_factory=set[str])
    holders: list[tuple[ET.Element, str]] = field(
        default_factory=list[tuple[ET.Element, str]]
    )


class Icd10CmReader(VocabularyReader):
    """Reader for the CMS ICD-10-CM / ICD-10-PCS files."""

    source_key: ClassVar[str] = "icd10cm"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (
        Vocabulary.ICD10CM,
        Vocabulary.ICD10PCS,
    )

    def _order(self, manifest_path: str) -> Iterator[OrderRow]:
        """Read a CMS order file.

        Fixed width: order number (5), code (7), billable flag (1), short title
        (60), long title.
        """
        with self.path(manifest_path).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield OrderRow(
                        code=line[6:13].strip(),
                        billable=line[14] == "1",
                        short_title=line[16:76].strip(),
                        long_title=line[77:].strip(),
                    )

    @cached_property
    def _cm_codes(self) -> list[OrderRow]:
        return list(self._order(CM_ORDER))

    @cached_property
    def _codes(self) -> set[str]:
        return {display_code(r.code, Vocabulary.ICD10CM) for r in self._cm_codes}

    @cached_property
    def _index_terms(self) -> dict[str, list[str]]:
        """Code -> alphabetic index entries that point to it (empty if no index)."""
        if not self.has(CM_INDEX):
            return {}
        terms: defaultdict[str, list[str]] = defaultdict(list)
        root = ET.parse(self.path(CM_INDEX)).getroot()  # nosec B314 - trusted CMS file
        for main_term in root.iter("mainTerm"):
            _walk_index(main_term, (), terms)
        return terms

    @cached_property
    def _tabular(self) -> _Tabular:
        tab = _Tabular()
        root = ET.parse(self.path(CM_TABULAR)).getroot()  # nosec B314 - trusted CMS file

        def walk(diag: ET.Element, parent_id: str) -> None:
            code = diag.findtext("name", "").strip()
            tab.in_tabular.add(code)
            tab.isa.append((_cm(code), parent_id))
            tab.holders.append((diag, _cm(code)))
            for note in diag.findall("inclusionTerm/note"):
                tab.inclusion[code].append(" ".join((note.text or "").split()))
            for child in diag.findall("diag"):
                walk(child, _cm(code))

        for chapter in root.iter("chapter"):
            number = chapter.findtext("name", "").strip()
            title = chapter.findtext("desc", "").strip()
            match = _CHAPTER_RANGE.search(title)
            tab.chapters.append((number, match.group(1) if match else "", title))
            chapter_id = _cm(f"chapter:{number}")
            tab.holders.append((chapter, chapter_id))
            for section in chapter.findall("section"):
                block = section.get("id", "")
                block_id = _cm(f"block:{block}")
                tab.blocks.append((block, number, section.findtext("desc", "").strip()))
                tab.isa.append((block_id, chapter_id))
                tab.holders.append((section, block_id))
                for diag in section.findall("diag"):
                    walk(diag, block_id)
        return tab

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield ICD-10-CM chapters, blocks and codes; ICD-10-PCS tables and codes."""
        tab = self._tabular
        for number, code_range, title in tab.chapters:
            yield Concept(
                Vocabulary.ICD10CM, code_range, title, kind="chapter",
                key=f"chapter:{number}", properties={"chapter": number},
            )  # fmt: skip
        for block, chapter, title in tab.blocks:
            yield Concept(
                Vocabulary.ICD10CM, block, title, kind="block",
                key=f"block:{block}", properties={"chapter": chapter},
            )  # fmt: skip
        index_terms = self._index_terms
        for row in self._cm_codes:
            code = display_code(row.code, Vocabulary.ICD10CM)
            yield Concept(
                Vocabulary.ICD10CM,
                code,
                row.long_title,
                kind="code",
                synonyms=tuple(dict.fromkeys(tab.inclusion.get(code, ()))),
                properties={
                    "billable": row.billable,
                    "code_no_dot": row.code,
                    "short_name": row.short_title,
                    "index_terms": list(dict.fromkeys(index_terms.get(code, ()))),
                },
            )

        for row in self._order(PCS_ORDER):
            if row.billable:
                yield Concept(
                    Vocabulary.ICD10PCS,
                    row.code,
                    row.long_title,
                    kind="code",
                    properties={"billable": True, "short_name": row.short_title},
                )
            else:
                yield Concept(
                    Vocabulary.ICD10PCS, row.code, row.long_title, kind="table",
                    key=f"table:{row.code}", properties={"short_name": row.short_title},
                )  # fmt: skip

    def iter_relations(self) -> Iterator[Relation]:
        """Yield the hierarchy and tabular-note edges."""
        tab, codes = self._tabular, self._codes
        for child, parent in tab.isa:
            yield Relation(child, "ISA", parent)
        for code in sorted(codes - tab.in_tabular):
            parent = _parent(code, codes)
            if parent is not None:
                yield Relation(_cm(code), "ISA", _cm(parent))

        for row in self._order(PCS_ORDER):
            if row.billable:
                pcs = concept_id(Vocabulary.ICD10PCS, row.code)
                table = concept_id(Vocabulary.ICD10PCS, f"table:{row.code[:3]}")
                yield Relation(pcs, "ISA", table)

        yield from self._note_relations()

    def _note_relations(self) -> Iterator[Relation]:
        """One edge per (holder, referenced concept, note type), with all note texts."""
        ranges = {r: _cm(f"chapter:{n}") for n, r, _ in self._tabular.chapters if r}
        ranges |= {b: _cm(f"block:{b}") for b, _, _ in self._tabular.blocks}
        edges: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)
        unresolved = 0
        for element, holder in self._tabular.holders:
            for tag, rel_type in NOTE_TYPES.items():
                for note in element.findall(f"{tag}/note"):
                    text = " ".join((note.text or "").split())
                    targets, missed = self._note_targets(text, ranges)
                    unresolved += missed
                    for target in targets:
                        if target != holder:
                            edges[(holder, rel_type, target)].append(text)
        if unresolved:
            log.info("%d ICD-10-CM note references matched no code", unresolved)
        for (source, rel_type, target), notes in edges.items():
            yield Relation(source, rel_type, target, properties={"notes": notes})

    def _note_targets(self, text: str, ranges: dict[str, str]) -> tuple[list[str], int]:
        """Resolve the code references in one note to concept ids.

        A partial code (``E08.-``) is the category itself. A range is a block or
        chapter if one has exactly that range, else every code of the same length
        between its two ends (``J30.1-J30.9``).

        Returns:
            The concept ids, and how many references matched nothing (retired
            codes, or text such as ``(G6PD)`` that looks like a code).
        """
        codes = self._codes
        targets: list[str] = []
        missed = 0
        for group in _PARENS.findall(text):
            for start, end in _REF.findall(group):
                start = start.rstrip(".")
                if not end:
                    if start in codes:
                        targets.append(_cm(start))
                    else:
                        missed += 1
                    continue
                end = end.rstrip(".")
                if f"{start}-{end}" in ranges:
                    targets.append(ranges[f"{start}-{end}"])
                    continue
                span = sorted(
                    c for c in codes if len(c) == len(start) and start <= c <= end
                )
                targets.extend(_cm(c) for c in span)
                missed += not span
        return targets, missed

    @cached_property
    def _ranges(self) -> dict[str, str]:
        """ICD-10-CM block and chapter range (``E08-E13``, ``E00-E89``) -> id."""
        tab = self._tabular
        ranges = {r: _cm(f"chapter:{n}") for n, r, _ in tab.chapters if r}
        ranges |= {b: _cm(f"block:{b}") for b, _, _ in tab.blocks}
        return ranges

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve a code published elsewhere to an ICD-10-CM / ICD-10-PCS concept.

        ICD-10-CM, tried in order: the code as given (``exact``), or a block or
        chapter by its range (``E08-E13``; UMLS writes one-category blocks as
        ``F99-F99``); trimmed and upper-cased (``normalised``); the longest
        prefix that is a code (``ancestor``): a code retired from this release,
        or a target whose 7th character is left open (``S72.001?`` ->
        ``S72.001``, ``M48.40X?`` -> ``M48.40``). ICD-10-PCS: the code, or the
        table of a 3-character code (``08P``), both ``exact``.

        Returns:
            The concept id and how it matched, or ``None``.
        """
        if vocabulary is Vocabulary.ICD10PCS:
            if len(code) == 3:
                table = concept_id(Vocabulary.ICD10PCS, f"table:{code}")
                return (table, "exact") if table in self.concept_ids else None
            return super().match(vocabulary, code)
        if vocabulary is not Vocabulary.ICD10CM:
            return None
        if "-" in code:
            start, _, end = code.strip().upper().partition("-")
            found = self._ranges.get(code) or self._ranges.get(
                start if start == end else f"{start}-{end}"
            )
            return (found, "exact") if found else None
        codes = self._codes
        if code in codes:
            return _cm(code), "exact"
        normalised = code.strip().upper()
        if normalised in codes:
            return _cm(normalised), "normalised"
        prefix = normalised
        while len(prefix) > 3:
            prefix = prefix[:-1].rstrip(".")
            if prefix in codes:
                return _cm(prefix), "ancestor"
        return None

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: the CMS release contains no cross-vocabulary maps."""
        yield from ()
