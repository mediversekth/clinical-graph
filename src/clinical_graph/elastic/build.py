"""Build the Elasticsearch indexes from the vocabulary readers.

One index per source release (``clinical_graph_<source>_<version>_<built>``)
holding a
document per (concept, text) of :mod:`clinical_graph.texts`, the same texts the
embeddings have. Searches go through one filtered alias per vocabulary
(``clinical_graph_<vocabulary>``): ``clinical_graph_icd10pcs`` is the
``icd10cm`` index filtered on ``vocabulary: icd10pcs``, and
``clinical_graph_snomed`` spans the International Edition's and the LOINC
Extension's indexes.

A build fills a new index, then in one atomic step points the aliases at it and
deletes the source's previous index, so searches never see a half-built index
and a release update leaves nothing behind.
"""

import logging
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk

from clinical_graph.elastic.connection import ElasticSettings, connect
from clinical_graph.elastic.mapping import (
    CONCEPT_FIELDS,
    MAPPINGS,
    PREFIX,
    SETTINGS,
    alias_name,
    index_name,
)
from clinical_graph.model import Concept
from clinical_graph.sources import load_manifest
from clinical_graph.texts import iter_concept_texts
from clinical_graph.vocabularies import READERS

log = logging.getLogger(__name__)


def index_sources() -> list[str]:
    """Keys of the readers whose concepts are indexed (not map-only sources)."""
    return [key for key, cls in READERS.items() if cls.vocabularies]


def source_indexes(es: Elasticsearch, source_key: str) -> dict[str, dict[str, Any]]:
    """Indexes built here for a source (any release): name -> ``_meta``."""
    found = es.indices.get_mapping(index=f"{PREFIX}*", allow_no_indices=True)
    indexes: dict[str, dict[str, Any]] = {}
    for name, body in found.body.items():
        meta: dict[str, Any] = body.get("mappings", {}).get("_meta", {})
        if meta.get("source") == source_key:
            indexes[name] = meta
    return indexes


def _documents(index: str, concepts: Iterable[Concept]) -> Iterator[dict[str, Any]]:
    """Bulk actions: one document per text of each indexed concept."""
    for concept, texts in iter_concept_texts(concepts):
        extra = {
            field: concept.properties[field]
            for field in CONCEPT_FIELDS
            if concept.properties.get(field) is not None
        }
        for i, text in enumerate(texts):
            yield {
                "_index": index,
                "_id": f"{concept.id}#{i}",
                "concept_id": concept.id,
                "vocabulary": str(concept.vocabulary),
                "code": concept.code,
                "kind": concept.kind,
                "name": concept.name,
                "origin": text.origin,
                "text": text.text,
                **extra,
            }


def build(
    source_key: str,
    *,
    settings: ElasticSettings | None = None,
    recreate: bool = False,
    chunk_size: int = 5_000,
) -> str:
    """Index the concepts of one source and point its vocabulary aliases at them.

    Args:
        source_key: ``sources.toml`` key of a vocabulary reader.
        settings: Connection settings; default :meth:`ElasticSettings.from_env`.
        recreate: Rebuild even if the source's current release is indexed.
        chunk_size: Documents per bulk request.

    Returns:
        The name of the index.

    Raises:
        ValueError: If ``source_key`` has no reader with vocabularies.
    """
    if source_key not in index_sources():
        raise ValueError(f"{source_key!r} has no concepts; known: {index_sources()}")
    source = load_manifest()[source_key]
    reader = READERS[source_key](source)
    built = datetime.now(UTC)
    index = index_name(source_key, source.version, built.strftime("%Y%m%dt%H%M%S"))
    aliases = [alias_name(v) for v in reader.vocabularies]

    with connect(settings) as es:
        current = source_indexes(es, source_key)
        for name, meta in current.items():
            if meta.get("version") == source.version and meta.get("complete"):
                if not recreate:
                    log.info("[%s] %s is up to date", source_key, name)
                    return name

        start = time.monotonic()
        meta = {
            "source": source_key,
            "version": source.version,
            "built": built.isoformat(timespec="seconds"),
            "complete": False,
        }
        es.indices.create(
            index=index,
            settings={**SETTINGS, "refresh_interval": "-1"},
            mappings={**MAPPINGS, "_meta": meta},
        )
        log.info("[%s] indexing into %s ...", source_key, index)
        n = 0
        for ok, item in streaming_bulk(
            es,
            _documents(index, reader.iter_concepts()),
            chunk_size=chunk_size,
            raise_on_error=True,
        ):
            n += ok
            if not ok:
                log.warning("[%s] not indexed: %s", source_key, item)
            elif n % 200_000 == 0:
                log.info("[%s] %d documents", source_key, n)
        es.indices.put_settings(index=index, settings={"refresh_interval": None})
        es.indices.refresh(index=index)
        es.indices.put_mapping(
            index=index,
            meta={**meta, "complete": True, "documents": n},
        )

        actions: list[dict[str, Any]] = [
            {
                "add": {
                    "index": index,
                    "alias": alias_name(vocabulary),
                    "filter": {"term": {"vocabulary": str(vocabulary)}},
                }
            }
            for vocabulary in reader.vocabularies
        ]
        old = list(current)  # earlier builds, and any left half-built
        actions += [{"remove_index": {"index": name}} for name in old]
        es.indices.update_aliases(actions=actions)
        log.info(
            "[%s] %d documents in %s, aliases %s%s, in %.0f s",
            source_key,
            n,
            index,
            ", ".join(aliases),
            f"; deleted {', '.join(old)}" if old else "",
            time.monotonic() - start,
        )
    return index
