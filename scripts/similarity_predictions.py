#!/usr/bin/env python3
"""Bài tập 3.3 — dự đoán cosine similarity cho 5 cặp câu, rồi đo thật (REPORT_CANHAN mục 4).

Chạy:  python scripts/similarity_predictions.py                # embedder theo .env (mặc định mock)
       python scripts/similarity_predictions.py --provider gemini
Dự đoán được ghi CỐ ĐỊNH trong PAIRS trước khi chạy — không sửa sau khi thấy kết quả.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

from src import compute_similarity  # noqa: E402
from src.embeddings import (  # noqa: E402
    EMBEDDING_PROVIDER_ENV, GEMINI_EMBEDDING_MODEL, LOCAL_EMBEDDING_MODEL, OPENAI_EMBEDDING_MODEL,
    GeminiEmbedder, LocalEmbedder, OpenAIEmbedder, _mock_embed,
)

# (dự đoán, câu A, câu B, lý do dự đoán)
PAIRS = [
    ("cao",  "You can get your money back if the parcel never shows up.",
             "A full refund is issued when the order does not arrive.",
             "Khác từ vựng gần như hoàn toàn (money back/refund, parcel/order, never shows up/does not arrive) nhưng cùng một ý"),
    ("thấp", "Etsy covers up to $250 of a refund.",
             "Select the pencil icon next to your shop name under Sales Channels.",
             "Hai chủ đề không liên quan: mức hoàn tiền vs thao tác giao diện"),
    ("cao (bẫy)", "The buyer must wait 48 hours after messaging the seller before opening a case.",
             "The seller must respond to the buyer's message within 48 hours.",
             "Trùng nhiều từ (buyer, seller, 48 hours, message) nên embedding có thể cho điểm cao dù nghĩa khác: một bên là điều kiện của buyer, bên kia là nghĩa vụ của seller"),
    ("cao",  "Người mua phải trả hàng trong vòng 30 ngày kể từ khi nhận.",
             "Buyers must return the item within 30 days of delivery.",
             "Cùng nghĩa, khác ngôn ngữ — kiểm tra embedder có đa ngữ thật không (mock chắc chắn thấp)"),
    ("thấp", "How is the estimated delivery date calculated?",
             "Can digital downloads be returned?",
             "Cùng là câu hỏi về chính sách Etsy nhưng khác hẳn chủ đề; dự đoán thấp, có thể hơi cao hơn cặp 2 vì cùng 'giọng' câu hỏi"),
]


def make_embedder(provider: str | None):
    provider = (provider or os.getenv(EMBEDDING_PROVIDER_ENV, "mock")).strip().lower()
    try:
        if provider == "local":
            return LocalEmbedder(os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        if provider == "openai":
            return OpenAIEmbedder(os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
        if provider == "gemini":
            return GeminiEmbedder(os.getenv("GEMINI_EMBEDDING_MODEL", GEMINI_EMBEDDING_MODEL))
    except Exception as error:
        print(f"[warn] không khởi tạo được '{provider}' ({error.__class__.__name__}: {error}) → dùng mock")
    return _mock_embed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mock", "local", "openai", "gemini"], default=None)
    args = parser.parse_args()
    load_dotenv(override=False)
    embed = make_embedder(args.provider)
    print(f"embedder: {getattr(embed, '_backend_name', embed.__class__.__name__)}\n")
    print(f"{'#':>2} | {'dự đoán':10} | {'cosine':>7} | câu A / câu B")
    for i, (pred, a, b, _) in enumerate(PAIRS, 1):
        score = compute_similarity(embed(a), embed(b))
        print(f"{i:>2} | {pred:10} | {score:+.3f} | {a}\n{'':2} | {'':10} | {'':7} | {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
