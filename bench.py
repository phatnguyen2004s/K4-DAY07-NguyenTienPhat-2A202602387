#!/usr/bin/env python3
"""bench.py — benchmark truy xuất cá nhân (Phát · R3 · chiến lược: Heading/Section chunker).

Chạy:   python bench.py | tee ket_qua_benchmark.txt      # 5 query, chiến lược mặc định
        python bench.py --strategy recursive              # đổi chiến lược để so sánh A/B
        python bench.py --baseline                        # bảng baseline cho REPORT_NHOM mục 2

Luồng (đúng 7 bước trong hướng dẫn nhóm mục 9.5):
  1. đọc từng .md → tách frontmatter thành metadata, phần thân thành content
  2. chunk phần thân bằng chiến lược cá nhân  (đổi DEFAULT_STRATEGY là xong — mọi thứ khác giữ nguyên)
  3. mỗi chunk → Document(id="<file>#<i>", metadata={**frontmatter, "doc_id": "<file>"})
  4. add_documents() vào EmbeddingStore
  5. chạy 5 query chung; query cần lọc thì dùng search_with_filter()
  6. in top-3: score, Document.id, doc_id, audience, preview
  7. lưu output: python bench.py | tee ket_qua_benchmark.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from src import (
    EMBEDDING_PROVIDER_ENV,
    GEMINI_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_MODEL,
    ChunkingStrategyComparator,
    Document,
    EmbeddingStore,
    FixedSizeChunker,
    GeminiEmbedder,
    KnowledgeBaseAgent,
    LocalEmbedder,
    OpenAIEmbedder,
    RecursiveChunker,
    SentenceChunker,
    _mock_embed,
)

CORPUS_DIR = Path("data/etsy-policies")
TOP_K = 3
CACHE_PATH = Path(".embedding_cache.json")

# ──────────────────────────────────────────────────────────────────────────────
# Chiến lược của Phát: chunk theo heading/section của văn bản chính sách
# ──────────────────────────────────────────────────────────────────────────────


class HeadingChunker:
    """Chunk theo heading Markdown — mỗi mục (section) của trang chính sách là một chunk.

    Lý do thiết kế: trang Help Center được người soạn chia sẵn thành các mục
    ("## How do I qualify?", "## When can I open a case?"). Mỗi mục đã là một đơn vị
    ngữ nghĩa trọn vẹn, nên cắt theo mục giữ được câu hỏi + đáp án trong cùng chunk,
    không cắt giữa danh sách điều kiện như FixedSize, cũng không dính heading vào cuối
    chunk trước như Recursive.

    Hai quy tắc:
      - Mọi chunk được gắn breadcrumb "H1 › H2 › H3" ở đầu để giữ ngữ cảnh "mục này nói
        về gì" — cũng giúp query khớp với tiêu đề mục.
      - Mục dài hơn max_chars → hạ xuống RecursiveChunker cắt phần thân, và GẮN LẠI
        breadcrumb vào từng mảnh con (không có bước này, mảnh thứ hai trở đi mất ngữ cảnh).
    """

    HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)

    def __init__(self, max_chars: int = 800, breadcrumb: bool = True) -> None:
        self.max_chars = max_chars
        self.breadcrumb = breadcrumb

    def sections(self, text: str) -> list[tuple[list[str], str]]:
        """Trả về [(đường dẫn heading, thân mục)] theo thứ tự xuất hiện."""
        matches = list(self.HEADING_RE.finditer(text))
        if not matches:
            return [([], text.strip())]
        out: list[tuple[list[str], str]] = []
        preamble = text[: matches[0].start()].strip()
        if preamble:
            out.append(([], preamble))
        stack: list[tuple[int, str]] = []  # (level, title) — heading cha đang mở
        for i, m in enumerate(matches):
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out.append(([t for _, t in stack], text[m.end() : end].strip()))
        return out

    def chunk(self, text: str) -> list[str]:
        chunks: list[str] = []
        for path, body in self.sections(text):
            if not body:
                continue  # heading không có thân (ví dụ H1 chỉ là tiêu đề) — tiêu đề vẫn nằm trong breadcrumb con
            header = (" › ".join(path) + "\n") if (path and self.breadcrumb) else ""
            if len(header) + len(body) <= self.max_chars:
                chunks.append(header + body)
                continue
            fallback = RecursiveChunker(chunk_size=max(200, self.max_chars - len(header)))
            for piece in fallback.chunk(body):
                chunks.append(header + piece)
        return chunks


# Mỗi thành viên chỉ đổi DÒNG NÀY sang chiến lược của mình; ingest/query giữ nguyên.
DEFAULT_STRATEGY = "heading"  # Phát: heading · Sang: fixed · Hoàng: recursive

STRATEGIES = {
    "heading": lambda: HeadingChunker(max_chars=800),
    "fixed": lambda: FixedSizeChunker(chunk_size=700, overlap=100),
    "recursive": lambda: RecursiveChunker(chunk_size=600),
    "sentence": lambda: SentenceChunker(max_sentences_per_chunk=4),
}

# ──────────────────────────────────────────────────────────────────────────────
# 5 benchmark query chung của nhóm — bản CANONICAL R2 Hoàng chốt (CP5)
#   markers: cụm đặc trưng của gold answer — chấm ở mức NỘI DUNG: chunk lấy về phải chứa nó
#   runs   : mỗi lần chạy một filter; run có primary=True là run tính điểm chính thức
# ──────────────────────────────────────────────────────────────────────────────

QUERIES = [
    # Bộ canonical do R2 Hoàng chốt (file R2_HOANG_5_BENCHMARK_QUERIES_GOLD.md) — không đổi wording.
    {
        "id": 1,
        "type": "condition",
        "query": "What conditions must be met before a buyer can open a case on Etsy?",
        "gold": "To open a case, the estimated delivery date for the order must have passed and at least 48 hours "
                "must have passed since the buyer sent the seller a Help with order request.",
        "runs": [
            {"label": "audience=buyer", "filter": {"audience": "buyer"}, "primary": True,
             "expected_doc_ids": ["buyer-open-case", "buyer-estimated-delivery"],
             "markers": ["48 hours"]},
        ],
    },
    {
        "id": 2,
        "type": "procedure",
        "query": "How does a seller work with a buyer to resolve an open Etsy case through Shop Manager?",
        "gold": "The seller uses Cases in Shop Manager, selects the applicable case, and communicates through "
                "Add Your Comment in the case log.",
        "runs": [
            {"label": "audience=seller", "filter": {"audience": "seller"}, "primary": True,
             "expected_doc_ids": ["seller-resolve-case"],
             "markers": ["Shop Manager"]},
        ],
    },
    {
        "id": 3,
        "type": "list + A/B metadata filter (BẮT BUỘC 3 lần)",
        "query": "How much refund does Etsy Purchase Protection provide for a qualifying order?",
        "gold": "BUYER: full refund for qualifying orders when an item doesn't arrive, arrives damaged, arrives 7+ days "
                "after the maximum estimated delivery date window, or differs significantly from the description. "
                "SELLER (contrast): Etsy covers up to $250 of a refund (or the converted equivalent); any remaining "
                "amount is charged to the seller, who does not need to issue the refund.",
        "runs": [
            {"label": "audience=buyer", "filter": {"audience": "buyer"}, "primary": True,
             "expected_doc_ids": ["buyer-purchase-protection"],
             "markers": ["full refund"]},
            {"label": "no filter", "filter": None, "primary": False,
             "expected_doc_ids": ["buyer-purchase-protection", "seller-purchase-protection"],
             "markers": ["full refund", "$250"]},
            {"label": "audience=seller", "filter": {"audience": "seller"}, "primary": False,
             "expected_doc_ids": ["seller-purchase-protection"],
             "markers": ["$250"]},
        ],
    },
    {
        "id": 4,
        "type": "formula",
        "query": "Which components are used to calculate an Etsy estimated delivery date?",
        "gold": "Processing time plus carrier transit time equals the estimated delivery date.",
        "runs": [
            {"label": "audience=buyer", "filter": {"audience": "buyer"}, "primary": True,
             "expected_doc_ids": ["buyer-estimated-delivery"],
             "markers": ["carrier transit time"]},
        ],
    },
    {
        "id": 5,
        "type": "numeric + procedure",
        "query": "How can a seller issue a full or partial refund, and what is the Etsy Payments time limit?",
        "gold": "The seller uses Shop Manager to issue the refund; Etsy Payments refunds can be issued after "
                "processing and before 180 days have passed.",
        "runs": [
            {"label": "audience=seller", "filter": {"audience": "seller"}, "primary": True,
             "expected_doc_ids": ["seller-issue-refund"],
             "markers": ["180 days"]},
        ],
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Nạp corpus
# ──────────────────────────────────────────────────────────────────────────────


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Tách YAML frontmatter đơn giản. Chịu được cả giá trị có nháy kép lẫn không."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        m = re.match(r"^(\w+):\s*(.*?)\s*$", line)
        if not m:
            continue
        key, value = m.groups()
        value = value.split(" #", 1)[0].strip()  # bỏ comment inline
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value
    return meta, parts[2].lstrip("\n")


def load_corpus(chunker) -> tuple[list[Document], dict[str, int]]:
    docs: list[Document] = []
    per_file: dict[str, int] = {}
    for path in sorted(CORPUS_DIR.glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        chunks = chunker.chunk(body)
        per_file[path.stem] = len(chunks)
        for i, content in enumerate(chunks):
            docs.append(Document(
                id=f"{path.stem}#{i}",
                content=content,
                metadata={**meta, "doc_id": path.stem, "chunk_index": i},  # frontmatter trải vào MỌI chunk
            ))
    return docs, per_file


# ──────────────────────────────────────────────────────────────────────────────
# Embedding backend (+ cache theo hash nội dung để chạy lại không tốn tiền/thời gian)
# ──────────────────────────────────────────────────────────────────────────────


class CachedEmbedder:
    def __init__(self, inner, path: Path) -> None:
        self.inner, self.path = inner, path
        self._backend_name = getattr(inner, "_backend_name", inner.__class__.__name__)
        self.cache: dict[str, list[float]] = json.loads(path.read_text()) if path.exists() else {}
        self.hits = self.misses = 0

    def __call__(self, text: str) -> list[float]:
        key = hashlib.sha1(f"{self._backend_name}\x00{text}".encode("utf-8")).hexdigest()
        if key in self.cache:
            self.hits += 1
        else:
            self.cache[key] = [float(v) for v in self.inner(text)]
            self.misses += 1
        return self.cache[key]

    def save(self) -> None:
        if self.misses:
            self.path.write_text(json.dumps(self.cache), encoding="utf-8")


def make_embedder(provider: str | None):
    provider = (provider or os.getenv(EMBEDDING_PROVIDER_ENV, "mock")).strip().lower()
    try:
        if provider == "local":
            return LocalEmbedder(model_name=os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        if provider == "openai":
            return OpenAIEmbedder(model_name=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
        if provider == "gemini":
            return GeminiEmbedder(model_name=os.getenv("GEMINI_EMBEDDING_MODEL", GEMINI_EMBEDDING_MODEL))
    except Exception as error:  # thiếu package / thiếu key → về mock, nhưng nói rõ
        print(f"[warn] không khởi tạo được embedder '{provider}' ({error.__class__.__name__}: {error}) → dùng mock")
    return _mock_embed


# ──────────────────────────────────────────────────────────────────────────────
# LLM cho agent: mặc định là stub (trích đoạn [1]) để pipeline chạy không cần API
# ──────────────────────────────────────────────────────────────────────────────


def stub_llm(prompt: str) -> str:
    m = re.search(r"\[1\] \(nguồn: (.*?)\)\n(.*?)(?=\n\n\[2\] \(nguồn|\n\nCÂU HỎI:)", prompt, re.S)
    if not m:
        return "[stub-LLM] không tách được ngữ cảnh"
    source, body = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
    return f"[stub-LLM — trích nguyên văn đoạn [1], nguồn {source}] {body[:220]}{'…' if len(body) > 220 else ''}"


def make_llm(kind: str):
    if kind == "gemini":
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        model = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
        return lambda prompt: client.models.generate_content(model=model, contents=prompt).text.strip()
    if kind == "openai":
        from openai import OpenAI
        client = OpenAI()
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        return lambda prompt: client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}]).choices[0].message.content.strip()
    return stub_llm


# ──────────────────────────────────────────────────────────────────────────────
# Chấm điểm hai mức
# ──────────────────────────────────────────────────────────────────────────────


def first_rank(results: list[dict], predicate) -> int | None:
    for rank, r in enumerate(results, start=1):
        if predicate(r):
            return rank
    return None


def score_run(results: list[dict], run: dict) -> dict:
    doc_rank = first_rank(results, lambda r: r["metadata"].get("doc_id") in run["expected_doc_ids"])
    markers = [m.lower() for m in run["markers"]]
    content_rank = first_rank(results, lambda r: any(m in r["content"].lower() for m in markers))
    # Rubric lab: 2đ nếu chunk chứa đáp án ở top-1, 1đ nếu ở top-2/3, 0đ nếu vắng.
    points = 2 if content_rank == 1 else (1 if content_rank else 0)
    return {"doc_rank": doc_rank, "content_rank": content_rank, "points": points}


def preview(text: str, n: int = 110) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat[:n] + ("…" if len(flat) > n else "")


# ──────────────────────────────────────────────────────────────────────────────
# Chế độ baseline (việc R3): so 3 chiến lược built-in + heading trên 2–3 tài liệu
# ──────────────────────────────────────────────────────────────────────────────


def coherence(chunks: list[str]) -> dict:
    heading_line = re.compile(r"^#{1,6} ", re.M)
    mid_sentence = sum(1 for c in chunks if c.strip() and c.strip()[-1] not in ".!?:")
    glued = sum(1 for c in chunks if heading_line.search(c.strip()[1:]))  # heading nằm GIỮA/CUỐI chunk
    return {"mid_sentence_end": mid_sentence, "heading_glued": glued}


def run_baseline(files: list[str], chunk_size: int) -> None:
    print(f"=== BASELINE ChunkingStrategyComparator (chunk_size={chunk_size}) — frontmatter đã bỏ ===")
    print(f"{'tài liệu':28} {'chiến lược':13} {'count':>5} {'avg_len':>8} {'kết thúc giữa câu':>18} {'heading dính':>13}")
    for stem in files:
        path = CORPUS_DIR / f"{stem}.md"
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        rows = ChunkingStrategyComparator().compare(body, chunk_size=chunk_size)
        rows["heading (Phát)"] = {"chunks": STRATEGIES["heading"]().chunk(body)}  # đúng cấu hình chạy benchmark
        for name, stats in rows.items():
            chunks = stats["chunks"]
            c = coherence(chunks)
            avg = sum(map(len, chunks)) / len(chunks) if chunks else 0
            print(f"{stem:28} {name:13} {len(chunks):5d} {avg:8.1f} {c['mid_sentence_end']:>10d}/{len(chunks):<7d} {c['heading_glued']:>6d}/{len(chunks)}")
        print()


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark retrieval cá nhân")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default=DEFAULT_STRATEGY)
    parser.add_argument("--provider", choices=["mock", "local", "openai", "gemini"], default=None,
                        help=f"embedding backend (mặc định: ${EMBEDDING_PROVIDER_ENV} trong .env, hoặc mock)")
    parser.add_argument("--llm", choices=["stub", "gemini", "openai"], default="stub")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--baseline", action="store_true", help="chỉ chạy bảng baseline comparator")
    parser.add_argument("--baseline-files", nargs="*",
                        default=["buyer-open-case", "seller-purchase-protection", "seller-set-return-policy"])
    parser.add_argument("--baseline-chunk-size", type=int, default=200)
    args = parser.parse_args()

    load_dotenv(override=False)
    if args.baseline:
        run_baseline(args.baseline_files, args.baseline_chunk_size)
        return 0

    chunker = STRATEGIES[args.strategy]()
    raw_embedder = make_embedder(args.provider)
    backend = getattr(raw_embedder, "_backend_name", raw_embedder.__class__.__name__)
    embedder = raw_embedder if raw_embedder is _mock_embed else CachedEmbedder(raw_embedder, CACHE_PATH)

    docs, per_file = load_corpus(chunker)
    store = EmbeddingStore(collection_name="bench", embedding_fn=embedder)
    store.add_documents(docs)
    agent = KnowledgeBaseAgent(store=store, llm_fn=make_llm(args.llm))

    print("=== BENCHMARK — Phát (R3) ===")
    print(f"strategy : {args.strategy}  ({chunker.__class__.__name__}, {vars(chunker)})")
    print(f"embedder : {backend}" + ("   ⚠ mock không có ngữ nghĩa — số liệu chỉ để kiểm pipeline" if raw_embedder is _mock_embed else ""))
    print(f"llm      : {args.llm}")
    print(f"corpus   : {len(per_file)} tài liệu → {store.get_collection_size()} chunk "
          f"(avg {sum(len(d.content) for d in docs) / max(1, len(docs)):.0f} ký tự/chunk)")
    for stem, n in per_file.items():
        print(f"           {stem:28} {n:3d} chunk")

    summary = []
    for q in QUERIES:
        print(f"\n{'─' * 100}\nQ{q['id']} [{q['type']}] {q['query']}\n   gold: {q['gold']}")
        for run in q["runs"]:
            results = store.search_with_filter(q["query"], top_k=args.top_k, metadata_filter=run["filter"])
            s = score_run(results, run)
            print(f"\n   ▶ run: {run['label']}" + ("   (tính điểm)" if run["primary"] else ""))
            for rank, r in enumerate(results, start=1):
                m = r["metadata"]
                print(f"     {rank}. score={r['score']:+.3f}  {r['id']:32} doc={m.get('doc_id'):27} aud={m.get('audience')}")
                print(f"        “{preview(r['content'])}”")
            if not results:
                print("     (không có kết quả — filter loại hết ứng viên)")
            doc_txt = f"top-{s['doc_rank']}" if s["doc_rank"] else "KHÔNG có trong top-3"
            con_txt = f"top-{s['content_rank']}" if s["content_rank"] else "KHÔNG có trong top-3"
            print(f"     chấm doc-level (doc_id gold): {doc_txt}   |   content-level (marker {run['markers']}): {con_txt}   →  {s['points']}/2 điểm")
            if run["primary"] or run["filter"] is not None:
                answer = agent.answer_with_filter(q["query"], top_k=args.top_k, metadata_filter=run["filter"])
                print(f"     agent: {preview(answer, 300)}")
            if run["primary"]:
                summary.append((q["id"], run["label"], s))

    print(f"\n{'═' * 100}\nTỔNG KẾT (run tính điểm của mỗi query) — strategy={args.strategy}, embedder={backend}")
    print(f"{'Q':>2}  {'filter':16} {'doc-level':>10} {'content-level':>14} {'điểm':>6}")
    total = 0
    for qid, label, s in summary:
        total += s["points"]
        d = f"top-{s['doc_rank']}" if s["doc_rank"] else "miss"
        c = f"top-{s['content_rank']}" if s["content_rank"] else "miss"
        print(f"{qid:>2}  {label:16} {d:>10} {c:>14} {s['points']:>4}/2")
    print(f"{'':2}  {'TỔNG':16} {'':>10} {'':>14} {total:>4}/10")
    if isinstance(embedder, CachedEmbedder):
        embedder.save()
        print(f"\n(embedding cache: {embedder.hits} hit / {embedder.misses} miss → {CACHE_PATH})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
