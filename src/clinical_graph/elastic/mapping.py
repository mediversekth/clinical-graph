"""Index names, analysis settings and the document mapping.

Ported from mediverse's SNOMED text index, now used by every vocabulary: an
English analyzer (lowercase, ASCII folding, possessives, stemming) whose stop
list keeps negations, since in clinical text *no* and *not* change the meaning
(*No known allergies*).
"""

from typing import Any

from clinical_graph.model import Vocabulary

PREFIX = "clinical_graph_"
"""Every index and alias made here starts with this, so they never collide with
other projects' indexes on the same cluster (mediverse: ``snomed_ct_v2``, ...)."""


def index_name(source_key: str, version: str, built: str) -> str:
    """Physical index of one build of a source release.

    E.g. ``clinical_graph_loinc_2.83_20261104t145501``: the build time makes
    every build a new index, so a rebuild never touches the one being searched.
    """
    return f"{PREFIX}{source_key}_{version}_{built}".lower()


def alias_name(vocabulary: Vocabulary) -> str:
    """Alias to search one vocabulary, e.g. ``clinical_graph_icd10cm``."""
    return f"{PREFIX}{vocabulary}"


# Lucene's _english_ stop list minus negations ("no", "not")
STOPWORDS: list[str] = [
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in",
    "into", "is", "it", "of", "on", "or", "such", "that", "the", "their",
    "then", "there", "these", "they", "this", "to", "was", "will", "with",
]  # fmt: skip

SETTINGS: dict[str, Any] = {
    "number_of_shards": 1,
    "number_of_replicas": 0,  # single node: no replicas, so the index can go green
    "analysis": {
        "filter": {
            "en_stop": {"type": "stop", "stopwords": STOPWORDS},
            "en_stem": {"type": "stemmer", "language": "english"},
            "en_possessive": {"type": "stemmer", "language": "possessive_english"},
        },
        "analyzer": {
            "en_folded": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "asciifolding",
                    "en_possessive",
                    "en_stop",
                    "en_stem",
                ],
            }
        },
        "normalizer": {
            "keyword_no_lower": {"type": "custom", "filter": ["asciifolding"]},
            "keyword_folded": {
                "type": "custom",
                "filter": ["lowercase", "asciifolding"],
            },
        },
    },
}

_KEYWORD: dict[str, Any] = {"type": "keyword"}

CONCEPT_FIELDS: dict[str, dict[str, Any]] = {
    "semantic_tag": _KEYWORD,  # SNOMEDCT
    "extension": _KEYWORD,  # SNOMEDCT: "loinc" for the LOINC Extension
    "class": _KEYWORD,  # LOINC term class (CHEM, HEM/BC, ...)
    "order_obs": _KEYWORD,  # LOINC term: Order, Observation, Both
    "part_type": _KEYWORD,  # LOINC part (COMPONENT, SYSTEM, ...)
    "billable": {"type": "boolean"},  # ICD10CM, ICD10PCS
    "code_no_dot": _KEYWORD,  # ICD10CM (E119, as in MIMIC)
}
"""Concept properties copied onto each document, for filtering; same names as
the node properties. A concept without the property leaves the field out."""

MAPPINGS: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "concept_id": _KEYWORD,  # icd10cm:E11.9, the Neo4j Concept.id
        "vocabulary": _KEYWORD,  # icd10cm
        "code": _KEYWORD,  # E11.9
        "kind": _KEYWORD,  # code, term, part, ...
        "name": {"type": "keyword", "ignore_above": 1024},  # the concept's name
        "origin": _KEYWORD,  # where `text` comes from: name, synonym, fsn, ...
        # text: analyzed, for BM25 / fuzzy matching
        # text.keyword: as published, for display and aggregations
        # text.exact: whole text ignoring case and accents, for exact-match boosts
        "text": {
            "type": "text",
            "analyzer": "en_folded",
            "fields": {
                "keyword": {
                    "type": "keyword",
                    "normalizer": "keyword_no_lower",
                    "ignore_above": 1024,
                },
                "exact": {
                    "type": "keyword",
                    "normalizer": "keyword_folded",
                    "ignore_above": 1024,
                },
            },
        },
        **CONCEPT_FIELDS,
    },
}
"""One document per (concept, text) of :mod:`clinical_graph.texts`."""
