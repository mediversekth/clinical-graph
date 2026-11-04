"""SapBERT embeddings of the vocabulary concepts.

Everything about embeddings lives here:

* :mod:`~clinical_graph.embeddings.texts`: which concepts are embedded and with
  which texts (name, synonyms, ...)
* :mod:`~clinical_graph.embeddings.encoder`: the SapBERT encoder
* :mod:`~clinical_graph.embeddings.store`: building them from the readers and
  saving them under ``processed/embeddings/sapbert/<source>/``
* :mod:`~clinical_graph.embeddings.graph`: loading the name vectors onto the
  Neo4j nodes, one vector index per vocabulary, and searching it
* :mod:`~clinical_graph.embeddings.search`: searching the saved embeddings,
  synonyms included

One model and one vector space for every vocabulary, so scores compare across
vocabularies; storage and indexes are per source and per vocabulary.
"""

from clinical_graph.embeddings.encoder import SAPBERT_MODEL, SapBertEncoder
from clinical_graph.embeddings.graph import (
    EMBEDDING_PROPERTY,
    index_name,
    load,
    search_graph,
)
from clinical_graph.embeddings.search import EmbeddingIndex
from clinical_graph.embeddings.store import (
    EmbeddingSet,
    build,
    embedding_sources,
    embeddings_dir,
)
from clinical_graph.embeddings.texts import Text, concept_texts, is_embedded, iter_texts

__all__ = [
    "EMBEDDING_PROPERTY",
    "SAPBERT_MODEL",
    "EmbeddingIndex",
    "EmbeddingSet",
    "SapBertEncoder",
    "Text",
    "build",
    "concept_texts",
    "embedding_sources",
    "embeddings_dir",
    "index_name",
    "is_embedded",
    "iter_texts",
    "load",
    "search_graph",
]
