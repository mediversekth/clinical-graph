"""Read each source with its vocabulary reader and write it to Neo4j."""

import logging
import time
from collections import Counter
from collections.abc import Iterable
from typing import LiteralString, cast

from neo4j import Driver

from clinical_graph.graph_ingestion.connection import Neo4jSettings, connect
from clinical_graph.graph_ingestion.schema import CONCEPT_LABEL, LABELS, create_schema
from clinical_graph.graph_ingestion.writer import GraphWriter, WriteCounts
from clinical_graph.model import Vocabulary, vocabulary_of
from clinical_graph.sources import load_manifest
from clinical_graph.vocabularies import READERS

log = logging.getLogger(__name__)


def _vocabulary_sources() -> list[str]:
    """Keys of the readers that load a vocabulary graph (not map-only sources)."""
    return [key for key, cls in READERS.items() if cls.vocabularies]


def delete_vocabulary(
    driver: Driver,
    database: str,
    vocabulary: Vocabulary,
    extension: str | None = None,
) -> int:
    """Delete the nodes of one vocabulary graph and their relationships.

    Only nodes with both the ``Concept`` label and the vocabulary's label are
    touched; other data in the database is left alone.

    Args:
        driver: The Neo4j driver.
        database: The database name.
        vocabulary: Whose nodes to delete.
        extension: Delete only the nodes of this extension (``extension``
            property); ``None`` deletes only the nodes that belong to none, so
            replacing SNOMED CT keeps the LOINC Extension and vice versa.

    Returns:
        The number of nodes deleted.
    """
    label = LABELS[vocabulary]
    where = "n.extension = $extension" if extension else "n.extension IS NULL"
    query = (
        f"MATCH (n:{CONCEPT_LABEL}:{label}) WHERE {where} "
        f"CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF 10000 ROWS "
        f"RETURN count(n) AS n"
    )
    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        record = session.run(cast(LiteralString, query), extension=extension).single()
    return int(record["n"]) if record else 0


def ingest(
    source_keys: Iterable[str] | None = None,
    *,
    settings: Neo4jSettings | None = None,
    batch_size: int = 10_000,
    replace: bool = False,
) -> dict[str, WriteCounts]:
    """Load vocabulary graphs into Neo4j: nodes first, then their relations.

    Args:
        source_keys: ``sources.toml`` keys to load; default all with a reader.
        settings: Connection settings; default :meth:`Neo4jSettings.from_env`.
        batch_size: Rows per write transaction.
        replace: Delete each vocabulary's existing nodes first, so nothing from
            an older release is left behind. Without it, writes are MERGEs and
            only add or update.

    Returns:
        Write counts per source key.
    """
    keys = list(source_keys or _vocabulary_sources())
    unknown = [k for k in keys if k not in READERS]
    if unknown:
        raise ValueError(f"no reader for {unknown}; known: {sorted(READERS)}")
    manifest = load_manifest()
    settings = settings or Neo4jSettings.from_env()

    results: dict[str, WriteCounts] = {}
    with connect(settings) as driver:
        create_schema(driver, settings.database)
        for key in keys:
            reader = READERS[key](manifest[key])
            if replace:
                for vocabulary in reader.vocabularies:
                    n = delete_vocabulary(
                        driver, settings.database, vocabulary, reader.extension
                    )
                    log.info("[%s] deleted %d %s nodes", key, n, LABELS[vocabulary])

            writer = GraphWriter(driver, settings.database, batch_size)
            start = time.monotonic()
            log.info("[%s] writing concepts ...", key)
            writer.write_concepts(reader.iter_concepts())
            log.info("[%s] nodes: %s", key, dict(writer.counts.nodes))
            log.info("[%s] writing relations ...", key)
            writer.write_relations(reader.iter_relations())
            for rel, n in sorted(writer.counts.edges.items()):
                log.info("[%s]   %-45s %9d", key, rel, n)
            if writer.counts.skipped_edges:
                log.warning(
                    "[%s] %d relations skipped: endpoint not found",
                    key,
                    writer.counts.skipped_edges,
                )
            log.info("[%s] done in %.0f s", key, time.monotonic() - start)
            results[key] = writer.counts
    return results


def dry_run(source_keys: Iterable[str] | None = None) -> dict[str, dict[str, int]]:
    """Read the sources as :func:`ingest` would, without Neo4j, and count.

    Returns:
        Per source key, ``{"nodes:<label>": n, "<label>:<TYPE>": n, ...}``.

    Raises:
        ValueError: If a relation joins two vocabularies.
    """
    manifest = load_manifest()
    results: dict[str, dict[str, int]] = {}
    for key in source_keys or _vocabulary_sources():
        reader = READERS[key](manifest[key])
        counts: Counter[str] = Counter()
        ids: set[str] = set()
        if reader.extension:  # its edges also join the base vocabulary's nodes
            for cls in READERS.values():
                if cls.extension is None and set(cls.vocabularies) & set(
                    reader.vocabularies
                ):
                    ids |= cls(manifest[cls.source_key]).concept_ids
        for concept in reader.iter_concepts():
            counts[f"nodes:{LABELS[concept.vocabulary]}"] += 1
            ids.add(concept.id)
        for rel in reader.iter_relations():
            vocabulary = vocabulary_of(rel.source)
            if vocabulary_of(rel.target) is not vocabulary:
                raise ValueError(f"{rel.type} joins vocabularies: {rel}")
            if rel.source not in ids or rel.target not in ids:
                counts["skipped (endpoint not found)"] += 1
            else:
                retired = rel.properties.get("active") is False
                suffix = " (inactive)" if retired else ""
                counts[f"{LABELS[vocabulary]}:{rel.type}{suffix}"] += 1
        results[key] = dict(sorted(counts.items()))
    return results
