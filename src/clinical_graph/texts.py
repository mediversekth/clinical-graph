"""The texts that find a concept: what the search indexes hold.

Both the SapBERT embeddings (:mod:`clinical_graph.embeddings`) and the
Elasticsearch indexes (:mod:`clinical_graph.elastic`) are built from these, so
the two retrievers see the same concepts and the same texts.

Every *current* concept is indexed, except grouping nodes that are not codes of
their own (:data:`SKIPPED_KINDS`). A concept gets one row per distinct text
(case and whitespace ignored), its name first:

* every vocabulary: ``name``, then each of ``synonyms`` (``synonym``)
* SNOMED CT: the FSN without its semantic tag (``fsn``), since SapBERT was
  trained on plain names
* LOINC terms: ``display_name``, ``short_name``, ``consumer_name``, and the
  ``RELATEDNAMES2`` entries (``related_name``) that at most
  :data:`RELATED_NAME_MAX_CODES` terms share: the field mixes real synonyms
  (``HbA1c``) with words that thousands of terms carry (``Blood``, ``Level``)
* LOINC parts: ``display_name``
* ICD-10-CM codes: the alphabetic index entries (``index_term``)
"""

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from clinical_graph.model import Concept, PropertyValue, Vocabulary
from clinical_graph.vocabularies.snomed import split_fsn

SKIPPED_KINDS: dict[Vocabulary, frozenset[str]] = {
    Vocabulary.ICD10CM: frozenset({"chapter", "block"}),
    Vocabulary.ICD10PCS: frozenset({"table"}),
    Vocabulary.ICD10: frozenset({"chapter", "block"}),
    Vocabulary.ICD9CM: frozenset({"classification", "chapter", "block"}),
    Vocabulary.LOINC: frozenset({"hierarchy", "group", "parentgroup"}),
    Vocabulary.ICF: frozenset({"section", "component", "qualifier_group", "qualifier"}),
}
"""Kinds of concept left out per vocabulary: code ranges, tables and groupings."""

RELATED_NAME_MAX_CODES = 20
"""A LOINC related name is embedded only if at most this many terms carry it."""

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Text:
    """One text of one concept, as embedded.

    ``origin`` says where the text comes from: ``name``, ``synonym``, ``fsn``,
    ``display_name``, ``short_name``, ``consumer_name``, ``related_name`` or
    ``index_term``.
    """

    concept_id: str
    origin: str
    text: str


def is_indexed(concept: Concept) -> bool:
    """Whether a concept is searchable: current, and not a grouping node."""
    skipped = SKIPPED_KINDS.get(concept.vocabulary, frozenset())
    return concept.active and concept.kind not in skipped


def _strings(value: PropertyValue) -> list[str]:
    """A string or list-of-strings property as a list."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return []


def _candidates(concept: Concept) -> Iterator[tuple[str, str]]:
    """``(origin, text)`` of a concept, before deduplication, name first."""
    props = concept.properties
    yield "name", concept.name
    if concept.vocabulary is Vocabulary.SNOMED:
        for fsn in _strings(props.get("fsn")):
            yield "fsn", split_fsn(fsn)[0]
    for origin in ("display_name", "short_name", "consumer_name"):
        if concept.vocabulary is Vocabulary.LOINC:
            for text in _strings(props.get(origin)):
                yield origin, text
    for synonym in concept.synonyms:
        yield "synonym", synonym
    if concept.vocabulary is Vocabulary.ICD10CM:
        for text in _strings(props.get("index_terms")):
            yield "index_term", text


def _related_names(concept: Concept) -> list[str]:
    if concept.vocabulary is not Vocabulary.LOINC:
        return []
    return _strings(concept.properties.get("related_names"))


def concept_texts(concept: Concept, related_ok: set[str] | None = None) -> list[Text]:
    """The texts of one concept, deduplicated, name first.

    Args:
        concept: The concept.
        related_ok: Lower-cased LOINC related names that are specific enough to
            embed; ``None`` embeds none.

    Returns:
        One :class:`Text` per distinct text.
    """
    candidates = list(_candidates(concept))
    if related_ok:
        candidates += [
            ("related_name", n)
            for n in _related_names(concept)
            if n.lower() in related_ok
        ]
    seen: set[str] = set()
    texts: list[Text] = []
    for origin, raw in candidates:
        text = _SPACE.sub(" ", raw).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            texts.append(Text(concept.id, origin, text))
    return texts


def iter_concept_texts(
    concepts: Iterable[Concept],
) -> Iterator[tuple[Concept, list[Text]]]:
    """Every indexed concept with its texts.

    Reads ``concepts`` once into memory: the LOINC related names are kept or
    dropped by how many terms share them.
    """
    indexed = [c for c in concepts if is_indexed(c)]
    uses = Counter(
        name for c in indexed for name in {n.lower() for n in _related_names(c)}
    )
    related_ok = {n for n, k in uses.items() if k <= RELATED_NAME_MAX_CODES}
    for concept in indexed:
        yield concept, concept_texts(concept, related_ok)


def iter_texts(concepts: Iterable[Concept]) -> Iterator[Text]:
    """The texts of every indexed concept, concept by concept."""
    for _, texts in iter_concept_texts(concepts):
        yield from texts
