"""Nearest-concept search over the saved embeddings, synonyms included.

Every text of a concept (name, synonyms, ...) is a row; a query keeps the
best-scoring row per concept. This finds a concept by any of its names, which
the Neo4j index (names only, :func:`~clinical_graph.embeddings.graph.
search_graph`) cannot.
"""

from typing import Any, cast

import numpy as np
import torch

from clinical_graph.embeddings.encoder import FloatMatrix, SapBertEncoder
from clinical_graph.embeddings.store import EmbeddingSet, HalfMatrix
from clinical_graph.embeddings.texts import Text
from clinical_graph.model import Vocabulary, vocabulary_of
from clinical_graph.vocabularies import READERS


def _tensor(array: FloatMatrix) -> torch.Tensor:
    """A float32 array as a tensor sharing its memory."""
    return torch.from_numpy(array)  # pyright: ignore[reportUnknownMemberType]


def _rows[T](tensor: torch.Tensor, _: type[T]) -> list[list[T]]:
    """A 2-d tensor as nested lists of ``T``."""
    return cast(list[list[T]], tensor.tolist())  # pyright: ignore[reportUnknownMemberType]


class EmbeddingIndex:
    """The saved embeddings of one vocabulary, with top-k search.

    The vectors are not copied into memory: they stay memory-mapped float16
    files and are scored in chunks of :data:`ROW_CHUNK` rows. The operating
    system keeps the file in its page cache once, shared by every process that
    searches it; a process itself holds the texts and a few hundred MB while
    scoring.

    Example::

        index = EmbeddingIndex.load(Vocabulary.LOINC)
        hits = index.search(["hemoglobin a1c", "serum sodium"], top_k=5)
    """

    ROW_CHUNK = 32_768
    """Rows converted to float32 and scored at a time."""

    def __init__(self, texts: list[Text], segments: list[HalfMatrix]) -> None:
        """Wrap texts and the row-aligned L2-normalised vectors.

        Args:
            texts: One per row, over all segments in order.
            segments: Vector matrices (memory-mapped or not), one after another.
        """
        n = sum(len(s) for s in segments)
        if len(texts) != n:
            raise ValueError(f"{len(texts)} texts, {n} vectors")
        self.texts = texts
        self.segments = segments
        self._encoder: SapBertEncoder | None = None

    def __len__(self) -> int:
        """Number of rows (texts)."""
        return len(self.texts)

    @classmethod
    def load(cls, vocabulary: Vocabulary) -> "EmbeddingIndex":
        """Map the rows of one vocabulary from every source that embeds it.

        SNOMED CT gets the International Edition and the LOINC Extension. A
        source's rows of one vocabulary are consecutive, so they are a view of
        the memory-mapped file, not a copy.

        Raises:
            FileNotFoundError: If a source of the vocabulary is not embedded.
        """
        texts: list[Text] = []
        segments: list[HalfMatrix] = []
        for key, reader in READERS.items():
            if vocabulary not in reader.vocabularies:
                continue
            data = EmbeddingSet.load(key)
            rows = [
                i
                for i, t in enumerate(data.texts)
                if vocabulary_of(t.concept_id) is vocabulary
            ]
            if not rows:
                continue
            texts += [data.texts[i] for i in rows]
            first, last = rows[0], rows[-1] + 1
            consecutive = last - first == len(rows)
            segments.append(
                data.vectors[first:last] if consecutive else data.vectors[rows]
            )
        if not segments:
            raise ValueError(f"no source embeds {vocabulary}")
        return cls(texts, segments)

    def encode(self, texts: list[str]) -> FloatMatrix:
        """Encode queries with SapBERT (loaded on first use)."""
        self._encoder = self._encoder or SapBertEncoder()
        return self._encoder.encode(texts)

    def search(self, texts: list[str], top_k: int = 10) -> list[list[dict[str, Any]]]:
        """Top-k concepts for each query text, by cosine similarity.

        Returns:
            Per query, ``{"id", "text", "origin", "score"}`` by descending
            score, where ``text`` is the concept's best-matching text.
        """
        return self.search_vectors(self.encode(texts), top_k)

    def search_vectors(
        self, queries: FloatMatrix, top_k: int = 10, query_batch_size: int = 1024
    ) -> list[list[dict[str, Any]]]:
        """Like :meth:`search`, for L2-normalised query vectors.

        Every chunk of rows is read once per batch of queries, so large batches
        are much faster per query; memory while scoring is about
        ``ROW_CHUNK * (768 + query_batch_size) * 4`` bytes. Runs on the CPU:
        the vectors stay in the shared page cache instead of a private copy.
        """
        # A concept has several rows: over-fetch before collapsing to concepts
        n_rows = min(top_k * 10, len(self))
        results: list[list[dict[str, Any]]] = []
        with torch.inference_mode():
            for b in range(0, len(queries), query_batch_size):
                batch = _tensor(
                    np.ascontiguousarray(
                        queries[b : b + query_batch_size], dtype=np.float32
                    )
                )
                scores, rows = self._top_rows(batch, n_rows)
                for score_list, row_list in zip(
                    _rows(scores, float), _rows(rows, int), strict=True
                ):
                    results.append(self._collapse(row_list, score_list, top_k))
        return results

    def _top_rows(
        self, batch: torch.Tensor, n_rows: int
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """The ``n_rows`` best rows for each query (row of ``batch``).

        Keeps the best rows of every chunk, then the best of those.

        Returns:
            Scores and row numbers, both ``(queries, n_rows)``, best first.
        """
        scores: list[torch.Tensor] = []
        rows: list[torch.Tensor] = []
        offset = 0
        for segment in self.segments:
            for start in range(0, len(segment), self.ROW_CHUNK):
                end = start + self.ROW_CHUNK
                chunk = _tensor(np.asarray(segment[start:end], np.float32))
                k = min(n_rows, len(chunk))
                top = torch.topk(batch @ chunk.T, k, dim=1)
                scores.append(top.values)
                rows.append(top.indices + offset + start)
            offset += len(segment)
        all_scores, all_rows = torch.cat(scores, dim=1), torch.cat(rows, dim=1)
        best = torch.topk(all_scores, n_rows, dim=1)
        return best.values, torch.gather(all_rows, 1, best.indices)

    def _collapse(
        self, rows: list[int], scores: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        """Keep the best row per concept, up to ``top_k`` concepts."""
        seen: set[str] = set()
        hits: list[dict[str, Any]] = []
        for row, score in zip(rows, scores, strict=True):
            text = self.texts[row]
            if text.concept_id in seen:
                continue
            seen.add(text.concept_id)
            hits.append(
                {
                    "id": text.concept_id,
                    "text": text.text,
                    "origin": text.origin,
                    "score": score,
                }
            )
            if len(hits) == top_k:
                break
        return hits
