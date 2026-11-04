"""Full-text concept search over the vocabulary aliases.

Ported from mediverse's ES retrieval: BM25 over every text of a concept, an
optional boost for the query as a phrase and for an exact (case- and
accent-insensitive) match, and hits collapsed on ``concept_id`` so each concept
appears once, ranked by its best text.
"""

from dataclasses import dataclass
from typing import Any

from elasticsearch import Elasticsearch

from clinical_graph.elastic.connection import connect
from clinical_graph.elastic.mapping import alias_name
from clinical_graph.model import Vocabulary


@dataclass(frozen=True)
class QueryOptions:
    """How a query is matched against the texts.

    Attributes:
        fuzziness: Typo tolerance, e.g. ``"AUTO"`` (``None``: off).
        operator: ``"or"`` (any query word) or ``"and"`` (every word).
        minimum_should_match: e.g. ``"75%"``; with ``operator="or"`` only.
        phrase_boost: Extra score for texts containing the query as a phrase.
        exact_boost: Extra score for texts equal to the query.
    """

    fuzziness: str | None = None
    operator: str = "or"
    minimum_should_match: str | None = None
    phrase_boost: float = 0.0
    exact_boost: float = 0.0


def build_query(
    text: str,
    options: QueryOptions | None = None,
    filters: dict[str, Any] | None = None,
    span: str | None = None,
) -> dict[str, Any]:
    """The ``query`` body for one search.

    Args:
        text: Text for the scored match (a span, possibly with context words).
        options: Matching options.
        filters: Exact field values to keep, e.g. ``{"kind": "term"}``.
        span: Text for the phrase / exact boosts; default ``text``. Pass the
            span alone when ``text`` carries context, so a text equal to the
            span still wins over context-word matches.
    """
    options = options or QueryOptions()
    span = span or text
    match: dict[str, Any] = {"query": text, "operator": options.operator}
    if options.fuzziness:
        match["fuzziness"] = options.fuzziness
    if options.minimum_should_match and options.operator == "or":
        match["minimum_should_match"] = options.minimum_should_match
    should: list[dict[str, Any]] = []
    if options.phrase_boost:
        should.append(
            {"match_phrase": {"text": {"query": span, "boost": options.phrase_boost}}}
        )
    if options.exact_boost:
        should.append(
            {"term": {"text.exact": {"value": span, "boost": options.exact_boost}}}
        )
    return {
        "bool": {
            "must": [{"match": {"text": match}}],
            "should": should,
            "filter": [{"term": {k: v}} for k, v in (filters or {}).items()],
        }
    }


def search(
    texts: list[str],
    vocabulary: Vocabulary,
    *,
    top_k: int = 10,
    options: QueryOptions | None = None,
    filters: dict[str, Any] | None = None,
    es: Elasticsearch | None = None,
) -> list[list[dict[str, Any]]]:
    """Best-matching concepts of one vocabulary for each text.

    Args:
        texts: Query texts.
        vocabulary: Which alias to search.
        top_k: Distinct concepts per text.
        options: Matching options.
        filters: Exact field values to keep (``kind``, ``semantic_tag``,
            ``billable``, ...).
        es: An open client to reuse; default a new one from the environment.

    Returns:
        Per text, ``{"id", "text", "origin", "name", "score"}`` in score order,
        ``text`` being the concept's best-matching text.
    """
    client = es or connect()
    try:
        results: list[list[dict[str, Any]]] = []
        for text in texts:
            response = client.search(
                index=alias_name(vocabulary),
                query=build_query(text, options, filters),
                collapse={"field": "concept_id"},
                size=top_k,
                source_includes=["concept_id", "text", "origin", "name"],
            )
            results.append(
                [
                    {
                        "id": hit["_source"]["concept_id"],
                        "text": hit["_source"]["text"],
                        "origin": hit["_source"]["origin"],
                        "name": hit["_source"]["name"],
                        "score": hit["_score"],
                    }
                    for hit in response["hits"]["hits"]
                ]
            )
        return results
    finally:
        if es is None:
            client.close()
