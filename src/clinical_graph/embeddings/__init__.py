"""SapBERT embeddings of the vocabulary concepts.

Everything about embeddings lives here:

* :mod:`~clinical_graph.embeddings.encoder`: the SapBERT encoder
* :mod:`~clinical_graph.embeddings.store`: building them from the readers and
  saving them under ``processed/embeddings/sapbert/<source>/``
* :mod:`~clinical_graph.embeddings.graph`: loading the name vectors onto the
  Neo4j nodes, one vector index per vocabulary, and searching it
* :mod:`~clinical_graph.embeddings.search`: searching the saved embeddings,
  synonyms included

Which concepts and texts are embedded is decided in :mod:`clinical_graph.texts`,
shared with the Elasticsearch indexes. One model and one vector space for every
vocabulary, so scores compare across vocabularies; storage and indexes are per
source and per vocabulary.
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

__all__ = [
    "EMBEDDING_PROPERTY",
    "SAPBERT_MODEL",
    "EmbeddingIndex",
    "EmbeddingSet",
    "SapBertEncoder",
    "build",
    "embedding_sources",
    "embeddings_dir",
    "index_name",
    "load",
    "search_graph",
]
