"""Batched, idempotent writes of concepts and relations.

Nodes are MERGEd on ``Concept.id``; relationships on their endpoints, type and
``Relation.key``. Running an ingestion twice therefore changes nothing.

:meth:`GraphWriter.write_relations` writes an edge only when both endpoints carry
the *same* vocabulary label, so no relation can join two vocabulary graphs.
Bindings between vocabularies go through :meth:`GraphWriter.write_mappings`
instead, as ``MAPS_TO`` edges MERGEd on ``provenance`` and ``id`` (the mapping's
key), and only between *different* vocabulary labels. Either way, records whose
endpoints do not exist are skipped by the ``MATCH`` (and counted as skipped).
"""

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, LiteralString, cast

from neo4j import Driver, ManagedTransaction

from clinical_graph.graph_ingestion.schema import CONCEPT_LABEL, LABELS
from clinical_graph.model import Concept, Mapping, Relation, Vocabulary, vocabulary_of

log = logging.getLogger(__name__)

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_REL_TYPE = re.compile(r"^[A-Z][A-Z0-9_]*$")

type Row = dict[str, Any]

MAPS_TO = "MAPS_TO"
"""Relationship type of every cross-vocabulary binding."""


def _label(vocabulary: Vocabulary) -> str:
    try:
        return LABELS[vocabulary]
    except KeyError:
        raise ValueError(f"{vocabulary} is not loaded as a graph") from None


def concept_row(concept: Concept) -> Row:
    """Neo4j parameters of one concept: its id and the properties to SET."""
    props: dict[str, Any] = {
        **concept.properties,
        "id": concept.id,
        "vocabulary": str(concept.vocabulary),
        "code": concept.code,
        "name": concept.name,
        "kind": concept.kind,
        "active": concept.active,
        "synonyms": list(concept.synonyms),
    }
    return {"id": concept.id, "props": props}


@dataclass
class WriteCounts:
    """How many records were sent and how many edges were created or matched."""

    nodes: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    edges: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped_edges: int = 0


class GraphWriter:
    """Write concepts and relations to Neo4j in batches."""

    def __init__(self, driver: Driver, database: str, batch_size: int = 10_000):
        """Bind the writer to a database.

        Args:
            driver: An open Neo4j driver.
            database: The database to write to.
            batch_size: Rows per ``UNWIND`` transaction.
        """
        self.driver = driver
        self.database = database
        self.batch_size = batch_size
        self.counts = WriteCounts()

    def _run(self, query: str, rows: list[Row]) -> int:
        """Run one ``UNWIND $rows`` write; returns the query's ``n``."""

        def work(tx: ManagedTransaction) -> int:
            record = tx.run(cast(LiteralString, query), rows=rows).single()
            return int(record["n"]) if record else 0

        with self.driver.session(database=self.database) as session:  # pyright: ignore[reportUnknownMemberType]
            return session.execute_write(work)

    def write_concepts(self, concepts: Iterable[Concept]) -> None:
        """MERGE concepts, labelled ``Concept`` plus their vocabulary label."""
        buffers: defaultdict[Vocabulary, list[Row]] = defaultdict(list)
        for concept in concepts:
            buffer = buffers[concept.vocabulary]
            buffer.append(concept_row(concept))
            if len(buffer) >= self.batch_size:
                self._flush_concepts(concept.vocabulary, buffer)
        for vocabulary, buffer in buffers.items():
            self._flush_concepts(vocabulary, buffer)

    def _flush_concepts(self, vocabulary: Vocabulary, buffer: list[Row]) -> None:
        if not buffer:
            return
        label = _label(vocabulary)
        query = (
            f"UNWIND $rows AS row "
            f"MERGE (n:{CONCEPT_LABEL} {{id: row.id}}) "
            f"SET n:{label}, n += row.props "
            f"RETURN count(n) AS n"
        )
        self.counts.nodes[label] += self._run(query, buffer)
        buffer.clear()

    def write_relations(self, relations: Iterable[Relation]) -> None:
        """MERGE relations between concepts of the same vocabulary.

        Raises:
            ValueError: If a relation joins two vocabularies, or its type or key
                names are not valid Neo4j identifiers.
        """
        buffers: defaultdict[tuple[Vocabulary, str, tuple[str, ...]], list[Row]] = (
            defaultdict(list)
        )
        for rel in relations:
            vocabulary = vocabulary_of(rel.source)
            if vocabulary_of(rel.target) is not vocabulary:
                raise ValueError(
                    f"{rel.type} joins two vocabularies: {rel.source} -> {rel.target}"
                )
            group = (vocabulary, rel.type, tuple(sorted(rel.key)))
            buffer = buffers[group]
            buffer.append(
                {
                    "source": rel.source,
                    "target": rel.target,
                    "key": rel.key,
                    "props": rel.properties,
                }
            )
            if len(buffer) >= self.batch_size:
                self._flush_relations(*group, buffer)
        for group, buffer in buffers.items():
            self._flush_relations(*group, buffer)

    def _flush_relations(
        self,
        vocabulary: Vocabulary,
        rel_type: str,
        key_names: tuple[str, ...],
        buffer: list[Row],
    ) -> None:
        if not buffer:
            return
        if not _REL_TYPE.match(rel_type):
            raise ValueError(f"invalid relationship type {rel_type!r}")
        if not all(_NAME.match(k) for k in key_names):
            raise ValueError(f"invalid relationship key names {key_names!r}")
        label = _label(vocabulary)
        key = ", ".join(f"{k}: row.key.{k}" for k in key_names)
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{CONCEPT_LABEL} {{id: row.source}}) WHERE a:{label} "
            f"MATCH (b:{CONCEPT_LABEL} {{id: row.target}}) WHERE b:{label} "
            f"MERGE (a)-[r:{rel_type}{' {' + key + '}' if key else ''}]->(b) "
            f"SET r += row.props "
            f"RETURN count(r) AS n"
        )
        written = self._run(query, buffer)
        self.counts.edges[f"{label}:{rel_type}"] += written
        self.counts.skipped_edges += len(buffer) - written
        buffer.clear()

    def write_mappings(self, mappings: Iterable[Mapping]) -> None:
        """MERGE ``MAPS_TO`` edges between concepts of two different vocabularies.

        Raises:
            ValueError: If a mapping joins two concepts of the same vocabulary.
        """
        buffers: defaultdict[tuple[Vocabulary, Vocabulary], list[Row]] = defaultdict(
            list
        )
        for m in mappings:
            group = (vocabulary_of(m.source), vocabulary_of(m.target))
            if group[0] is group[1]:
                raise ValueError(f"mapping within one vocabulary: {m}")
            buffer = buffers[group]
            buffer.append(
                {
                    "source": m.source,
                    "target": m.target,
                    "provenance": m.provenance,
                    "id": m.key or "",
                    "props": {**m.properties, "equivalence": str(m.equivalence)},
                }
            )
            if len(buffer) >= self.batch_size:
                self._flush_mappings(*group, buffer)
        for group, buffer in buffers.items():
            self._flush_mappings(*group, buffer)

    def _flush_mappings(
        self, source: Vocabulary, target: Vocabulary, buffer: list[Row]
    ) -> None:
        if not buffer:
            return
        a_label, b_label = _label(source), _label(target)
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{CONCEPT_LABEL} {{id: row.source}}) WHERE a:{a_label} "
            f"MATCH (b:{CONCEPT_LABEL} {{id: row.target}}) WHERE b:{b_label} "
            f"MERGE (a)-[r:{MAPS_TO} {{provenance: row.provenance, id: row.id}}]->(b) "
            f"SET r += row.props "
            f"RETURN count(r) AS n"
        )
        written = self._run(query, buffer)
        self.counts.edges[f"{a_label}-{MAPS_TO}->{b_label}"] += written
        self.counts.skipped_edges += len(buffer) - written
        buffer.clear()
