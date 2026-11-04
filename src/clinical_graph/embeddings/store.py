"""Embeddings on disk, one folder per source.

``<data dir>/processed/embeddings/sapbert/<source key>/`` holds:

* ``texts.tsv``: ``concept_id``, ``origin``, ``text``; one row per embedded
  text (see :mod:`clinical_graph.texts`), a concept's rows together
  and its ``name`` row first
* ``vectors.npy``: float16, shape ``(rows, 768)``, row-aligned with
  ``texts.tsv``, L2-normalised
* ``info.json``: model, source key and release version, row and concept counts

Encoding is saved in chunks under ``chunks/`` while it runs, so a build that is
interrupted resumes where it stopped. A folder whose ``info.json`` names the
current model and release is up to date and not rebuilt.
"""

import csv
import json
import logging
import shutil
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from clinical_graph import paths
from clinical_graph.embeddings.encoder import SAPBERT_MODEL, SapBertEncoder
from clinical_graph.sources import load_manifest
from clinical_graph.texts import Text, iter_texts
from clinical_graph.vocabularies import READERS

log = logging.getLogger(__name__)

MODEL_FOLDER = "sapbert"
"""Folder of the SapBERT embeddings under ``processed/embeddings``."""

type HalfMatrix = np.ndarray[Any, np.dtype[np.float16]]


def embedding_sources() -> list[str]:
    """Keys of the readers whose concepts are embedded (not map-only sources)."""
    return [key for key, cls in READERS.items() if cls.vocabularies]


def embeddings_dir(source_key: str) -> Path:
    """Folder of a source's embeddings."""
    return paths.processed_dir() / "embeddings" / MODEL_FOLDER / source_key


def _write_texts(path: Path, texts: list[Text]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(["concept_id", "origin", "text"])
        writer.writerows((t.concept_id, t.origin, t.text) for t in texts)


def _read_texts(path: Path) -> list[Text]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = csv.reader(fh, delimiter="\t")
        next(rows)
        return [Text(cid, origin, text) for cid, origin, text in rows]


def _read_info(folder: Path) -> dict[str, Any] | None:
    path = folder / "info.json"
    return json.loads(path.read_text()) if path.is_file() else None


def build(
    source_key: str,
    *,
    batch_size: int = 256,
    chunk_size: int = 100_000,
    overwrite: bool = False,
    device: str | None = None,
) -> Path:
    """Embed the concepts of one source and save them to :func:`embeddings_dir`.

    Args:
        source_key: ``sources.toml`` key of a vocabulary reader.
        batch_size: Texts per forward pass.
        chunk_size: Rows per chunk saved while encoding.
        overwrite: Rebuild even if the folder is up to date.
        device: Torch device; default CUDA when available.

    Returns:
        The folder.

    Raises:
        ValueError: If ``source_key`` has no reader with vocabularies.
    """
    if source_key not in embedding_sources():
        raise ValueError(
            f"{source_key!r} has no concepts to embed; known: {embedding_sources()}"
        )
    source = load_manifest()[source_key]
    folder = embeddings_dir(source_key)
    info = _read_info(folder)
    if (
        info
        and not overwrite
        and info.get("model") == SAPBERT_MODEL
        and info.get("version") == source.version
    ):
        log.info("[%s] embeddings up to date in %s", source_key, folder)
        return folder
    if overwrite or info:  # forced, or built for another release / model
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    chunks = folder / "chunks"
    chunks.mkdir(exist_ok=True)
    texts_path = folder / "texts.tsv"

    start = time.monotonic()
    if texts_path.is_file() and any(chunks.iterdir()):
        log.info("[%s] resuming from %s", source_key, chunks)
        texts = _read_texts(texts_path)
    else:
        log.info("[%s] reading concepts ...", source_key)
        texts = list(iter_texts(READERS[source_key](source).iter_concepts()))
        _write_texts(texts_path, texts)
    n = len(texts)
    log.info("[%s] %d texts to embed", source_key, n)

    encoder: SapBertEncoder | None = None
    parts: list[Path] = []
    for i, first in enumerate(range(0, n, chunk_size)):
        part = chunks / f"part_{i:04d}.npy"
        parts.append(part)
        if part.is_file():
            continue
        encoder = encoder or SapBertEncoder(device=device)
        last = min(first + chunk_size, n)
        vectors = encoder.encode(
            [t.text for t in texts[first:last]], batch_size=batch_size
        )
        np.save(part, vectors.astype(np.float16))
        log.info("[%s] encoded %d / %d", source_key, last, n)

    matrix = np.concatenate([np.load(p) for p in parts])
    np.save(folder / "vectors.npy", matrix)
    info = {
        "model": SAPBERT_MODEL,
        "source": source_key,
        "version": source.version,
        "rows": n,
        "concepts": len({t.concept_id for t in texts}),
        "dimension": int(matrix.shape[1]),
        "dtype": "float16",
        "origins": dict(Counter(t.origin for t in texts).most_common()),
    }
    (folder / "info.json").write_text(json.dumps(info, indent=2) + "\n")
    shutil.rmtree(chunks)
    log.info(
        "[%s] saved %s to %s in %.0f s",
        source_key,
        matrix.shape,
        folder,
        time.monotonic() - start,
    )
    return folder


@dataclass(frozen=True, slots=True)
class EmbeddingSet:
    """The saved embeddings of one source.

    ``vectors`` is memory-mapped float16; convert slices as needed.
    """

    folder: Path
    info: dict[str, Any]
    texts: list[Text]
    vectors: HalfMatrix

    @classmethod
    def load(cls, source_key: str) -> "EmbeddingSet":
        """Load what :func:`build` saved for a source.

        Raises:
            FileNotFoundError: If the source has not been embedded.
        """
        folder = embeddings_dir(source_key)
        info = _read_info(folder)
        if info is None:
            raise FileNotFoundError(
                f"no embeddings in {folder}; run `clinical-graph embed build "
                f"{source_key}`"
            )
        texts = _read_texts(folder / "texts.tsv")
        vectors: HalfMatrix = np.load(folder / "vectors.npy", mmap_mode="r")
        if len(texts) != len(vectors):
            raise ValueError(f"{folder}: {len(texts)} texts, {len(vectors)} vectors")
        return cls(folder, info, texts, vectors)

    def name_rows(self) -> Iterator[tuple[str, int]]:
        """``(concept id, row)`` of each concept's ``name`` text."""
        for row, text in enumerate(self.texts):
            if text.origin == "name":
                yield text.concept_id, row
