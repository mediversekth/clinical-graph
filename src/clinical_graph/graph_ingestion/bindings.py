"""Cross-vocabulary bindings: ``MAPS_TO`` edges between the vocabulary graphs.

Readers yield :class:`~clinical_graph.model.Mapping` records whose target id holds
the code as the map publishes it. Before writing, each target is resolved with
the target vocabulary's reader (:meth:`VocabularyReader.match`), which can
normalise variant spellings or fall back to a broader code; the edge records
how (``match``: ``exact``, ``normalised``, ``ancestor``) and the published code
(``target_code``). Run after ``ingest``: endpoints must already be in Neo4j.
"""

import dataclasses
import logging
from collections import Counter
from collections.abc import Iterable, Iterator

from neo4j import Driver

from clinical_graph.graph_ingestion.connection import Neo4jSettings, connect
from clinical_graph.graph_ingestion.schema import CONCEPT_LABEL, LABELS
from clinical_graph.graph_ingestion.writer import MAPS_TO, GraphWriter, WriteCounts
from clinical_graph.model import Mapping, MappingEquivalence, Vocabulary, vocabulary_of
from clinical_graph.sources import load_manifest
from clinical_graph.sources.manifest import Source
from clinical_graph.vocabularies import READERS, VocabularyReader

log = logging.getLogger(__name__)


def target_readers(
    manifest: dict[str, Source],
) -> dict[Vocabulary, list[VocabularyReader]]:
    """The readers of each vocabulary loaded as a graph, to resolve map targets.

    A vocabulary can have several: SNOMED CT has the International Edition and
    the LOINC Extension.
    """
    readers: dict[Vocabulary, list[VocabularyReader]] = {}
    for key, cls in READERS.items():
        reader: VocabularyReader | None = None
        for vocabulary in cls.vocabularies:
            if vocabulary in LABELS:
                reader = reader or cls(manifest[key])
                readers.setdefault(vocabulary, []).append(reader)
    return readers


def _match(
    readers: list[VocabularyReader], vocabulary: Vocabulary, code: str
) -> tuple[str, str] | None:
    """The first reader's match of a code; an exact match wins over the others."""
    found = [m for r in readers if (m := r.match(vocabulary, code)) is not None]
    return next((m for m in found if m[1] == "exact"), found[0] if found else None)


def resolve(
    mappings: Iterable[Mapping],
    readers: dict[Vocabulary, list[VocabularyReader]],
    counts: Counter[str],
) -> Iterator[Mapping]:
    """Resolve each mapping's target to a concept id; drop those that match none.

    A target resolved to a broader code (``ancestor``) gets equivalence
    ``wider``.

    Args:
        mappings: Mappings with the published target code in the id.
        readers: Reader per target vocabulary, see :func:`target_readers`.
        counts: Updated with ``match: <how>`` and ``skipped: <why>`` counts.
    """
    unmatched: Counter[str] = Counter()
    for m in mappings:
        vocabulary = vocabulary_of(m.target)
        if vocabulary not in readers:
            counts[f"skipped: {vocabulary} is not loaded"] += 1
            continue
        code = m.target.split(":", 1)[1]
        found = _match(readers[vocabulary], vocabulary, code)
        if found is None:
            counts["skipped: target code not found"] += 1
            unmatched[code] += 1
            continue
        target, how = found
        counts[f"match: {how}"] += 1
        yield dataclasses.replace(
            m,
            target=target,
            equivalence=MappingEquivalence.WIDER
            if how == "ancestor"
            else m.equivalence,
            properties={**m.properties, "target_code": code, "match": how},
        )
    if unmatched:
        log.info(
            "%d target codes matched nothing, e.g. %s",
            len(unmatched),
            ", ".join(c for c, _ in unmatched.most_common(15)),
        )


def delete_mappings(driver: Driver, database: str, provenances: Iterable[str]) -> int:
    """Delete the ``MAPS_TO`` edges of some maps, by their ``provenance``.

    Returns:
        The number of edges deleted.
    """
    query = (
        f"MATCH (:{CONCEPT_LABEL})-[r:{MAPS_TO}]->(:{CONCEPT_LABEL}) "
        f"WHERE r.provenance IN $provenances "
        f"CALL (r) {{ DELETE r }} IN TRANSACTIONS OF 10000 ROWS "
        f"RETURN count(r) AS n"
    )
    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        record = session.run(query, provenances=list(provenances)).single()
    return int(record["n"]) if record else 0


def _mappings(reader: VocabularyReader, key: str) -> Iterator[Mapping] | None:
    try:
        return iter(reader.iter_mappings())
    except NotImplementedError:
        log.info("[%s] no mappings implemented, skipped", key)
        return None


def bind(
    source_keys: Iterable[str] | None = None,
    *,
    settings: Neo4jSettings | None = None,
    batch_size: int = 10_000,
    replace: bool = False,
) -> dict[str, WriteCounts]:
    """Write the mappings of each source as ``MAPS_TO`` edges.

    Args:
        source_keys: ``sources.toml`` keys whose mappings to write; default all.
        settings: Connection settings; default :meth:`Neo4jSettings.from_env`.
        batch_size: Rows per write transaction.
        replace: First delete the ``MAPS_TO`` edges of the source's maps (its
            reader's ``provenances``), so rows dropped from a newer release go
            away; other maps' edges are kept.

    Returns:
        Write counts per source key.
    """
    manifest = load_manifest()
    settings = settings or Neo4jSettings.from_env()
    readers = target_readers(manifest)
    results: dict[str, WriteCounts] = {}
    with connect(settings) as driver:
        for key in source_keys or READERS:
            reader = READERS[key](manifest[key])
            mappings = _mappings(reader, key)
            if mappings is None:
                continue
            if replace and reader.provenances:
                n = delete_mappings(driver, settings.database, reader.provenances)
                log.info("[%s] deleted %d %s edges", key, n, MAPS_TO)
            counts: Counter[str] = Counter()
            writer = GraphWriter(driver, settings.database, batch_size)
            writer.write_mappings(resolve(mappings, readers, counts))
            for name, n in sorted({**counts, **writer.counts.edges}.items()):
                log.info("[%s]   %-45s %9d", key, name, n)
            if writer.counts.skipped_edges:
                log.warning(
                    "[%s] %d mappings skipped: endpoint not in Neo4j",
                    key,
                    writer.counts.skipped_edges,
                )
            results[key] = writer.counts
    return results


def dry_run_bind(source_keys: Iterable[str] | None = None) -> dict[str, dict[str, int]]:
    """Read and resolve the mappings as :func:`bind` would, without Neo4j.

    Returns:
        Per source key: resolved edges per ``<source label>-MAPS_TO-><target
        label>``, ``match: <how>`` and ``skipped: <why>`` counts.
    """
    manifest = load_manifest()
    readers = target_readers(manifest)
    results: dict[str, dict[str, int]] = {}
    for key in source_keys or READERS:
        reader = READERS[key](manifest[key])
        mappings = _mappings(reader, key)
        if mappings is None:
            continue
        counts: Counter[str] = Counter()
        for m in resolve(mappings, readers, counts):
            source = vocabulary_of(m.source)
            if not any(m.source in r.concept_ids for r in readers[source]):
                counts["skipped: source concept not found"] += 1
                continue
            label = f"{LABELS[source]}-{MAPS_TO}->{LABELS[vocabulary_of(m.target)]}"
            counts[label] += 1
            if m.properties.get("active") is False:
                counts[f"{label} (inactive)"] += 1
        if counts:
            results[key] = dict(sorted(counts.items()))
    return results
