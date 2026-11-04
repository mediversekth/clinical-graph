"""SapBERT text encoder.

SapBERT was trained with the ``[CLS]`` token as the embedding (not mean
pooling), so that is what :class:`SapBertEncoder` returns, L2-normalised: the
dot product of two vectors is their cosine similarity.
"""

import logging
import os
from collections.abc import Sequence
from typing import Any

# The tokenizers' own threads warn (and can deadlock) after a fork; set before
# tokenizers are first used, keeping a value exported in the shell.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from transformers import AutoModel, AutoTokenizer  # noqa: E402

log = logging.getLogger(__name__)

SAPBERT_MODEL = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
"""HuggingFace id of the SapBERT checkpoint used for every vocabulary."""

MAX_LENGTH = 128
"""Tokens per text; longer texts (a few RxNorm packs) are truncated."""

type FloatMatrix = np.ndarray[Any, np.dtype[np.float32]]


class SapBertEncoder:
    """Encode texts with SapBERT on the GPU if there is one.

    Example::

        encoder = SapBertEncoder()
        vectors = encoder.encode(["type 2 diabetes", "HbA1c"])  # (2, 768)
    """

    def __init__(
        self,
        model_name: str = SAPBERT_MODEL,
        device: str | None = None,
        max_length: int = MAX_LENGTH,
    ) -> None:
        """Load the tokenizer and model.

        Args:
            model_name: HuggingFace model id.
            device: ``"cuda"``, ``"cpu"``, ...; default CUDA when available.
            max_length: Tokens per text.
        """
        self.model_name = model_name
        self.max_length = max_length
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        log.info("loading %s on %s", model_name, self.device)
        self.tokenizer: Any = AutoTokenizer.from_pretrained(model_name)  # pyright: ignore[reportUnknownMemberType]
        self.model: Any = AutoModel.from_pretrained(model_name)  # pyright: ignore[reportUnknownMemberType]
        self.model.to(self.device).eval()  # pyright: ignore[reportUnknownMemberType]

    @property
    def dimension(self) -> int:
        """Length of the vectors."""
        return int(self.model.config.hidden_size)

    def encode(self, texts: Sequence[str], batch_size: int = 256) -> FloatMatrix:
        """Encode texts into L2-normalised ``[CLS]`` vectors.

        Texts are batched by length, so batches carry little padding; the rows
        of the result are in the order of ``texts``.

        Args:
            texts: The texts.
            batch_size: Texts per forward pass.

        Returns:
            Float32 matrix of shape ``(len(texts), dimension)``.
        """
        out = np.empty((len(texts), self.dimension), dtype=np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        with torch.inference_mode():
            for start in range(0, len(order), batch_size):
                rows = order[start : start + batch_size]
                batch = self.tokenizer(
                    [texts[i] for i in rows],
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                ).to(self.device)
                cls = self.model(**batch).last_hidden_state[:, 0]
                cls = torch.nn.functional.normalize(cls, dim=1)
                out[rows] = cls.float().cpu().numpy()
        return out
