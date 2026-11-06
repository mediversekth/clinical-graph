"""ICD-9-CM, CMS Version 32 (FY2015, the final release), with UMLS headers.

ICD-9-CM has two volumes, kept in one vocabulary (``Vocabulary.ICD9CM``): their
codes cannot collide once dotted, diagnoses having three characters before the
dot (``250.01``, ``V45.81``; four for external causes, ``E849.0``) and
procedures two (``45.81``).

* Concepts:

  - codes, with the published dot (``icd9cm:250.01``, ``icd9cm:45.81``). The
    billable codes come from the CMS files (long title as ``name``, abbreviated
    title as ``short_name``, ``billable: true``). CMS lists no headers; the
    categories and subcategories above them (``250``, ``250.0``) come from the
    ICD9CM header atoms (``TTY=HT``) of the UMLS Metathesaurus (``umls`` source,
    ``billable: false``), if it is on disk.
  - grouping ranges from the same UMLS atoms, ``icd9cm:<kind>:<range>``:
    ``classification`` (``001-999.99`` *Diseases and injuries*, ``00-99.99``
    *Procedures*), ``chapter`` (``001-139.99`` *Infectious and parasitic
    diseases*, ``01-05.99`` *Operations on the nervous system*; the
    supplementary V and E classifications, ``V01-V91.99``, ``E000-E999.9``, are
    chapters too) and ``block`` (``010-018.99`` *Tuberculosis*, nested blocks
    included). Every concept has ``axis``: ``diagnosis`` or ``procedure``.

* Relations: ``ISA``: a dotted code -> its longest prefix that is a code
  (``250.01`` -> ``250.0`` -> ``250``); a category -> the narrowest range
  containing it; a range -> the narrowest range containing it.

* Mappings: none; the maps are their own sources (``icd9cm_snomed``,
  ``icd9cm_gems``).
"""

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from typing import ClassVar

from clinical_graph.model import Concept, Mapping, Relation, Vocabulary, concept_id
from clinical_graph.sources import load_manifest
from clinical_graph.vocabularies.base import VocabularyReader

log = logging.getLogger(__name__)

DX_LONG = "ICD-9-CM-v{v}-master-descriptions/CMS{v}_DESC_LONG_DX.txt"
DX_SHORT = "ICD-9-CM-v{v}-master-descriptions/CMS{v}_DESC_SHORT_DX.txt"
SG_LONG = "ICD-9-CM-v{v}-master-descriptions/CMS{v}_DESC_LONG_SG.txt"
SG_SHORT = "ICD-9-CM-v{v}-master-descriptions/CMS{v}_DESC_SHORT_SG.txt"

UMLS_SOURCE = "umls"
UMLS_CONSO = "META/MRCONSO.RRF"

CLASSIFICATIONS = frozenset({"001-999.99", "00-99.99"})
"""UMLS ranges above the chapters: all diseases and injuries, all procedures."""

_NUMBER = re.compile(r"([VE]?)(\d+(?:\.\d+)?)")


def dotted(code: str, *, procedure: bool) -> str:
    """Add the dot to an ICD-9-CM code as CMS and the GEMs publish it.

    ``"25001"`` -> ``"250.01"``, ``"E8490"`` -> ``"E849.0"``; procedures (volume
    3) ``"4581"`` -> ``"45.81"``.
    """
    code = code.strip()
    width = 2 if procedure else 4 if code.startswith("E") else 3
    return f"{code[:width]}.{code[width:]}" if len(code) > width else code


def _axis(code: str) -> str:
    """``diagnosis`` or ``procedure``, from a dotted code or a range."""
    head = code.split("-", 1)[0].split(".", 1)[0]
    return "procedure" if head.isdigit() and len(head) == 2 else "diagnosis"


def _space(code: str) -> tuple[str, float]:
    """Where a code or range bound sits: its axis and prefix, and its number."""
    match = _NUMBER.fullmatch(code)
    if match is None:
        raise ValueError(f"not an ICD-9-CM code: {code!r}")
    return f"{_axis(code)}:{match.group(1)}", float(match.group(2))


@dataclass(frozen=True, slots=True)
class _Range:
    """A UMLS grouping range, ``001-139.99``."""

    code: str
    name: str
    space: str
    start: float
    end: float

    def contains(self, code: str) -> bool:
        space, number = _space(code)
        return space == self.space and self.start <= number <= self.end

    @property
    def width(self) -> float:
        return self.end - self.start


class Icd9CmReader(VocabularyReader):
    """Reader for the CMS ICD-9-CM v32 files, with the UMLS ICD9CM headers."""

    source_key: ClassVar[str] = "icd9cm"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.ICD9CM,)

    def _titles(self, manifest_path: str, *, procedure: bool) -> dict[str, str]:
        """Dotted code -> title, from a CMS description file (Latin-1)."""
        titles: dict[str, str] = {}
        with self.path(manifest_path).open(encoding="latin-1") as fh:
            for line in fh:
                code, _, title = line.strip().partition(" ")
                if code:
                    titles[dotted(code, procedure=procedure)] = title.strip()
        return titles

    @cached_property
    def _billable(self) -> dict[str, tuple[str, str]]:
        """Dotted billable code -> (long title, abbreviated title)."""
        codes: dict[str, tuple[str, str]] = {}
        for long, short, procedure in (
            (DX_LONG, DX_SHORT, False),
            (SG_LONG, SG_SHORT, True),
        ):
            short_titles = self._titles(short, procedure=procedure)
            for code, title in self._titles(long, procedure=procedure).items():
                codes[code] = (title, short_titles.get(code, ""))
        return codes

    @cached_property
    def _headers(self) -> dict[str, str]:
        """UMLS ICD9CM header atoms (``TTY=HT``): code or range -> name.

        Empty, with a warning, if the UMLS release is not on disk.
        """
        try:
            path = load_manifest()[UMLS_SOURCE].file(UMLS_CONSO, self.raw_dir)
        except KeyError:
            path = None
        if path is None or not path.is_file():
            log.warning("UMLS MRCONSO not found: ICD-9-CM loaded without headers")
            return {}
        headers: dict[str, str] = {}
        with path.open(encoding="utf-8", newline="") as fh:
            for line in fh:
                if "|ICD9CM|HT|" not in line:
                    continue
                f = line.split("|", 18)
                if f[11] == "ICD9CM" and f[12] == "HT" and f[16] == "N":
                    headers.setdefault(f[13], f[14])
        return headers

    @cached_property
    def _ranges(self) -> dict[str, _Range]:
        ranges: dict[str, _Range] = {}
        for code, name in self._headers.items():
            if "-" in code:
                start, _, end = code.partition("-")
                space, low = _space(start)
                _, high = _space(end)
                ranges[code] = _Range(code, name, space, low, high)
        return ranges

    @cached_property
    def _codes(self) -> dict[str, tuple[str, str, bool]]:
        """Dotted code -> (name, abbreviated title, billable).

        The CMS billable codes, then the UMLS headers that are not among them.
        """
        codes = {c: (long, short, True) for c, (long, short) in self._billable.items()}
        for code, name in self._headers.items():
            if "-" not in code and code not in codes:
                codes[code] = (name, "", False)
        return codes

    def _range_parent(self, code: str, *, strict: bool) -> _Range | None:
        """The narrowest range containing a code or range (other than itself)."""
        if code in self._ranges:
            own = self._ranges[code]
            candidates = [
                r
                for r in self._ranges.values()
                if r.code != code
                and r.space == own.space
                and r.start <= own.start
                and own.end <= r.end
                and (r.width > own.width or not strict)
            ]
        else:
            candidates = [r for r in self._ranges.values() if r.contains(code)]
        return min(candidates, key=lambda r: r.width, default=None)

    @cached_property
    def _range_kinds(self) -> dict[str, str]:
        """Range -> ``classification``, ``chapter`` or ``block``."""
        kinds: dict[str, str] = {}
        for code in self._ranges:
            parent = self._range_parent(code, strict=True)
            if code in CLASSIFICATIONS:
                kinds[code] = "classification"
            elif parent is None or parent.code in CLASSIFICATIONS:
                kinds[code] = "chapter"
            else:
                kinds[code] = "block"
        return kinds

    def _id(self, code: str) -> str:
        """Concept id of a code or range."""
        if code in self._ranges:
            return concept_id(Vocabulary.ICD9CM, f"{self._range_kinds[code]}:{code}")
        return concept_id(Vocabulary.ICD9CM, code)

    def _parent(self, code: str) -> str | None:
        """The ``ISA`` parent of a code or range, as a code or range."""
        if code not in self._ranges:
            prefix = code
            while "." in prefix:
                prefix = prefix[:-1].rstrip(".")
                if prefix in self._codes:
                    return prefix
        parent = self._range_parent(code, strict=True)
        return parent.code if parent else None

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield the ranges, then the codes (headers and billable codes)."""
        kinds = self._range_kinds
        for code, r in self._ranges.items():
            yield Concept(
                Vocabulary.ICD9CM,
                code,
                r.name,
                kind=kinds[code],
                key=f"{kinds[code]}:{code}",
                properties={"axis": _axis(code)},
            )
        for code, (name, short, billable) in self._codes.items():
            yield Concept(
                Vocabulary.ICD9CM,
                code,
                name,
                kind="code",
                properties={
                    "axis": _axis(code),
                    "billable": billable,
                    "code_no_dot": code.replace(".", ""),
                    "short_name": short or None,
                },
            )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield the ``ISA`` hierarchy."""
        orphans = 0
        for code in [*self._ranges, *self._codes]:
            parent = self._parent(code)
            if parent is None:
                orphans += code not in self._ranges  # roots: the classifications, V, E
                continue
            yield Relation(self._id(code), "ISA", self._id(parent))
        if orphans:
            log.info("%d ICD-9-CM codes or ranges have no parent", orphans)

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: the maps are sources of their own."""
        yield from ()

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve a code published elsewhere to an ICD-9-CM concept.

        Tried in order: the code or range as given (``exact``); trimmed and
        upper-cased (``normalised``); the longest prefix that is a code
        (``ancestor``). Codes must carry their dot: ``0010`` could be the
        diagnosis ``001.0`` or the procedure ``00.10``; see :func:`dotted`.

        Returns:
            The concept id and how it matched, or ``None``.
        """
        if vocabulary is not Vocabulary.ICD9CM:
            return None
        if code in self._codes or code in self._ranges:
            return self._id(code), "exact"
        normalised = code.strip().upper()
        if normalised in self._codes or normalised in self._ranges:
            return self._id(normalised), "normalised"
        prefix = normalised
        while "." in prefix:
            prefix = prefix[:-1].rstrip(".")
            if prefix in self._codes:
                return self._id(prefix), "ancestor"
        return None
