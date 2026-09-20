# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Nguyễn Tiến Phát
**Nhóm:** 3Kings
**Ngày:** 20/10/2026

> **Nộp 1 bản / sinh viên.** Phần nhóm (lựa chọn tài liệu, thiết kế chiến lược, bộ câu hỏi đánh giá, demo) nộp chung 1 bản trong `REPORT_NHOM.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) + Kết quả truy xuất của tôi (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### Độ tương tự Cosine (Cosine Similarity) (Bài tập 1.1)

**Độ tương tự cosine cao (High cosine similarity) nghĩa là gì?**
> Hai vector embedding gần như cùng hướng trong không gian ngữ nghĩa, tức hai đoạn văn bản nói về cùng một ý — bất kể dùng từ giống hay khác nhau. 1.0 là trùng hướng hoàn toàn, ~0 là không liên quan, âm là ngược hướng.

**Ví dụ có độ tương tự CAO:**
- Câu A: *"You can get your money back if the parcel never shows up."*
- Câu B: *"A full refund is issued when the order does not arrive."*
- Tại sao tương đồng: gần như không chung từ nào (money back/refund, parcel/order, never shows up/does not arrive) nhưng cùng diễn đạt một chính sách — hoàn tiền khi hàng không đến. Embedding tốt phải nhận ra *nghĩa* chứ không so khớp *từ*.

**Ví dụ có độ tương tự THẤP:**
- Câu A: *"Etsy covers up to $250 of a refund."*
- Câu B: *"Select the pencil icon next to your shop name under Sales Channels."*
- Tại sao khác: một câu là điều khoản tài chính, câu kia là thao tác giao diện — không chung chủ đề, không chung ý, dù cùng nằm trong một trang Help Center.

**Tại sao độ tương tự cosine (cosine similarity) được ưu tiên hơn khoảng cách Euclid (Euclidean distance) cho text embeddings?**
> Cosine chỉ đo góc (hướng) giữa hai vector và bỏ qua độ lớn — ý nghĩa trong text embedding nằm ở hướng, còn độ lớn dễ bị ảnh hưởng bởi độ dài văn bản. Hơn nữa hầu hết mô hình embedding chuẩn hoá vector về độ dài 1, khi đó cosine bằng đúng tích vô hướng nên tính rất rẻ (`search()` của tôi tận dụng điều này); khoảng cách Euclid trong không gian hàng trăm chiều lại kém phân biệt vì mọi điểm đều "xa" nhau.

### Bài toán tính toán Chunking (Bài tập 1.2)

**Tài liệu 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**
> Trình bày phép tính: số chunk = ceil((10.000 − 50) / (500 − 50)) = ceil(9.950 / 450) = ceil(22,11) = **23**. Kiểm lại bằng code: `len(FixedSizeChunker(chunk_size=500, overlap=50).chunk('a'*10000))` → 23 (bước nhảy 450, chunk cuối bắt đầu ở vị trí 9.900 và chứa 100 ký tự còn lại).
> Đáp án: **23 chunk**.

**Nếu độ chồng chéo (overlap) tăng lên 100, số lượng chunk thay đổi thế nào? Tại sao muốn độ chồng chéo nhiều hơn?**
> ceil((10.000 − 100) / (500 − 100)) = ceil(24,75) = **25 chunk** (code cũng cho 25) — tăng 2 chunk vì bước nhảy giảm từ 450 xuống 400. Muốn overlap lớn hơn vì thông tin nằm đúng ranh giới chunk (một câu bị cắt đôi) sẽ xuất hiện trọn vẹn trong ít nhất một chunk, giúp truy xuất không bỏ sót; đổi lại tốn thêm chunk/embedding và nội dung trùng lặp có thể chiếm nhiều slot trong top-k.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

Giải thích cách tiếp cận của bạn khi lập trình (implement) các phần chính trong gói `src`.

### Các hàm chia nhỏ (Chunking Functions)

**`SentenceChunker.chunk`** — hướng tiếp cận:
> Tôi tách câu bằng regex `(?<=[.!?])\s+` — cắt tại **khoảng trắng đứng sau** dấu `.`/`!`/`?` nhờ *lookbehind*, nên dấu câu vẫn nằm lại trong câu (nếu split thẳng bằng `[.!?]\s+` thì dấu câu bị nuốt và mọi chunk thành câu cụt). Sau đó `strip` từng câu, bỏ câu rỗng, và gom mỗi `max_sentences_per_chunk` câu thành một chunk bằng slicing với bước nhảy; text rỗng hoặc toàn khoảng trắng trả `[]`. Edge case tôi biết là **chưa** xử lý: chữ viết tắt có dấu chấm (`Dr. Smith`, `v.v.`) sẽ bị cắt nhầm; số thập phân (`3.5`) thì an toàn vì sau dấu chấm không có khoảng trắng.

**`RecursiveChunker.chunk` / `_split`** — hướng tiếp cận:
> `_split` thử separator theo thứ tự ưu tiên `["\n\n", "\n", ". ", " ", ""]`: split text bằng separator hiện tại rồi chạy **hai chiều** — *xuống*: mảnh nào vẫn dài hơn `chunk_size` thì gọi đệ quy với các separator mịn hơn; *lên*: các mảnh nhỏ liền kề được nối lại (bằng chính separator đó) vào một buffer cho tới sát `chunk_size` rồi mới `flush`, nhờ vậy 40 dòng ngắn thành 4 chunk chứ không phải 40 chunk vụn. Ba base case: text đã ≤ `chunk_size` → trả nguyên; hết separator (kể cả `separators=[]`) → cắt cứng theo `chunk_size`; separator `""` → cắt cứng theo ký tự. Separator không xuất hiện trong text thì bỏ qua, thử separator kế tiếp.

### Lớp EmbeddingStore

**`add_documents` + `search`** — hướng tiếp cận:
> Tôi bỏ hẳn nhánh ChromaDB (starter gán `_use_chroma = True` *trước* khi tạo client — máy chấm có `chromadb` là 14 test sập) và chỉ dùng in-memory: mỗi `Document` → một record `{index, id, content, metadata (bản copy), embedding}` qua `_make_record`, không tự chunk (1 Document = 1 record). `search` gọi `_search_records`: embed query, tính cosine với mọi record bằng `compute_similarity` (với vector đã chuẩn hoá của Mock/Local thì bằng tích vô hướng, với backend không chuẩn hoá vẫn đúng), sort giảm dần (tie-break theo thứ tự nạp để kết quả ổn định), cắt `top_k`, và **bỏ `embedding` khỏi kết quả** để output không bị vector 64–768 chiều làm bẩn.

**`search_with_filter` + `delete_document`** — hướng tiếp cận:
> Lọc **trước**, rank sau: `search_with_filter` lọc `self._store` theo metadata (mọi cặp key/value phải khớp; giá trị dạng list nghĩa là "một trong") rồi đưa tập ứng viên đó vào cùng `_search_records` mà `search` dùng — hai hàm chỉ khác tập ứng viên nên không thể lệch nhau. Lọc sau top-k sẽ sai: k slot có thể bị tài liệu sai đối tượng chiếm hết và trả về rỗng dù store còn tài liệu hợp lệ (tôi kiểm chứng: 5 doc buyer + 1 doc seller, mock xếp buyer cao hơn, `top_k=1` với filter seller vẫn ra đúng doc seller). `delete_document` giữ lại các record có `metadata["doc_id"]` khác `doc_id`, so kích thước trước/sau để trả `True/False`; `_make_record` luôn gắn `doc_id` = phần trước `#` của `Document.id` (`policy#1` → `policy`), nên xoá một file là xoá trọn mọi chunk của nó.

### Tác tử KnowledgeBaseAgent

**`answer`** — hướng tiếp cận:
> Ba nhịp: `store.search(question, top_k)` → `build_prompt` → `llm_fn(prompt)`; store rỗng hoặc không có kết quả thì trả thông báo "không tìm thấy" và **không gọi LLM**. Ngữ cảnh được dựng bằng cách đánh số từng chunk `[1] (nguồn: doc_id, audience=…)` + nội dung, rồi prompt ràng buộc model: chỉ dùng NGỮ CẢNH, trích dẫn số hiệu đoạn đã dùng, không có thì nói rõ không tìm thấy — nhờ vậy câu trả lời truy vết được về đúng file và đúng chunk (*Source Traceability* trong `docs/EVALUATION.md`). Tôi thêm `answer_with_filter(question, top_k, metadata_filter)` đi cùng luồng nhưng truy xuất qua `search_with_filter`, dùng cho A/B filter ở benchmark; chữ ký các hàm của starter giữ nguyên.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử (Test Results)

```
(.venv) imac@Phats-MacBook-Air K4-DAY07-NguyenTienPhat-2A202602387 % pytest tests/ -v
============================= test session starts ==============================
platform darwin -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0 -- /Users/imac/Programming/K4-DAY07-NguyenTienPhat-2A202602387/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/imac/Programming/K4-DAY07-NguyenTienPhat-2A202602387
collected 42 items

tests/test_solution.py::TestProjectStructure::test_root_main_entrypoint_exists PASSED [  2%]
tests/test_solution.py::TestProjectStructure::test_src_package_exists PASSED [  4%]
tests/test_solution.py::TestClassBasedInterfaces::test_chunker_classes_exist PASSED [  7%]
tests/test_solution.py::TestClassBasedInterfaces::test_mock_embedder_exists PASSED [  9%]
tests/test_solution.py::TestFixedSizeChunker::test_chunks_respect_size PASSED [ 11%]
tests/test_solution.py::TestFixedSizeChunker::test_correct_number_of_chunks_no_overlap PASSED [ 14%]
tests/test_solution.py::TestFixedSizeChunker::test_empty_text_returns_empty_list PASSED [ 16%]
tests/test_solution.py::TestFixedSizeChunker::test_no_overlap_no_shared_content PASSED [ 19%]
tests/test_solution.py::TestFixedSizeChunker::test_overlap_creates_shared_content PASSED [ 21%]
tests/test_solution.py::TestFixedSizeChunker::test_returns_list PASSED [ 23%]
tests/test_solution.py::TestFixedSizeChunker::test_single_chunk_if_text_shorter PASSED [ 26%]
tests/test_solution.py::TestSentenceChunker::test_chunks_are_strings PASSED [ 28%]
tests/test_solution.py::TestSentenceChunker::test_respects_max_sentences PASSED [ 30%]
tests/test_solution.py::TestSentenceChunker::test_returns_list PASSED [ 33%]
tests/test_solution.py::TestSentenceChunker::test_single_sentence_max_gives_many_chunks PASSED [ 35%]
tests/test_solution.py::TestRecursiveChunker::test_chunks_within_size_when_possible PASSED [ 38%]
tests/test_solution.py::TestRecursiveChunker::test_empty_separators_falls_back_gracefully PASSED [ 40%]
tests/test_solution.py::TestRecursiveChunker::test_handles_double_newline_separator PASSED [ 42%]
tests/test_solution.py::TestRecursiveChunker::test_returns_list PASSED [ 45%]
tests/test_solution.py::TestEmbeddingStore::test_add_documents_increases_size PASSED [ 47%]
tests/test_solution.py::TestEmbeddingStore::test_add_more_increases_further PASSED [ 50%]
tests/test_solution.py::TestEmbeddingStore::test_initial_size_is_zero PASSED [ 52%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_content_key PASSED [ 54%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_score_key PASSED [ 57%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_sorted_by_score_descending PASSED [ 59%]
tests/test_solution.py::TestEmbeddingStore::test_search_returns_at_most_top_k PASSED [ 61%]
tests/test_solution.py::TestEmbeddingStore::test_search_returns_list PASSED [ 64%]
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_non_empty PASSED [ 66%]
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_returns_string PASSED [ 69%]
tests/test_solution.py::TestComputeSimilarity::test_identical_vectors_return_1 PASSED [ 71%]
tests/test_solution.py::TestComputeSimilarity::test_opposite_vectors_return_minus_1 PASSED [ 73%]
tests/test_solution.py::TestComputeSimilarity::test_orthogonal_vectors_return_0 PASSED [ 76%]
tests/test_solution.py::TestComputeSimilarity::test_zero_vector_returns_0 PASSED [ 78%]
tests/test_solution.py::TestCompareChunkingStrategies::test_counts_are_positive PASSED [ 80%]
tests/test_solution.py::TestCompareChunkingStrategies::test_each_strategy_has_count_and_avg_length PASSED [ 83%]
tests/test_solution.py::TestCompareChunkingStrategies::test_returns_three_strategies PASSED [ 85%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_filter_by_department PASSED [ 88%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_no_filter_returns_all_candidates PASSED [ 90%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_returns_at_most_top_k PASSED [ 92%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_reduces_collection_size PASSED [ 95%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_false_for_nonexistent_doc PASSED [ 97%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_true_for_existing_doc PASSED [100%]

============================== 42 passed in 0.03s ==============================
```

**Số lượng bài test vượt qua (pass):** 42 / 42

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

Dự đoán được ghi cố định trong `scripts/similarity_predictions.py` **trước khi chạy**; lệnh đo: `python scripts/similarity_predictions.py [--provider mock|local|gemini]`.

| Cặp | Câu A | Câu B | Dự đoán | Điểm thực tế | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | You can get your money back if the parcel never shows up. | A full refund is issued when the order does not arrive. | cao (khác từ, cùng nghĩa) | **0.800** | ✅ |
| 2 | Etsy covers up to $250 of a refund. | Select the pencil icon next to your shop name under Sales Channels. | thấp (khác chủ đề) | **0.548** | ✅ |
| 3 | The buyer must wait 48 hours after messaging the seller before opening a case. | The seller must respond to the buyer's message within 48 hours. | cao — *bẫy*: trùng từ (buyer, seller, 48 hours) nhưng khác nghĩa | **0.868** | ✅ (đúng "cao", nhưng cao nhất bảng — xem suy ngẫm) |
| 4 | Người mua phải trả hàng trong vòng 30 ngày kể từ khi nhận. | Buyers must return the item within 30 days of delivery. | cao (cùng nghĩa, khác ngôn ngữ) | **0.812** | ✅ |
| 5 | How is the estimated delivery date calculated? | Can digital downloads be returned? | thấp (cùng "giọng" câu hỏi, khác chủ đề) | **0.498** | ✅ |

Embedder: `gemini-embedding-001` (đo ngày 2026-09-20). Đối chiếu: cùng 5 cặp chạy bằng `MockEmbedder` cho +0.139 / +0.090 / −0.032 / +0.041 / +0.152 — tất cả ~0 và thứ tự ngược hẳn (cặp 5 dự đoán *thấp* lại cao nhất), vì mock băm MD5 chuỗi ký tự, không mã hoá ý nghĩa.

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**
> Bất ngờ nhất là cặp 3: hai câu **khác nghĩa** (điều kiện của buyer vs nghĩa vụ của seller) được 0.868 — **cao hơn cả cặp đồng nghĩa thật** (cặp 1, 0.800). Embedding biểu diễn "chủ đề + từ vựng chung" rất mạnh (buyer, seller, 48 hours, message), nhưng phân biệt *ai phải làm gì* yếu hơn nhiều — đó chính là lý do query Q3 của nhóm cần `metadata_filter` theo `audience`: cosine không tự tách được buyer/seller khi hai văn bản dùng chung từ vựng. Hai điều đáng ghi thêm: cặp 4 Việt–Anh đạt 0.812, tức model nối được nghĩa xuyên ngôn ngữ; và hai cặp "thấp" vẫn ở ~0.5 chứ không gần 0 — với model này "không liên quan" nằm quanh 0.5, nên điểm tuyệt đối không nói lên gì, chỉ **thứ hạng tương đối** trong cùng một truy vấn mới có nghĩa.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Chạy **5 câu hỏi đánh giá của nhóm** trên mã nguồn cá nhân của bạn trong gói `src`. **5 câu hỏi này phải trùng với các thành viên cùng nhóm** (xem `REPORT_NHOM.md`).

Cấu hình: chiến lược **Heading/Section chunker** (`max_chars=800`, breadcrumb, fallback Recursive) → 54 chunk; embedder `gemini-embedding-001`; `top_k=3`; filter theo file canonical của R2 (Q1/Q3/Q4 `audience=buyer`, Q2/Q5 `audience=seller`; Q3 chạy thêm không filter và `seller`). LLM của agent là stub trích nguyên văn đoạn [1] (không có API sinh văn bản), nên "câu trả lời agent" = nội dung chunk top-1. Output đầy đủ: `ket_qua_benchmark.txt`.

| # | Câu hỏi (Query) | Top-1 Chunk truy xuất được (tóm tắt) | Điểm Score | Có liên quan không? (Relevant) | Câu trả lời của Agent (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | What conditions must be met before a buyer can open a case on Etsy? | `buyer-open-case#1` — mục "How to open a case" (7 bước thao tác) | 0.839 | **Một phần**: đúng file, sai mục — mục có đáp án "When can I open a case?" (48 hours) đứng #3 với 0.833 | Trích các bước mở case, **không** nêu điều kiện 48h/EDD → chưa trả lời được |
| 2 | How does a seller work with a buyer to resolve an open Etsy case through Shop Manager? | `seller-resolve-case#5` — mục "How do I work with my buyer to resolve the case?" | 0.901 | **Có** — đúng file, đúng mục, chứa "Shop Manager", "Add Your Comment" | Trích đúng 4 bước Shop Manager → Help → Cases → Add Your Comment ✓ |
| 3 | How much refund does Etsy Purchase Protection provide for a qualifying order? *(filter buyer)* | `buyer-purchase-protection#0` — mục "Qualifying order issues" | 0.829 | **Có** — chứa "full refund" + 4 điều kiện. *Không filter:* top-1 là `seller-purchase-protection#0` ($250) → sai đối tượng | Trích "full refund for qualifying orders when an item doesn't arrive / arrives damaged / 7+ days / differs significantly" ✓ |
| 4 | Which components are used to calculate an Etsy estimated delivery date? | `buyer-estimated-delivery#2` — mục "How do I see the EDD before purchasing?" | 0.820 | **Một phần**: đúng file, sai mục — mục "How is the EDD calculated?" (processing + carrier transit) đứng #2 với 0.805 | Trích cách *xem* EDD trên Etsy.com/app → không trả lời "thành phần tính" |
| 5 | How can a seller issue a full or partial refund, and what is the Etsy Payments time limit? | `seller-issue-refund#6` — mục "When can I issue a refund?" | 0.858 | **Có** — chứa "180 days"; các bước refund nằm ở #2 (`#1`, "To refund an order") | Trích giới hạn 180 ngày ✓; phần quy trình phải lấy từ [2] |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** **5 / 5** (chấm theo nội dung/marker: Q2, Q3, Q5 ở top-1; Q4 ở top-2; Q1 ở top-3) → theo rubric `docs/SCORING.md`: 2+2+2+1+1 = **8 / 10**. Chấm "ngây thơ" theo doc_id thì 5/5 câu đều top-1 (10/10) — khoảng cách 2 điểm giữa hai cách chấm là phát hiện chính của tôi: với chunker theo heading, các mục trong **cùng một file** có điểm cosine gần như nhau (Q1: 0.839/0.836/0.833), nên file đúng luôn thắng nhưng *mục* đúng không chắc ở top-1.

So sánh cùng corpus, cùng 5 query, cùng embedder, chỉ đổi chunker (tôi chạy cả 4 để có số liệu đối chiếu cho nhóm — file `report/benchmark_runs/*.txt`):

| Chiến lược | Số chunk | Avg ký tự | Q1 | Q2 | Q3 | Q4 | Q5 | Tổng |
|---|---|---|---|---|---|---|---|---|
| FixedSize 700 / overlap 100 (Sang) | 43 | 652 | 2 | 2 | 2 | 2 | 2 | **10/10** |
| Recursive 600 (Hoàng) | 52 | 472 | 1 | 2 | 2 | 1 | 2 | 8/10 |
| **Heading/Section 800 (Phát)** | 54 | 484 | 1 | 2 | 2 | 1 | 2 | 8/10 |
| Sentence 4 câu | 101 | 241 | 1 | 2 | 2 | 0 | 2 | 7/10 |
| *Đối chứng:* FixedSize 500 / overlap 50 | 57 | 473 | 2 | 2 | 2 | 1 | 2 | 9/10 |
| *Đối chứng:* FixedSize 800 / **overlap 0** | 35 | 703 | 2 | 1 | 2 | 1 | 1 | 7/10 |
| *Đối chứng:* Heading `max_chars=1200` | 50 | 517 | 1 | 2 | 2 | 1 | 2 | 8/10 |

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**
> Chiến lược của tôi coherence tốt nhất (0 chunk cắt giữa câu, 0 heading dính) nhưng điểm retrieval thua FixedSize của Sang. Ba run đối chứng cho thấy nguyên nhân **không phải kích thước chunk**: FixedSize 500/50 (cỡ ≈ heading) vẫn 9/10, còn FixedSize 800/**0** (to hơn nhưng không overlap) tụt xuống 7/10 — yếu tố quyết định là **overlap**: một câu ở ranh giới xuất hiện trong hai chunk nên có hai cơ hội lọt top-1, đúng điều tôi đã dự đoán ở Warm-up 1.2. Điểm yếu của heading chunker là các mục **cùng một file** có điểm cosine sát nhau (Q1: 0.839/0.836/0.833) nên mục đúng dễ rơi xuống #2–#3, và tăng `max_chars` lên 1200 không đổi gì vì đơn vị vẫn là mục. Bài học: "mạch lạc" không tự động bằng "truy xuất tốt"; nếu làm lại tôi sẽ lai hai ý — giữ ranh giới mục nhưng thêm overlap (nối 1–2 câu cuối của mục trước vào đầu mục sau). *(Cập nhật thêm sau buổi demo với các nhóm khác.)*

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Khởi động (Warm-up) | 5 / 5 |
| Hướng tiếp cận của tôi (My Approach) | 10 / 10 |
| Hoàn thiện code (Core Implementation — tests) | 30 / 30 |
| Dự đoán độ tương tự (Similarity Predictions) | 5 / 5 |
| Kết quả truy xuất của tôi (Competition Results) | 8 / 10 |
| **Tổng phần cá nhân** | **58 / 60** |
