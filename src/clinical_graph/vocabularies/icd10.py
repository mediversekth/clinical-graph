"""WHO ICD-10, ClaML edition (2019).

* Concepts (``Vocabulary.ICD10``): chapters (``icd10:chapter:4``; ``code`` is the
  chapter's range, ``E00-E90``), blocks (``icd10:block:E10-E14``) and categories
  (``icd10:E11.9``, code with its dot, as published).

  ClaML lists shared subdivisions once, as *modifiers*, and attaches them to
  categories or blocks; they are expanded here into codes of their own:

  - 4th character (``.0`` ... ``.9``) on 3-character categories, e.g. the
    diabetes subdivisions before ``E10``: ``E11`` + ``.0`` *With coma* =
    ``E11.0`` *Type 2 diabetes mellitus: With coma*.
  - 5th character on 4-character codes, e.g. the site codes of chapter XIII
    (``M00.0`` + ``1`` = ``M00.01``) or closed / open for fractures
    (``S72.0`` + ``0`` = ``S72.00``). On a 3-character category without
    subcategories the character follows the dot (``M45`` + ``2`` = ``M45.2``).

  ``ExcludeModifier`` switches a modifier off for a block or category and
  everything under it. WHO's 2019 file does that for every external-cause
  block, so the place and activity subdivisions of ``V01``-``Y98`` are not
  generated. Generated codes have ``generated: true`` and, when WHO marks the
  subdivision as optional, ``optional: true``.

* Relations: ``ISA`` (code -> parent code or block, block -> parent block or
  chapter); ``EXCLUDES`` from the class holding an exclusion note to each
  code, block or chapter it references (``notes`` holds the note texts); and
  ``PAIRED_WITH`` for the dagger / asterisk system: from a code to the
  counterpart(s) WHO names in its title (``A17.0`` *Tuberculous meningitis*,
  dagger -> ``G01`` *Meningitis in bacterial diseases classified elsewhere*,
  asterisk; ``D63.0`` asterisk -> block ``C00-D48``).

* Mappings: none; ICD-10 is the *target* of the SNOMED CT International map.
  :meth:`Icd10Reader.match` resolves those targets to concept ids.
"""

import logging
import re
import xml.etree.ElementTree as ET  # nosec B405 - trusted WHO release file
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import ClassVar

from clinical_graph.model import (
    Concept,
    Mapping,
    PropertyValue,
    Relation,
    Vocabulary,
    concept_id,
)
from clinical_graph.vocabularies.base import VocabularyReader

log = logging.getLogger(__name__)

CLAML = "icd10{v}en.xml"

_USAGE = {"aster": "asterisk", "dagger": "dagger"}
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}
_PLACEHOLDER = re.compile(r"([A-Z]\d\d)\.X(\d)")
_REF_CODE = re.compile(r"[A-Z]\d\d(?:\.\d{1,2})?")


def roman_to_int(numeral: str) -> int:
    """``"XXII"`` -> ``22``."""
    total = 0
    for char, following in zip(numeral, [*numeral[1:], ""], strict=True):
        value = _ROMAN[char]
        total += -value if following and _ROMAN[following] > value else value
    return total


def _label_text(label: ET.Element | None, *, references: bool = True) -> str:
    """The text of a rubric label, whitespace collapsed.

    Args:
        label: The ``Label`` element.
        references: Keep the text of ``Reference`` children (the codes of an
            exclusion note); ``False`` keeps only the description.
    """
    if label is None:
        return ""

    def text(element: ET.Element) -> str:
        parts = [element.text or ""]
        for child in element:
            if references or child.tag != "Reference":
                inner = text(child)
                # Fragments are list items; inline markup (<Sub>12</Sub>) is not.
                block = child.tag in {"Fragment", "Para", "Reference"}
                parts.append(f" {inner} " if block else inner)
            parts.append(child.tail or "")
        return "".join(parts)

    return " ".join(text(label).split())


def _rubrics(element: ET.Element, kind: str) -> list[ET.Element]:
    return [
        label
        for rubric in element.findall("Rubric")
        if rubric.get("kind") == kind
        for label in rubric.findall("Label")
    ]


@dataclass(slots=True)
class _Class:
    """One chapter, block or category, explicit or generated from a modifier."""

    code: str
    kind: str  # chapter, block, category
    name: str
    parent: str | None
    children: list[str] = field(default_factory=list[str])
    synonyms: list[str] = field(default_factory=list[str])
    properties: dict[str, PropertyValue] = field(
        default_factory=dict[str, PropertyValue]
    )
    exclusions: list[tuple[str, list[str]]] = field(
        default_factory=list[tuple[str, list[str]]]
    )
    """(note text, referenced codes) per exclusion rubric."""
    paired: list[str] = field(default_factory=list[str])
    """Dagger / asterisk counterparts named in the title (``A17.0`` -> ``G01``)."""


@dataclass(frozen=True, slots=True)
class _ModifierClass:
    code: str  # ".0" (4th character) or "0" (5th character)
    name: str
    synonyms: tuple[str, ...]


class Icd10Reader(VocabularyReader):
    """Reader for the WHO ICD-10 ClaML file."""

    source_key: ClassVar[str] = "icd10"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.ICD10,)

    @cached_property
    def _classes(self) -> dict[str, _Class]:
        """Every class by code, modifiers expanded, in classification order."""
        root = ET.parse(self.path(CLAML)).getroot()  # nosec B314

        modifiers: defaultdict[str, list[_ModifierClass]] = defaultdict(list)
        for mc in root.iter("ModifierClass"):
            modifiers[mc.get("modifier", "")].append(
                _ModifierClass(
                    code=mc.get("code", ""),
                    name=_label_text(next(iter(_rubrics(mc, "preferred")), None)),
                    synonyms=tuple(
                        _label_text(label) for label in _rubrics(mc, "inclusion")
                    ),
                )
            )

        classes: dict[str, _Class] = {}
        applied: list[tuple[str, str, bool]] = []  # (holder, modifier, optional)
        excluded: dict[str, set[str]] = {}
        for element in root.iter("Class"):
            code, kind = element.get("code", ""), element.get("kind", "")
            superclass = element.find("SuperClass")
            preferred = next(iter(_rubrics(element, "preferred")), None)
            cls = _Class(
                code=code,
                kind=kind,
                name=_label_text(preferred, references=False),
                parent=superclass.get("code") if superclass is not None else None,
                children=[s.get("code", "") for s in element.findall("SubClass")],
                synonyms=[_label_text(lb) for lb in _rubrics(element, "inclusion")],
            )
            if preferred is not None:
                cls.paired = [r.text or "" for r in preferred.iter("Reference")]
            props = cls.properties
            if usage := element.get("usage"):
                props["usage"] = _USAGE.get(usage, usage)
            if long_names := _rubrics(element, "preferredLong"):
                # Titles of e.g. C00.0 are short ("External upper lip") with a
                # long form ("Malignant neoplasm: External upper lip").
                props["short_name"] = cls.name
                cls.name = _label_text(long_names[0], references=False)
            if definitions := _rubrics(element, "definition"):
                props["definition"] = " ".join(_label_text(d) for d in definitions)
            for label in _rubrics(element, "exclusion"):
                refs = [r.text or "" for r in label.iter("Reference")]
                cls.exclusions.append((_label_text(label, references=False), refs))
            for mb in element.findall("ModifiedBy"):
                usage = mb.find("Meta[@name='usage']")
                optional = usage is not None and usage.get("value") == "optional"
                applied.append((code, mb.get("code", ""), optional))
            if ex := element.findall("ExcludeModifier"):
                excluded[code] = {e.get("code", "") for e in ex}
            classes[code] = cls

        # 4th-character modifiers first, so 5th characters also reach their codes.
        applied.sort(key=lambda a: not modifiers[a[1]][0].code.startswith("."))
        for holder, modifier, optional in applied:
            self._expand(classes, holder, modifiers[modifier], modifier, excluded,
                         optional)  # fmt: skip
        return classes

    @staticmethod
    def _expand(
        classes: dict[str, _Class],
        holder: str,
        subdivisions: list[_ModifierClass],
        modifier: str,
        excluded: dict[str, set[str]],
        optional: bool,
    ) -> None:
        """Add the codes one ``ModifiedBy`` generates under ``holder``."""
        fourth = subdivisions[0].code.startswith(".")
        categories: list[str] = []
        stack = [holder]
        while stack:
            code = stack.pop()
            if modifier in excluded.get(code, ()):
                continue
            cls = classes[code]
            if cls.kind == "category":
                categories.append(code)
            if cls.kind != "category" or len(code) == 3:
                stack.extend(reversed(cls.children))

        if fourth:
            bases = [c for c in categories if len(c) == 3]
        else:
            bases = [
                c
                for c in categories
                if len(c) == 5 or (len(c) == 3 and not classes[c].children)
            ]
        for base in bases:
            parent = classes[base]
            for sub in subdivisions:
                sep = "" if fourth or "." in base else "."
                code = f"{base}{sep}{sub.code}"
                if code in classes:
                    continue
                classes[code] = _Class(
                    code=code,
                    kind="category",
                    name=f"{parent.name}: {sub.name}",
                    parent=base,
                    synonyms=list(sub.synonyms),
                    properties={
                        "generated": True,
                        "optional": optional,
                        **(
                            {"usage": parent.properties["usage"]}
                            if "usage" in parent.properties
                            else {}
                        ),
                    },
                )
                parent.children.append(code)

    def _id(self, code: str) -> str:
        cls = self._classes[code]
        if cls.kind == "chapter":
            key = f"chapter:{roman_to_int(code)}"
        elif cls.kind == "block":
            key = f"block:{code}"
        else:
            key = code
        return concept_id(Vocabulary.ICD10, key)

    def _chapter_range(self, cls: _Class) -> str:
        blocks = [c for c in cls.children if self._classes[c].kind == "block"]
        if not blocks:
            return cls.code
        return f"{blocks[0].split('-')[0]}-{blocks[-1].split('-')[-1]}"

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield chapters, blocks and codes (generated subdivisions included)."""
        for code, cls in self._classes.items():
            props: dict[str, PropertyValue] = dict(cls.properties)
            if cls.kind == "chapter":
                props["chapter"] = roman_to_int(code)
                yield Concept(
                    Vocabulary.ICD10, self._chapter_range(cls), cls.name,
                    kind="chapter", key=f"chapter:{roman_to_int(code)}",
                    properties=props,
                )  # fmt: skip
            elif cls.kind == "block":
                yield Concept(
                    Vocabulary.ICD10, code, cls.name, kind="block",
                    key=f"block:{code}", synonyms=tuple(cls.synonyms),
                    properties=props,
                )  # fmt: skip
            else:
                props["code_no_dot"] = code.replace(".", "")
                props["terminal"] = not cls.children
                props.setdefault("generated", False)
                yield Concept(
                    Vocabulary.ICD10,
                    code,
                    cls.name,
                    kind="code",
                    synonyms=tuple(dict.fromkeys(s for s in cls.synonyms if s)),
                    properties=props,
                )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield ``ISA`` and ``EXCLUDES`` edges."""
        classes = self._classes
        for code, cls in classes.items():
            if cls.parent is not None and cls.parent in classes:
                yield Relation(self._id(code), "ISA", self._id(cls.parent))

        ranges = {
            self._chapter_range(c): self._id(code)
            for code, c in classes.items()
            if c.kind == "chapter"
        }
        ranges |= {
            code: self._id(code) for code, c in classes.items() if c.kind == "block"
        }
        edges: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
        unresolved = 0
        for code, cls in classes.items():
            holder = self._id(code)
            for text, refs in cls.exclusions:
                for ref in refs:
                    targets = self._resolve_reference(ref, ranges)
                    unresolved += not targets
                    for target in targets:
                        if target != holder and text not in edges[(holder, target)]:
                            edges[(holder, target)].append(text)
        if unresolved:
            log.info("%d ICD-10 exclusion references matched no code", unresolved)
        for (source, target), notes in edges.items():
            yield Relation(source, "EXCLUDES", target, properties={"notes": notes})

        pairs: set[tuple[str, str]] = set()
        for code, cls in classes.items():
            holder = self._id(code)
            for ref in cls.paired:
                for target in self._resolve_reference(ref, ranges):
                    if target != holder and (holder, target) not in pairs:
                        pairs.add((holder, target))
                        yield Relation(holder, "PAIRED_WITH", target)

    def _resolve_reference(self, ref: str, ranges: dict[str, str]) -> list[str]:
        """Concept ids of one exclusion reference.

        ``E11.9`` is that code, ``E10.-`` the category, ``E10-E14`` the block or
        chapter with exactly that range, or else every category of the same
        length between the two ends; dagger and asterisk marks are ignored.
        """
        ref = ref.strip().rstrip("*+† ").removesuffix(".-").removesuffix("-")
        if ref in ranges:
            return [ranges[ref]]
        codes = _REF_CODE.findall(ref)
        if len(codes) == 1 and codes[0] == ref:
            return [self._id(ref)] if ref in self._classes else []
        if len(codes) == 2 and "-" in ref:
            start, end = codes
            return [
                self._id(c)
                for c, cls in self._classes.items()
                if cls.kind == "category" and len(c) == len(start) and start <= c <= end
            ]
        return []

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve a map target to an ICD-10 code.

        Tried in order: the code as given (``exact``); upper-cased, or with the
        ``X`` placeholder some maps put in the 4th position removed
        (``M45.X2`` -> ``M45.2``) (``normalised``); the longest prefix that is a
        code, e.g. a retired subdivision or one WHO's file does not generate
        (``W19.9`` -> ``W19``) (``ancestor``).

        Returns:
            The concept id and how it matched, or ``None``.
        """
        if vocabulary is not Vocabulary.ICD10:
            return None
        if "-" in code:
            return self._match_range(code)
        categories = self._classes
        if code in categories and categories[code].kind == "category":
            return self._id(code), "exact"
        normalised = code.strip().upper()
        if placeholder := _PLACEHOLDER.fullmatch(normalised):
            normalised = f"{placeholder.group(1)}.{placeholder.group(2)}"
        if normalised in categories and categories[normalised].kind == "category":
            return self._id(normalised), "normalised"
        prefix = normalised
        while len(prefix) > 3:
            prefix = prefix[:-1].rstrip(".")
            if prefix in categories and categories[prefix].kind == "category":
                return self._id(prefix), "ancestor"
        return None

    @cached_property
    def _ranges(self) -> dict[str, str]:
        """Block and chapter range (``E10-E14``, ``E00-E90``) -> id."""
        ranges: dict[str, str] = {}
        for code, cls in self._classes.items():
            if cls.kind == "block":
                ranges[code] = self._id(code)
            elif cls.kind == "chapter":
                ranges[self._chapter_range(cls)] = self._id(code)
        return ranges

    def _match_range(self, code: str) -> tuple[str, str] | None:
        """A block or chapter by its range; UMLS writes ``D55-D59.9``, ``F99-F99.9``."""
        start, _, end = code.strip().upper().partition("-")
        end = end.split(".", 1)[0]
        for candidate in (f"{start}-{end}", start if start == end else None):
            if candidate and candidate in self._ranges:
                how = "exact" if candidate == code else "normalised"
                return self._ranges[candidate], how
        return None

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: WHO ICD-10 has no maps to other vocabularies."""
        yield from ()
