from typing import Callable

from .store import EmbeddingStore


class KnowledgeBaseAgent:
    """
    An agent that answers questions using a vector knowledge base.

    Retrieval-augmented generation (RAG) pattern:
        1. Retrieve top-k relevant chunks from the store.
        2. Build a prompt with the chunks as context.
        3. Call the LLM to generate an answer.
    """

    NO_CONTEXT_ANSWER = "Không tìm thấy thông tin liên quan trong cơ sở tri thức."

    def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3) -> str:
        if self.store.get_collection_size() == 0:
            return self.NO_CONTEXT_ANSWER
        results = self.store.search(question, top_k=top_k)
        return self._generate(question, results)

    def answer_with_filter(self, question: str, top_k: int = 3, metadata_filter: dict | None = None) -> str:
        """Same RAG flow, but retrieval is restricted by metadata (used for A/B in bench.py)."""
        if self.store.get_collection_size() == 0:
            return self.NO_CONTEXT_ANSWER
        results = self.store.search_with_filter(question, top_k=top_k, metadata_filter=metadata_filter)
        return self._generate(question, results)

    def _generate(self, question: str, results: list[dict]) -> str:
        if not results:
            return self.NO_CONTEXT_ANSWER
        return self.llm_fn(self.build_prompt(question, results))

    @staticmethod
    def build_prompt(question: str, results: list[dict]) -> str:
        """Number each chunk [1], [2], ... with its source so answers can be traced back.

        The instructions pin the model to the supplied context: cite the chunk numbers it
        used, and say the information is missing rather than guessing.
        """
        context_blocks = []
        for n, r in enumerate(results, start=1):
            meta = r.get("metadata", {})
            source = meta.get("doc_id") or meta.get("source") or r.get("id", "unknown")
            audience = meta.get("audience")
            label = f"{source}" + (f", audience={audience}" if audience else "")
            context_blocks.append(f"[{n}] (nguồn: {label})\n{r['content'].strip()}")
        context = "\n\n".join(context_blocks)

        return (
            "Bạn là trợ lý trả lời câu hỏi về chính sách dựa trên tài liệu được cung cấp.\n"
            "Quy tắc:\n"
            "- Chỉ dùng thông tin trong NGỮ CẢNH bên dưới; không suy đoán, không dùng kiến thức ngoài.\n"
            "- Khi trả lời, trích dẫn số hiệu đoạn đã dùng, ví dụ [1] hoặc [2].\n"
            "- Nếu ngữ cảnh không chứa câu trả lời, nói rõ là không tìm thấy thông tin.\n\n"
            f"NGỮ CẢNH:\n{context}\n\n"
            f"CÂU HỎI: {question}\n"
            "TRẢ LỜI:"
        )
