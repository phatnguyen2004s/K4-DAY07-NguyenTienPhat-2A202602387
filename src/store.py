from __future__ import annotations

from typing import Any, Callable

from .chunking import compute_similarity
from .embeddings import _mock_embed
from .models import Document


class EmbeddingStore:
    """
    A vector store for text chunks.

    In-memory implementation only. The ChromaDB branch of the starter was dropped on
    purpose: no test or checkpoint needs it, and a half-initialised Chroma client would
    silently break every method on machines that happen to have chromadb installed.
    The embedding_fn parameter allows injection of mock embeddings for tests.
    """

    def __init__(
        self,
        collection_name: str = "documents",
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        self._embedding_fn = embedding_fn or _mock_embed
        self._collection_name = collection_name
        self._use_chroma = False
        self._store: list[dict[str, Any]] = []
        self._collection = None
        self._next_index = 0

    @staticmethod
    def _parent_doc_id(doc: Document) -> str:
        """doc_id points at the source document, not the chunk.

        Chunks created by bench.py are named "<file-stem>#<n>"; delete_document()
        must remove all of them by the stem, so strip the "#<n>" suffix here.
        """
        if "doc_id" in doc.metadata:
            return str(doc.metadata["doc_id"])
        return doc.id.split("#", 1)[0]

    def _make_record(self, doc: Document) -> dict[str, Any]:
        metadata = dict(doc.metadata)  # copy: never mutate the caller's object
        metadata["doc_id"] = self._parent_doc_id(doc)
        record = {
            "index": self._next_index,
            "id": doc.id,
            "content": doc.content,
            "metadata": metadata,
            "embedding": self._embedding_fn(doc.content),
        }
        self._next_index += 1
        return record

    def _search_records(self, query: str, records: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        """Similarity search over any candidate set.

        search() and search_with_filter() differ only in the candidate list they pass
        in, so both share this ranking code and cannot drift apart.
        """
        if top_k <= 0 or not records:
            return []
        query_embedding = self._embedding_fn(query)
        scored = [
            (compute_similarity(query_embedding, record["embedding"]), record["index"], record)
            for record in records
        ]
        # Highest score first; ties broken by insertion order for deterministic output.
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            {"id": r["id"], "content": r["content"], "metadata": dict(r["metadata"]), "score": score}
            for score, _, r in scored[:top_k]
        ]

    def add_documents(self, docs: list[Document]) -> None:
        """
        Embed each document's content and store it.

        One Document = one record. Chunking is the caller's job (see bench.py).
        """
        for doc in docs:
            self._store.append(self._make_record(doc))

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Find the top_k most similar documents to query.

        Cosine similarity via compute_similarity — identical to the dot product for the
        normalised vectors MockEmbedder/LocalEmbedder produce, and still correct for
        backends that do not normalise.
        """
        return self._search_records(query, self._store, top_k)

    def get_collection_size(self) -> int:
        """Return the total number of stored chunks."""
        return len(self._store)

    def search_with_filter(self, query: str, top_k: int = 3, metadata_filter: dict = None) -> list[dict]:
        """
        Search with optional metadata pre-filtering.

        Filter FIRST, then rank. Filtering after taking top_k could return nothing even
        though matching chunks exist, because the k slots were taken by other documents.
        A filter value that is a list/tuple/set matches any of its members.
        """
        if not metadata_filter:
            candidates = self._store
        else:
            candidates = [r for r in self._store if self._matches(r["metadata"], metadata_filter)]
        return self._search_records(query, candidates, top_k)

    @staticmethod
    def _matches(metadata: dict[str, Any], metadata_filter: dict[str, Any]) -> bool:
        for key, expected in metadata_filter.items():
            if key not in metadata:
                return False
            if isinstance(expected, (list, tuple, set)):
                if metadata[key] not in expected:
                    return False
            elif metadata[key] != expected:
                return False
        return True

    def delete_document(self, doc_id: str) -> bool:
        """
        Remove all chunks belonging to a document.

        Returns True if any chunks were removed, False otherwise.
        """
        before = len(self._store)
        self._store = [r for r in self._store if r["metadata"].get("doc_id") != doc_id]
        return len(self._store) < before
