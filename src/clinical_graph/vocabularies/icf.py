"""WHO ICF (International Classification of Functioning, Disability and Health).

Read from the ICF *simple tabulation* WHO publishes with each ICD-11 platform
release (``SimpleTabulation-ICF-en.txt``, from the ICF browser's Info menu). ICF
has no ClaML any more; the tabulation has the codes, titles and hierarchy, but
no definitions or inclusion / exclusion notes (those are only in the ICD API).

* Concepts (``Vocabulary.ICF``), ``code`` as ICF writes it:

  - ``section``: the tabulation's two top chapters, ``icf:section:category``
    (*ICF Category*) and ``icf:section:qualifier`` (*ICF Qualifier*);
  - ``component``: body functions, body structures, activities and
    participation, environmental factors (``icf:component:b``, code ``b``);
  - ``chapter``: the ICF chapters (``icf:chapter:b1`` *Mental functions*);
  - ``block``: the ICF blocks, coded by their range (``icf:block:b110-b139``
    *Global mental functions*);
  - ``category``: the coded categories, 1st to 4th level (``icf:b110``,
    ``icf:b1100``, ``icf:d4500``);
  - ``qualifier_group`` and ``qualifier``: the qualifier scales
    (*Extent or magnitude of impairment*: ``icf:qualifier_group:<id>``, with
    qualifiers ``icf:qi0`` ... ``icf:qi9``).

  The tabulation gives the groupings no code (blocks have WHO's ``BlockId``,
  ``BlockL3-b11``, kept as ``block_id``); their codes are derived from the
  categories under them, which is how ICF writes them and how UMLS cites them.
  Every node has ``uri`` (its ICF linearization URI), ``is_leaf``,
  ``is_residual`` (*other specified* / *unspecified*) and, except the sections,
  ``component`` (``b``, ``s``, ``d``, ``e``; ``q`` for qualifiers). All but the
  residual categories have ``foundation_uri`` (the WHO-FIC Foundation entity,
  shared with ICD-11); ``coding_note`` where WHO gives one.

* Relations: ``ISA`` (child -> parent in the tabulation).

* Mappings: none; ICF is linked through UMLS (``umls``).
"""

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
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

TABULATION = "SimpleTabulation-ICF-en.txt"

_INDENT = re.compile(r"^(?:- )+")
_CODE = re.compile(r"^[bdes]\d+$")


@dataclass(frozen=True, slots=True)
class _Row:
    uri: str  # linearization URI: every row has one
    foundation_uri: str  # "" for residual categories (linearization only)
    code: str
    block_id: str
    title: str
    class_kind: str  # chapter, block, category
    depth: int
    is_residual: bool
    is_leaf: bool
    coding_note: str
    parent: str  # linearization URI of the parent, "" for the two top chapters


def _flag(value: str) -> bool:
    return value.strip().lower() == "true"


class IcfReader(VocabularyReader):
    """Reader for the WHO ICF simple tabulation."""

    source_key: ClassVar[str] = "icf"
    vocabularies: ClassVar[tuple[Vocabulary, ...]] = (Vocabulary.ICF,)

    @cached_property
    def _rows(self) -> list[_Row]:
        """The tabulation's rows, in file (hierarchy) order.

        ``Parent`` is a Foundation URI; it is turned into the parent's
        linearization URI, since residual categories have no Foundation entity.
        """
        rows: list[_Row] = []
        with self.path(TABULATION).open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader)
            col = {name.strip(): i for i, name in enumerate(header)}
            for f in reader:
                if not f:
                    continue
                rows.append(
                    _Row(
                        uri=f[col["Linearization URI"]].strip(),
                        foundation_uri=f[col["Foundation URI"]].strip(),
                        code=f[col["Code"]].strip(),
                        block_id=f[col["BlockId"]].strip(),
                        title=_INDENT.sub("", f[col["Title"]].strip()),
                        class_kind=f[col["ClassKind"]].strip(),
                        depth=int(f[col["DepthInKind"]]),
                        is_residual=_flag(f[col["IsResidual"]]),
                        is_leaf=_flag(f[col["isLeaf"]]),
                        coding_note=f[col["CodingNote"]].strip(),
                        parent=f[col["Parent"]].strip(),
                    )
                )
        linearized = {r.foundation_uri: r.uri for r in rows if r.foundation_uri}
        return [replace(r, parent=linearized.get(r.parent, "")) for r in rows]

    @cached_property
    def _codes(self) -> dict[str, list[str]]:
        """Linearization URI -> its code and the codes of every category below it."""
        children: dict[str, list[_Row]] = {}
        for row in self._rows:
            children.setdefault(row.parent, []).append(row)

        below: dict[str, list[str]] = {}

        def collect(row: _Row) -> list[str]:
            codes = [row.code] if row.code else []
            for child in children.get(row.uri, []):
                codes += collect(child)
            below[row.uri] = codes
            return codes

        for root in children.get("", []):
            collect(root)
        return below

    @cached_property
    def _keys(self) -> dict[str, tuple[str, str, str | None]]:
        """Linearization URI -> (kind, code, key) of every row.

        ``key`` is ``None`` for categories and qualifiers (their id is the code).
        """
        keys: dict[str, tuple[str, str, str | None]] = {}
        for row in self._rows:
            kind, code = self._kind_code(row)
            key = None if kind in {"category", "qualifier"} else f"{kind}:{code}"
            keys[row.uri] = (kind, code, key)
        return keys

    def _id(self, uri: str) -> str:
        _, code, key = self._keys[uri]
        return concept_id(Vocabulary.ICF, key or code)

    def _kind_code(self, row: _Row) -> tuple[str, str]:
        """The node kind and ICF code of a row (derived for groupings)."""
        if row.class_kind == "category":
            return ("qualifier" if row.code.startswith("q") else "category"), row.code
        if row.class_kind == "chapter":
            return "section", row.title.removeprefix("ICF ").lower()
        if not row.block_id:  # a qualifier scale: no BlockId, no code
            return "qualifier_group", row.uri.rsplit("/", 1)[-1]
        codes = [c for c in self._codes[row.uri] if _CODE.match(c)]
        tops = sorted(c for c in codes if len(c) == 4)  # 1st-level categories
        if row.depth == 1:
            return "component", codes[0][0]
        if row.depth == 2:
            return "chapter", codes[0][:2]
        return "block", f"{tops[0]}-{tops[-1]}"

    def _component(self, row: _Row) -> str | None:
        """``b``, ``s``, ``d``, ``e`` or ``q``, if all codes below share it."""
        letters = {c[0] for c in self._codes[row.uri]}
        return letters.pop() if len(letters) == 1 else None

    def iter_concepts(self) -> Iterator[Concept]:
        """Yield sections, components, chapters, blocks, categories, qualifiers."""
        for row in self._rows:
            kind, code, key = self._keys[row.uri]
            properties: dict[str, PropertyValue] = {
                "uri": row.uri,
                "is_leaf": row.is_leaf,
                "is_residual": row.is_residual,
            }
            if component := self._component(row):
                properties["component"] = component
            if row.foundation_uri:
                properties["foundation_uri"] = row.foundation_uri
            if row.block_id:
                properties["block_id"] = row.block_id
            if row.coding_note:
                properties["coding_note"] = row.coding_note
            yield Concept(
                Vocabulary.ICF,
                code,
                row.title,
                kind=kind,
                key=key,
                properties=properties,
            )

    def iter_relations(self) -> Iterator[Relation]:
        """Yield ``ISA`` from each entity to its parent in the tabulation."""
        for row in self._rows:
            if row.parent:
                yield Relation(self._id(row.uri), "ISA", self._id(row.parent))

    def iter_mappings(self) -> Iterator[Mapping]:
        """Yield nothing: ICF publishes no maps; UMLS links it."""
        yield from ()

    @cached_property
    def _by_code(self) -> dict[str, str]:
        """ICF code (``b110``, ``b110-b139``, ``b1``, ``b``) -> id."""
        return {
            code: self._id(uri)
            for uri, (kind, code, _) in self._keys.items()
            if kind not in {"section", "qualifier_group"}
        }

    def match(self, vocabulary: Vocabulary, code: str) -> tuple[str, str] | None:
        """Resolve an ICF code: a category, or a block, chapter or component.

        Tried in order: the code as given (``exact``); trimmed and lower-cased
        (``normalised``). No broader-code fallback: ICF codes are not cited
        with open positions.

        Returns:
            The concept id and how it matched, or ``None``.
        """
        if vocabulary is not Vocabulary.ICF:
            return None
        if code in self._by_code:
            return self._by_code[code], "exact"
        normalised = code.strip().lower()
        if normalised in self._by_code:
            return self._by_code[normalised], "normalised"
        return None
