"""Embeddings in Neo4j: one vector per concept and one vector index per vocabulary.

Each embedded concept gets its ``name`` vector as the ``embedding`` property
(float32, via ``db.create.setNodeVectorProperty``: Community Edition cannot
store the ``VECTOR`` type). Each vocabulary label gets its own cosine vector
index, ``concept_embedding_<label>`` (``concept_embedding_loinc``), with
``kind`` as filter property; one index per label keeps a large vocabulary from
crowding a small one out of the top hits. Synonym vectors stay on disk
(:mod:`clinical_graph.embeddings.search` searches them).
"""

import logging
import time
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, LiteralString, cast

from neo4j import Driver, ManagedTransaction

from clinical_graph.embeddings.encoder import SapBertEncoder
from clinical_graph.embeddings.store import EmbeddingSet, embedding_sources
from clinical_graph.graph_ingestion.connection import Neo4jSettings, connect
from clinical_graph.graph_ingestion.schema import CONCEPT_LABEL, LABELS
from clinical_graph.model import Vocabulary, vocabulary_of
from clinical_graph.sources import load_manifest
from clinical_graph.vocabularies import READERS

log = logging.getLogger(__name__)

EMBEDDING_PROPERTY = "embedding"
"""Node property holding the concept's SapBERT vector."""


def index_name(vocabulary: Vocabulary) -> str:
    """Name of a vocabulary's vector index, e.g. ``concept_embedding_snomedct``."""
    return f"concept_embedding_{LABELS[vocabulary].lower()}"


def create_vector_index(
    driver: Driver, database: str, vocabulary: Vocabulary, dimension: int
) -> None:
    """Create a vocabulary's vector index if it does not exist, and wait for it."""
    query = (
        f"CREATE VECTOR INDEX {index_name(vocabulary)} IF NOT EXISTS "
        f"FOR (n:{LABELS[vocabulary]}) ON n.{EMBEDDING_PROPERTY} WITH [n.kind] "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dimension)}, "
        f"`vector.similarity_function`: 'cosine'}}}}"
    )
    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        session.run(cast(LiteralString, query)).consume()
        session.run("CALL db.awaitIndexes(3600)").consume()


def remove_embeddings(
    driver: Driver, database: str, vocabulary: Vocabulary, extension: str | None
) -> int:
    """Remove ``embedding`` from a vocabulary's nodes (of one extension, or none).

    Returns:
        The number of nodes that had one.
    """
    where = "n.extension = $extension" if extension else "n.extension IS NULL"
    query = (
        f"MATCH (n:{CONCEPT_LABEL}:{LABELS[vocabulary]}) "
        f"WHERE n.{EMBEDDING_PROPERTY} IS NOT NULL AND {where} "
        f"CALL (n) {{ REMOVE n.{EMBEDDING_PROPERTY} }} IN TRANSACTIONS OF 10000 ROWS "
        f"RETURN count(n) AS n"
    )
    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        record = session.run(cast(LiteralString, query), extension=extension).single()
    return int(record["n"]) if record else 0


def _write(
    driver: Driver, database: str, label: str, rows: list[dict[str, Any]]
) -> int:
    query = (
        f"UNWIND $rows AS row "
        f"MATCH (n:{CONCEPT_LABEL} {{id: row.id}}) WHERE n:{label} "
        f"CALL db.create.setNodeVectorProperty(n, '{EMBEDDING_PROPERTY}', row.vector) "
        f"RETURN count(n) AS n"
    )

    def work(tx: ManagedTransaction) -> int:
        record = tx.run(cast(LiteralString, query), rows=rows).single()
        return int(record["n"]) if record else 0

    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        return session.execute_write(work)


def _write_name_vectors(
    driver: Driver, database: str, data: EmbeddingSet, batch_size: int
) -> dict[str, int]:
    """Write each concept's name vector; counts per label and ``not found``."""
    counts: defaultdict[str, int] = defaultdict(int)
    buffers: defaultdict[Vocabulary, list[dict[str, Any]]] = defaultdict(list)

    def flush(vocabulary: Vocabulary) -> None:
        rows = buffers[vocabulary]
        written = _write(driver, database, LABELS[vocabulary], rows)
        counts[LABELS[vocabulary]] += written
        counts["not found"] += len(rows) - written
        rows.clear()

    for concept_id, row in data.name_rows():
        vocabulary = vocabulary_of(concept_id)
        vector = data.vectors[row].astype(float).tolist()
        buffers[vocabulary].append({"id": concept_id, "vector": vector})
        if len(buffers[vocabulary]) >= batch_size:
            flush(vocabulary)
    for vocabulary, rows in buffers.items():
        if rows:
            flush(vocabulary)
    return dict(counts)


def load(
    source_keys: Iterable[str] | None = None,
    *,
    settings: Neo4jSettings | None = None,
    batch_size: int = 2_000,
    replace: bool = False,
) -> dict[str, dict[str, int]]:
    """Write saved embeddings onto the concept nodes and create the indexes.

    Args:
        source_keys: Sources to load; default every embedded source.
        settings: Connection settings; default :meth:`Neo4jSettings.from_env`.
        batch_size: Nodes per write transaction.
        replace: First remove the ``embedding`` of the source's nodes, so
            concepts no longer embedded (retired since) lose theirs.

    Returns:
        Per source key, nodes written per label and ``"not found"``: embedded
        concepts with no node (the source is not ingested, or is older).
    """
    keys = list(source_keys or embedding_sources())
    manifest = load_manifest()
    settings = settings or Neo4jSettings.from_env()
    results: dict[str, dict[str, int]] = {}
    with connect(settings) as driver:
        for key in keys:
            start = time.monotonic()
            data = EmbeddingSet.load(key)
            if data.info["version"] != manifest[key].version:
                log.warning(
                    "[%s] embeddings are of release %s, sources.toml has %s",
                    key,
                    data.info["version"],
                    manifest[key].version,
                )
            reader = READERS[key]
            if replace:
                for vocabulary in reader.vocabularies:
                    n = remove_embeddings(
                        driver, settings.database, vocabulary, reader.extension
                    )
                    log.info(
                        "[%s] removed %d %s embeddings", key, n, LABELS[vocabulary]
                    )

            counts = _write_name_vectors(driver, settings.database, data, batch_size)
            for vocabulary in reader.vocabularies:
                create_vector_index(
                    driver, settings.database, vocabulary, int(data.info["dimension"])
                )
            log.info("[%s] %s in %.0f s", key, dict(counts), time.monotonic() - start)
            results[key] = counts
    return results


def search_graph(
    texts: list[str],
    vocabulary: Vocabulary,
    *,
    top_k: int = 10,
    kind: str | None = None,
    settings: Neo4jSettings | None = None,
    encoder: SapBertEncoder | None = None,
) -> list[list[dict[str, Any]]]:
    """Nearest concepts of one vocabulary to each text, by the Neo4j vector index.

    Matches the concepts' names only; :class:`~clinical_graph.embeddings.search.
    EmbeddingIndex` also matches their synonyms.

    Args:
        texts: Query texts.
        vocabulary: Whose index to search.
        top_k: Hits per text.
        kind: Only concepts of this ``kind`` (``term``, ``part``, ...).
        settings: Connection settings; default :meth:`Neo4jSettings.from_env`.
        encoder: A loaded encoder to reuse.

    Returns:
        Per text, ``{"id", "name", "kind", "score"}`` by descending score.
    """
    encoder = encoder or SapBertEncoder()
    vectors = encoder.encode(texts)
    settings = settings or Neo4jSettings.from_env()
    where = "WHERE n.kind = $kind " if kind else ""
    query = (
        f"CYPHER 25 MATCH (n:{LABELS[vocabulary]}) "
        f"SEARCH n IN (VECTOR INDEX {index_name(vocabulary)} FOR $vector "
        f"{where}LIMIT $k) SCORE AS score "
        f"RETURN n.id AS id, n.name AS name, n.kind AS kind, score "
        f"ORDER BY score DESC"
    )
    results: list[list[dict[str, Any]]] = []
    with connect(settings) as driver:
        session = driver.session(database=settings.database)  # pyright: ignore[reportUnknownMemberType]
        with session:
            for vector in vectors:
                records = session.run(
                    cast(LiteralString, query),
                    vector=vector.astype(float).tolist(),
                    k=top_k,
                    kind=kind,
                )
                results.append([r.data() for r in records])
    return results
