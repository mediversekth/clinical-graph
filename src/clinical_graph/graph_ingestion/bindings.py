"""Cross-vocabulary bindings: ``MAPS_TO`` edges between the vocabulary graphs.

Also the associations (:class:`~clinical_graph.model.Association`, MED-RT's
``MAY_TREAT`` and the like): edges between vocabularies that are not bindings,
resolved the same way on both ends and written by the same command.

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
from typing import LiteralString, cast

from neo4j import Driver

from clinical_graph.graph_ingestion.connection import Neo4jSettings, connect
from clinical_graph.graph_ingestion.schema import CONCEPT_LABEL, LABELS
from clinical_graph.graph_ingestion.writer import (
    MAPS_TO,
    GraphWriter,
    WriteCounts,
    check_association_type,
)
from clinical_graph.model import (
    Association,
    Mapping,
    MappingEquivalence,
    PropertyValue,
    Vocabulary,
    vocabulary_of,
)
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


class _Resolver:
    """Resolve published codes (``<vocabulary>:<code>``) to concept ids, counting."""

    def __init__(
        self,
        readers: dict[Vocabulary, list[VocabularyReader]],
        counts: Counter[str],
        *,
        no_ancestor: bool,
    ) -> None:
        self.readers = readers
        self.counts = counts
        self.no_ancestor = no_ancestor
        self.unmatched: Counter[str] = Counter()

    def __call__(self, id_: str, end: str) -> tuple[str, str, str] | None:
        """``(concept id, how, published code)``, or ``None`` (counted)."""
        vocabulary = vocabulary_of(id_)
        if vocabulary not in self.readers:
            self.counts[f"skipped: {vocabulary} is not loaded"] += 1
            return None
        code = id_.split(":", 1)[1]
        found = _match(self.readers[vocabulary], vocabulary, code)
        if found is None:
            self.counts[f"skipped: {end} code not found"] += 1
            self.unmatched[f"{vocabulary}:{code}"] += 1
            return None
        if self.no_ancestor and found[1] == "ancestor":
            self.counts[f"skipped: {end} matches only a broader code"] += 1
            return None
        return found[0], found[1], code

    def log_unmatched(self) -> None:
        if self.unmatched:
            log.info(
                "%d codes matched nothing, e.g. %s",
                len(self.unmatched),
                ", ".join(c for c, _ in self.unmatched.most_common(15)),
            )


def resolve(
    mappings: Iterable[Mapping],
    readers: dict[Vocabulary, list[VocabularyReader]],
    counts: Counter[str],
    *,
    supplementary: bool = False,
) -> Iterator[Mapping]:
    """Resolve each mapping's target to a concept id; drop those that match none.

    A target resolved to a broader code (``ancestor``) gets equivalence
    ``wider``.

    Args:
        mappings: Mappings with the published target code in the id.
        readers: Reader per target vocabulary, see :func:`target_readers`.
        counts: Updated with ``match: <how>`` and ``skipped: <why>`` counts.
        supplementary: The reader is ``supplementary``: resolve the source as
            well (``source_code``, ``source_match``) and drop ``ancestor``
            matches on either end.
    """
    lookup = _Resolver(readers, counts, no_ancestor=supplementary)
    for m in mappings:
        extra: dict[str, PropertyValue] = {}
        source = m.source
        if supplementary:
            found_source = lookup(m.source, "source")
            if found_source is None:
                continue
            source, source_how, source_code = found_source
            extra = {"source_code": source_code, "source_match": source_how}
        found = lookup(m.target, "target")
        if found is None:
            continue
        target, how, code = found
        counts[f"match: {how}"] += 1
        yield dataclasses.replace(
            m,
            source=source,
            target=target,
            equivalence=MappingEquivalence.WIDER
            if how == "ancestor"
            else m.equivalence,
            properties={**m.properties, **extra, "target_code": code, "match": how},
        )
    lookup.log_unmatched()


def resolve_associations(
    associations: Iterable[Association],
    readers: dict[Vocabulary, list[VocabularyReader]],
    counts: Counter[str],
) -> Iterator[Association]:
    """Resolve both ends of each association; drop those that match no concept.

    An end that matches only a broader code is dropped too: a drug that treats a
    disease does not treat its whole parent. The edge records the published
    codes and how they matched (``source_code``, ``source_match``,
    ``target_code``, ``target_match``).
    """
    lookup = _Resolver(readers, counts, no_ancestor=True)
    for a in associations:
        source = lookup(a.source, "source")
        target = lookup(a.target, "target") if source is not None else None
        if source is None or target is None:
            continue
        counts[f"match: {source[1]} -> {target[1]}"] += 1
        yield dataclasses.replace(
            a,
            source=source[0],
            target=target[0],
            properties={
                **a.properties,
                "source_code": source[2],
                "source_match": source[1],
                "target_code": target[2],
                "target_match": target[1],
            },
        )
    lookup.log_unmatched()


def only_new(
    mappings: Iterable[Mapping], linked: set[frozenset[str]], counts: Counter[str]
) -> Iterator[Mapping]:
    """Drop mappings between two concepts that are linked already (either way).

    Args:
        mappings: Resolved mappings.
        linked: Pairs of concept ids already joined by ``MAPS_TO``; the pairs let
            through are added, so a pair is written once.
        counts: Updated with ``skipped: already linked``.
    """
    for m in mappings:
        pair = frozenset((m.source, m.target))
        if pair in linked:
            counts["skipped: already linked"] += 1
            continue
        linked.add(pair)
        yield m


def linked_pairs(
    driver: Driver, database: str, exclude: Iterable[str]
) -> set[frozenset[str]]:
    """Pairs of concepts joined by ``MAPS_TO`` edges of other provenances."""
    query = (
        f"MATCH (a:{CONCEPT_LABEL})-[r:{MAPS_TO}]->(b:{CONCEPT_LABEL}) "
        f"WHERE NOT r.provenance IN $exclude "
        f"RETURN a.id AS a, b.id AS b"
    )
    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        result = session.run(query, exclude=list(exclude))
        return {frozenset((str(r["a"]), str(r["b"]))) for r in result}


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


def delete_associations(
    driver: Driver, database: str, types: Iterable[str], provenances: Iterable[str]
) -> int:
    """Delete the association edges of some sources, by type and ``provenance``.

    Returns:
        The number of edges deleted.
    """
    deleted = 0
    for rel_type in types:
        check_association_type(rel_type)
        query = (
            f"MATCH (:{CONCEPT_LABEL})-[r:{rel_type}]->(:{CONCEPT_LABEL}) "
            f"WHERE r.provenance IN $provenances "
            f"CALL (r) {{ DELETE r }} IN TRANSACTIONS OF 10000 ROWS "
            f"RETURN count(r) AS n"
        )
        with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
            record = session.run(
                cast(LiteralString, query), provenances=list(provenances)
            ).single()
        deleted += int(record["n"]) if record else 0
    return deleted


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
    """Write the mappings of each source as ``MAPS_TO`` edges, and its associations.

    Args:
        source_keys: ``sources.toml`` keys whose mappings to write; default all.
        settings: Connection settings; default :meth:`Neo4jSettings.from_env`.
        batch_size: Rows per write transaction.
        replace: First delete the ``MAPS_TO`` and association edges of the
            source (its reader's ``provenances``), so rows dropped from a newer
            release go away; other sources' edges are kept.

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
            if mappings is None and not reader.association_types:
                continue
            counts: Counter[str] = Counter()
            writer = GraphWriter(driver, settings.database, batch_size)
            if mappings is not None:
                if replace and reader.provenances:
                    n = delete_mappings(driver, settings.database, reader.provenances)
                    log.info("[%s] deleted %d %s edges", key, n, MAPS_TO)
                resolved = resolve(
                    mappings, readers, counts, supplementary=reader.supplementary
                )
                if reader.supplementary:
                    linked = linked_pairs(driver, settings.database, reader.provenances)
                    resolved = only_new(resolved, linked, counts)
                writer.write_mappings(resolved)
            if reader.association_types:
                if replace:
                    n = delete_associations(
                        driver,
                        settings.database,
                        reader.association_types,
                        reader.provenances,
                    )
                    log.info("[%s] deleted %d association edges", key, n)
                writer.write_associations(
                    resolve_associations(reader.iter_associations(), readers, counts)
                )
            for name, n in sorted({**counts, **writer.counts.edges}.items()):
                log.info("[%s]   %-45s %9d", key, name, n)
            if writer.counts.skipped_edges:
                log.warning(
                    "[%s] %d edges skipped: endpoint not in Neo4j",
                    key,
                    writer.counts.skipped_edges,
                )
            results[key] = writer.counts
    return results


def dry_run_bind(source_keys: Iterable[str] | None = None) -> dict[str, dict[str, int]]:
    """Read and resolve the mappings and associations as :func:`bind` would.

    Without Neo4j.

    Returns:
        Per source key: resolved edges per ``<source label>-<TYPE>-><target
        label>``, ``match: <how>`` and ``skipped: <why>`` counts.
    """
    manifest = load_manifest()
    readers = target_readers(manifest)
    results: dict[str, dict[str, int]] = {}
    linked: set[frozenset[str]] = set()  # pairs written by the maps seen so far
    seen: set[str] = set()
    for key in source_keys or READERS:
        reader = READERS[key](manifest[key])
        mappings = _mappings(reader, key)
        if mappings is None and not reader.association_types:
            continue
        counts: Counter[str] = Counter()
        if mappings is not None:
            resolved = resolve(
                mappings, readers, counts, supplementary=reader.supplementary
            )
            if reader.supplementary:
                for other, cls in READERS.items():  # what bind would find in Neo4j
                    if other not in seen and other != key and not cls.supplementary:
                        linked |= _pairs(cls(manifest[other]), other, readers)
                resolved = only_new(resolved, linked, counts)
            for m in resolved:
                source = vocabulary_of(m.source)
                if not any(m.source in r.concept_ids for r in readers[source]):
                    counts["skipped: source concept not found"] += 1
                    continue
                linked.add(frozenset((m.source, m.target)))
                label = f"{LABELS[source]}-{MAPS_TO}->{LABELS[vocabulary_of(m.target)]}"
                counts[label] += 1
                if m.properties.get("active") is False:
                    counts[f"{label} (inactive)"] += 1
        for a in resolve_associations(reader.iter_associations(), readers, counts):
            source, target = vocabulary_of(a.source), vocabulary_of(a.target)
            counts[f"{LABELS[source]}-{a.type}->{LABELS[target]}"] += 1
        seen.add(key)
        if counts:
            results[key] = dict(sorted(counts.items()))
    return results


def _pairs(
    reader: VocabularyReader,
    key: str,
    readers: dict[Vocabulary, list[VocabularyReader]],
) -> set[frozenset[str]]:
    """The concept pairs a (non-supplementary) source's maps link, resolved."""
    mappings = _mappings(reader, key)
    if mappings is None:
        return set()
    resolved = resolve(mappings, readers, Counter())
    return {frozenset((m.source, m.target)) for m in resolved}
