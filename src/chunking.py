from __future__ import annotations

import math
import re


class FixedSizeChunker:
    """
    Split text into fixed-size chunks with optional overlap.

    Rules:
        - Each chunk is at most chunk_size characters long.
        - Consecutive chunks share overlap characters.
        - The last chunk contains whatever remains.
        - If text is shorter than chunk_size, return [text].
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        step = self.chunk_size - self.overlap
        chunks: list[str] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + self.chunk_size]
            chunks.append(chunk)
            if start + self.chunk_size >= len(text):
                break
        return chunks


class SentenceChunker:
    """
    Split text into chunks of at most max_sentences_per_chunk sentences.

    Sentence detection: split on ". ", "! ", "? " or ".\n".
    Strip extra whitespace from each chunk.
    """

    # Split at whitespace that FOLLOWS a terminal punctuation mark. The lookbehind
    # keeps the punctuation attached to its sentence instead of swallowing it.
    # Known limits: abbreviations ("Dr. Smith", "v.v. ") and initials still split,
    # while decimals ("3.5") are safe because no whitespace follows the dot.
    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

    def __init__(self, max_sentences_per_chunk: int = 3) -> None:
        self.max_sentences_per_chunk = max(1, max_sentences_per_chunk)

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        sentences = [s.strip() for s in self._SENTENCE_BOUNDARY.split(text.strip()) if s.strip()]

        chunks: list[str] = []
        for start in range(0, len(sentences), self.max_sentences_per_chunk):
            group = sentences[start : start + self.max_sentences_per_chunk]
            chunks.append(" ".join(group))
        return chunks


class RecursiveChunker:
    """
    Recursively split text using separators in priority order.

    Default separator priority:
        ["\n\n", "\n", ". ", " ", ""]
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, separators: list[str] | None = None, chunk_size: int = 500) -> None:
        self.separators = self.DEFAULT_SEPARATORS if separators is None else list(separators)
        self.chunk_size = chunk_size

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]
        return [c for c in self._split(text, self.separators) if c.strip()]

    def _hard_cut(self, text: str) -> list[str]:
        """Last resort: cut every chunk_size characters, ignoring boundaries."""
        return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

    def _split(self, current_text: str, remaining_separators: list[str]) -> list[str]:
        # Base case 1: already small enough.
        if len(current_text) <= self.chunk_size:
            return [current_text]
        # Base case 2: no separators left (also covers separators=[]).
        if not remaining_separators:
            return self._hard_cut(current_text)

        separator, rest = remaining_separators[0], remaining_separators[1:]
        # Base case 3: the "" separator means character-level cutting.
        if separator == "":
            return self._hard_cut(current_text)

        pieces = current_text.split(separator)
        if len(pieces) == 1:
            # Separator not present at this level — try the next, finer one.
            return self._split(current_text, rest)

        # Two directions:
        #   down — a piece still longer than chunk_size is split again with finer separators;
        #   up   — adjacent small pieces are merged (re-joined with the same separator)
        #          until just under chunk_size, so short lines don't become tiny chunks.
        chunks: list[str] = []
        buffer: list[str] = []
        buffer_len = 0

        def flush() -> None:
            nonlocal buffer, buffer_len
            if buffer:
                chunks.append(separator.join(buffer))
            buffer, buffer_len = [], 0

        for piece in pieces:
            if len(piece) > self.chunk_size:
                flush()
                chunks.extend(self._split(piece, rest))
                continue
            added = len(piece) + (len(separator) if buffer else 0)
            if buffer and buffer_len + added > self.chunk_size:
                flush()
                added = len(piece)
            buffer.append(piece)
            buffer_len += added
        flush()
        return chunks


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def compute_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    cosine_similarity = dot(a, b) / (||a|| * ||b||)

    Returns 0.0 if either vector has zero magnitude.
    """
    norm_a = math.sqrt(_dot(vec_a, vec_a))
    norm_b = math.sqrt(_dot(vec_b, vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return _dot(vec_a, vec_b) / (norm_a * norm_b)


class ChunkingStrategyComparator:
    """Run all built-in chunking strategies and compare their results."""

    def compare(self, text: str, chunk_size: int = 200) -> dict:
        strategies = {
            "fixed_size": FixedSizeChunker(chunk_size=chunk_size, overlap=chunk_size // 10),
            "by_sentences": SentenceChunker(max_sentences_per_chunk=3),
            "recursive": RecursiveChunker(chunk_size=chunk_size),
        }
        result: dict = {}
        for name, chunker in strategies.items():
            chunks = chunker.chunk(text)
            count = len(chunks)
            avg_length = round(sum(len(c) for c in chunks) / count, 1) if count else 0.0
            result[name] = {"count": count, "avg_length": avg_length, "chunks": chunks}
        return result
