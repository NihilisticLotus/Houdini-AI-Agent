"""Local text embedding with character n-gram fallback.

Provides cosine-similarity based vector search for memory retrieval.
When numpy is available, uses proper float32 arrays; otherwise falls back
to pure-Python list-based computation with acceptable performance for
small-to-medium memory stores.
"""

from __future__ import annotations

import math
import struct
import threading
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

# Try numpy for faster computation
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Character n-gram embedding
# ---------------------------------------------------------------------------

_NGRAM_SIZE = 3


def _char_ngrams(text: str, n: int = _NGRAM_SIZE) -> List[str]:
    """Extract character n-grams from text."""
    text = f"^{text.lower().strip()}$"
    if len(text) < n:
        return [text]
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def _build_vocab(texts: List[str], n: int = _NGRAM_SIZE) -> Dict[str, int]:
    """Build a vocabulary index from all texts."""
    counter: Counter = Counter()
    for text in texts:
        counter.update(_char_ngrams(text, n))
    # Keep n-grams that appear at least once
    return {gram: idx for idx, (gram, _) in enumerate(counter.most_common())}


def embed_text(text: str, vocab: Optional[Dict[str, int]] = None) -> List[float]:
    """Create a TF-IDF-like vector for a text using character n-grams.

    If vocab is None, creates a simple TF vector from the text alone.
    """
    ngrams = _char_ngrams(text)
    if not ngrams:
        return []

    if vocab is not None:
        dim = len(vocab)
        vec = [0.0] * dim
        for gram in ngrams:
            idx = vocab.get(gram)
            if idx is not None:
                vec[idx] += 1.0
    else:
        # Fallback: use gram index as-is
        gram_set = sorted(set(ngrams))
        dim = len(gram_set)
        gram_idx = {g: i for i, g in enumerate(gram_set)}
        vec = [0.0] * dim
        for gram in ngrams:
            vec[gram_idx[gram]] += 1.0

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def embed_texts(texts: List[str]) -> Tuple[List[List[float]], Dict[str, int]]:
    """Embed multiple texts using a shared vocabulary.

    Returns (vectors, vocabulary).
    """
    vocab = _build_vocab(texts)
    vectors = [embed_text(text, vocab) for text in texts]
    return vectors, vocab


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def vector_to_bytes(vec: List[float]) -> bytes:
    """Serialize a float vector to bytes."""
    return struct.pack(f"{len(vec)}f", *vec)


def bytes_to_vector(data: bytes) -> List[float]:
    """Deserialize bytes to a float vector."""
    count = len(data) // 4
    return list(struct.unpack(f"{count}f", data))


# ---------------------------------------------------------------------------
# LocalEmbedder class
# ---------------------------------------------------------------------------

class LocalEmbedder:
    """Local text embedder using character n-grams with TF-IDF weighting.

    Usage:
        embedder = LocalEmbedder()
        vec = embedder.embed("create a box node in /obj")
        similar = embedder.search(vec, memory_store)
    """

    def __init__(self) -> None:
        self._vocab: Optional[Dict[str, int]] = None
        self._idf: Optional[Dict[str, float]] = None
        self._doc_count = 0

    def fit(self, texts: List[str]) -> None:
        """Build vocabulary and IDF weights from a corpus."""
        if not texts:
            return
        self._vocab = _build_vocab(texts)
        # Compute IDF
        doc_freq: Counter = Counter()
        for text in texts:
            seen = set(_char_ngrams(text))
            for gram in seen:
                doc_freq[gram] += 1
        self._doc_count = len(texts)
        self._idf = {}
        for gram, freq in doc_freq.items():
            self._idf[gram] = math.log((self._doc_count + 1) / (freq + 1)) + 1

    def embed(self, text: str) -> List[float]:
        """Embed a single text. Uses fitted vocab/IDF if available."""
        if self._vocab is not None and self._idf is not None:
            ngrams = _char_ngrams(text)
            dim = len(self._vocab)
            vec = [0.0] * dim
            for gram in ngrams:
                idx = self._vocab.get(gram)
                if idx is not None:
                    idf = self._idf.get(gram, 1.0)
                    vec[idx] += idf
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            return vec
        return embed_text(text)

    def similarity(self, text_a: str, text_b: str) -> float:
        """Compute similarity between two texts."""
        vec_a = self.embed(text_a)
        vec_b = self.embed(text_b)
        return cosine_similarity(vec_a, vec_b)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_embedder_instance: Optional[LocalEmbedder] = None
_embedder_lock = threading.Lock()


def get_embedder() -> LocalEmbedder:
    """Get the global LocalEmbedder singleton."""
    global _embedder_instance
    if _embedder_instance is None:
        with _embedder_lock:
            if _embedder_instance is None:
                _embedder_instance = LocalEmbedder()
    return _embedder_instance
