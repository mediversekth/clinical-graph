"""Elasticsearch full-text indexes of the vocabulary concepts.

Everything about Elasticsearch lives here:

* :mod:`~clinical_graph.elastic.connection`: ``ELASTICSEARCH_*`` settings
* :mod:`~clinical_graph.elastic.mapping`: index and alias names, analyzer,
  document mapping
* :mod:`~clinical_graph.elastic.build`: one index per source release, filled
  from the readers; one filtered alias per vocabulary
* :mod:`~clinical_graph.elastic.search`: BM25 concept search, collapsed per
  concept

The documents are the texts of :mod:`clinical_graph.texts`, the same ones the
SapBERT embeddings have, and carry the Neo4j ``Concept.id`` as ``concept_id``.
"""

from clinical_graph.elastic.build import build, index_sources, source_indexes
from clinical_graph.elastic.connection import ElasticSettings, connect
from clinical_graph.elastic.mapping import PREFIX, alias_name, index_name
from clinical_graph.elastic.search import QueryOptions, build_query, search

__all__ = [
    "PREFIX",
    "ElasticSettings",
    "QueryOptions",
    "alias_name",
    "build",
    "build_query",
    "connect",
    "index_name",
    "index_sources",
    "search",
    "source_indexes",
]
