# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** [Tên nhóm]
**Thành viên:** [Họ tên từng thành viên]
**Ngày:** [Ngày nộp]

> **Nộp 1 bản / nhóm.** Phần cá nhân (hướng tiếp cận, kết quả riêng, dự đoán…) mỗi thành viên nộp riêng trong `REPORT_CANHAN.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần nhóm: 40** = Lựa chọn tài liệu (10) + Thiết kế chiến lược (15) + Chất lượng truy xuất (10) + Thuyết trình (5).

---

## 1. Lựa chọn tài liệu (Document Set Quality) — Nhóm (10 điểm)

### Chủ đề (Domain) & Lý Do Chọn

**Chủ đề:** [ví dụ: Customer support FAQ, Luật Việt Nam, công thức nấu ăn, ...]

**Tại sao nhóm chọn chủ đề này?**
> *Viết 2-3 câu:*

### Danh sách tài liệu (Data Inventory)

| # | Tên tài liệu | Nguồn (Source URL) | Ngày lấy / Phiên bản | Số ký tự | Metadata đã gán |
|---|--------------|------------|--------------------|----------|-----------------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

**Danh sách kiểm tra quản trị dữ liệu (Data governance checklist):**
- [ ] Tập tài liệu (Corpus) chỉ chứa nguồn công khai/được phép dùng và không chứa dữ liệu cá nhân, thông tin đăng nhập hoặc tài liệu nội bộ.
- [ ] Mỗi tài liệu có `source_url`, `retrieved_at`, `document_version` (hoặc ngày hiệu lực) trong metadata.

### Cấu trúc Metadata (Metadata Schema)

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho truy xuất (retrieval)? |
|----------------|------|---------------|-------------------------------|
| | | | |
| | | | |

---

## 2. Thiết kế chiến lược (Strategy Design) — Nhóm (15 điểm)

> Mỗi thành viên thử **một chiến lược khác nhau** trên cùng bộ tài liệu; nhóm tổng hợp và so sánh ở đây.

### Phân tích đường cơ sở (Baseline Analysis)

Chạy `ChunkingStrategyComparator().compare()` trên 2-3 tài liệu:

> **[Phát — R3]** `ChunkingStrategyComparator().compare(body, chunk_size=500)`, frontmatter YAML đã tách trước khi đo; lệnh tái tạo `python bench.py --baseline --baseline-chunk-size 500`. Hai chỉ số coherence đo tự động: *cắt giữa câu* = chunk không kết thúc bằng `. ! ? :`; *heading dính* = có dòng `## …` nằm giữa/cuối chunk (heading bị tách khỏi nội dung của nó). Dòng in nghiêng là chunker theo heading của Phát để đối chiếu.

| Tài liệu | Chiến lược (Strategy) | Số lượng Chunk | Độ dài trung bình | Giữ được ngữ cảnh không? |
|-----------|----------|-------------|------------|-------------------|
| buyer-open-case (3.945 ký tự) | FixedSizeChunker (`fixed_size`) | 9 | 482.9 | Kém — 7/9 cắt giữa câu, 7/9 heading dính giữa chunk |
| | SentenceChunker (`by_sentences`) | 20 | 195.3 | Trung bình — 0/20 cắt giữa câu nhưng chunk ngắn, danh sách điều kiện tách khỏi câu dẫn; 4/20 heading dính |
| | RecursiveChunker (`recursive`) | 10 | 392.9 | Khá — 3/10 cắt giữa câu; 4/10 heading dính vào **cuối chunk trước** (chunk 0 kết thúc bằng "## How to open a case") |
| | *Heading/Section (Phát)* | *8* | *505.6* | *Tốt — 0/8, 0/8; mỗi chunk = 1 mục trọn vẹn* |
| seller-purchase-protection (3.097 ký tự) | FixedSizeChunker | 7 | 485.4 | Kém — 6/7 cắt giữa câu, 3/7 heading dính; list 8 điều kiện eligibility bị cắt đôi |
| | SentenceChunker | 13 | 236.2 | Trung bình — 0/13, 0/13 nhưng list 8 điều kiện rải ra 3 chunk |
| | RecursiveChunker | 9 | 342.6 | Khá — 0/9 cắt giữa câu; 3/9 heading dính |
| | *Heading/Section (Phát)* | *5* | *645.6* | *Tốt — 0/5, 0/5; mục "How do I qualify?" giữ trọn 8 điều kiện* |
| seller-set-return-policy (3.581 ký tự) | FixedSizeChunker | 8 | 491.5 | Kém — 7/8 cắt giữa câu, 6/8 heading dính; các bước 1–9 bị cắt ngang |
| | SentenceChunker | 27 | 130.9 | Trung bình — chunk rất ngắn (131 ký tự), mỗi bước thao tác thành 1 chunk rời |
| | RecursiveChunker | 9 | 396.2 | Khá — 0/9 cắt giữa câu; 5/9 heading dính |
| | *Heading/Section (Phát)* | *7* | *546.3* | *Tốt — 0/7, 0/7* |

**[Phát] Nhận xét baseline:** FixedSize cho chunk đều nhất nhưng phá cấu trúc — gần như mọi chunk cắt giữa câu và heading rơi vào giữa chunk. Sentence giữ trọn câu nhưng chunk quá ngắn, danh sách điều kiện/bước thao tác rải ra nhiều chunk. Recursive cân bằng tốt hơn, song chỉ biết `\n\n` chứ không biết heading nên thường **dính heading vào cuối chunk trước** — mảnh nội dung phía sau mất tiêu đề. Đó là khoảng trống mà chunker theo heading nhắm tới.

### Chiến lược của từng thành viên

> Mỗi thành viên điền một khối dưới đây (copy thêm nếu nhóm có nhiều hơn 3 người).

**Thành viên 1 — [Tên]**
- **Loại chiến lược:** [FixedSize / Sentence / Recursive / custom]
- **Mô tả & lý do chọn cho chủ đề này:** *(2-3 câu)*
- **Code snippet (nếu custom):**
```python
# Dán mã nguồn (implementation) vào đây
```

**Thành viên 2 — [Tên]**
- **Loại chiến lược:**
- **Mô tả & lý do chọn:**
- **Code snippet (nếu custom):**

**Thành viên 3 — Nguyễn Tiến Phát (R3)**
- **Loại chiến lược:** custom — `HeadingChunker` (chunk theo heading/section Markdown; section dài hơn `max_chars` fallback `RecursiveChunker`, gắn lại breadcrumb vào từng mảnh con). Tham số thực tế: `max_chars=800`, `breadcrumb=True` → 54 chunk / 9 file, trung bình 484 ký tự.
- **Mô tả & lý do chọn:** Trang Help Center của Etsy được người soạn chia sẵn thành mục (`## When can I open a case?`, `## How do I qualify?`) — mỗi mục là một đơn vị ngữ nghĩa trọn vẹn: câu hỏi ở heading, đáp án ở thân. Cắt theo mục giữ nguyên "câu hỏi + đáp án" và các danh sách điều kiện/bước thao tác trong cùng chunk (FixedSize cắt đôi, Recursive làm mất heading). Mỗi chunk được gắn breadcrumb `H1 › H2` ở đầu nên tự mang ngữ cảnh "mục này nói về gì", query dạng câu hỏi khớp trực tiếp với heading dạng câu hỏi, và kết quả truy vết được về đúng file + đúng mục (*Source Traceability*). Mục dài hơn 800 ký tự mới hạ xuống Recursive và breadcrumb được gắn lại vào từng mảnh để mảnh thứ hai không mất ngữ cảnh.
- **Code snippet (nếu custom):**
```python
class HeadingChunker:
    HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)

    def __init__(self, max_chars: int = 800, breadcrumb: bool = True) -> None:
        self.max_chars, self.breadcrumb = max_chars, breadcrumb

    def sections(self, text):                      # -> [(đường dẫn heading, thân mục)]
        matches = list(self.HEADING_RE.finditer(text))
        if not matches:
            return [([], text.strip())]
        out, stack = [], []                        # stack = heading cha đang mở [(level, title)]
        if (pre := text[: matches[0].start()].strip()):
            out.append(([], pre))
        for i, m in enumerate(matches):
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out.append(([t for _, t in stack], text[m.end():end].strip()))
        return out

    def chunk(self, text: str) -> list[str]:
        chunks = []
        for path, body in self.sections(text):
            if not body:
                continue
            header = (" › ".join(path) + "\n") if (path and self.breadcrumb) else ""
            if len(header) + len(body) <= self.max_chars:
                chunks.append(header + body)
            else:                                  # section dài: hạ xuống recursive, gắn lại breadcrumb
                for piece in RecursiveChunker(chunk_size=max(200, self.max_chars - len(header))).chunk(body):
                    chunks.append(header + piece)
        return chunks
```

### So Sánh Giữa Các Thành Viên

| Thành viên | Chiến lược (Strategy) | Điểm truy xuất (/10) | Điểm mạnh | Điểm yếu |
|-----------|----------|----------------------|-----------|----------|
| Sang | FixedSize + overlap | *(Sang điền)* | | |
| Hoàng | Recursive | *(Hoàng điền)* | | |
| Phát | Heading/Section (custom) | **8/10** (Q2/Q3/Q5 top-1; Q1 top-3; Q4 top-2) | Coherence cao nhất (0 cắt giữa câu, 0 heading dính); mỗi chunk truy vết về đúng mục; doc-level top-1 cả 5 câu | Các mục **cùng một file** có cosine sát nhau (Q1: 0.839/0.836/0.833) nên mục đúng dễ rơi #2–#3; không có overlap giữa các mục; kích thước chunk không đều |

> **[Phát — R3, số đối chứng]** Để so sánh công bằng tôi chạy cả 4 chiến lược trên **cùng** corpus / 5 query canonical / `gemini-embedding-001` / `top_k=3`, chỉ đổi dòng chọn chunker trong `bench.py` (output: `report/benchmark_runs/*.txt`). Sang/Hoàng thay bằng số chạy trên repo của mình nếu khác.
>
> | Chiến lược | Chunk | Avg ký tự | Q1 | Q2 | Q3 | Q4 | Q5 | Tổng |
> |---|---|---|---|---|---|---|---|---|
> | FixedSize 700/100 | 43 | 652 | 2 | 2 | 2 | 2 | 2 | **10/10** |
> | Recursive 600 | 52 | 472 | 1 | 2 | 2 | 1 | 2 | 8/10 |
> | Heading 800 | 54 | 484 | 1 | 2 | 2 | 1 | 2 | 8/10 |
> | Sentence 4 câu | 101 | 241 | 1 | 2 | 2 | 0 | 2 | 7/10 |
> | *đối chứng* FixedSize 500/50 | 57 | 473 | 2 | 2 | 2 | 1 | 2 | 9/10 |
> | *đối chứng* FixedSize 800/**0** | 35 | 703 | 2 | 1 | 2 | 1 | 1 | 7/10 |

**Chiến lược nào tốt nhất cho chủ đề này? Tại sao?**
> **[Phát — đề xuất, Sang tổng hợp]** Về điểm retrieval, FixedSize có overlap thắng (10/10) và hai run đối chứng chỉ ra yếu tố quyết định là **overlap chứ không phải kích thước chunk**: FixedSize 500/50 (cỡ ≈ heading) vẫn 9/10, còn FixedSize 800 không overlap tụt xuống 7/10 — một câu ở ranh giới xuất hiện trong hai chunk nên có hai cơ hội lọt top-1. Chunker theo heading mạch lạc nhất và truy vết tốt nhất (đúng file 5/5, chunk = đúng mục), nhưng vì các mục cùng file có điểm sát nhau nên mục chứa đáp án không chắc ở top-1 (Q1, Q4). Với corpus chính sách, chiến lược tốt nhất có lẽ là **lai**: giữ ranh giới mục của heading chunker để agent trả lời/ trích dẫn được, và thêm overlap 1–2 câu giữa các mục liền kề để mục đúng không bị "hụt" top-1.

---

## 3. Câu hỏi đánh giá & Chất lượng truy xuất (Retrieval Quality) — Nhóm (10 điểm)

### Câu hỏi đánh giá & Câu trả lời chuẩn (nhóm thống nhất)

> **Đúng 5 câu hỏi**, đa dạng, có thể kiểm chứng; **ít nhất 1 câu** cần lọc metadata mới trả lời tốt. Đây là bộ câu hỏi chung cho mọi thành viên chạy.

| # | Câu hỏi (Query) | Câu trả lời chuẩn (Gold Answer) | Chunk nào chứa thông tin? |
|---|-------|-------------------------------|--------------------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

### Tổng hợp chất lượng truy xuất của nhóm

> Cách chấm (theo `docs/SCORING.md`): **2 điểm/câu** — top-3 chứa chunk liên quan + agent trả lời đúng (2), có liên quan nhưng thiếu/không ở top-1 (1), không có trong top-3 (0).

> **[Phát — từ 4 run cùng embedder; Sang tổng hợp lại với số của Sang/Hoàng]**

| # | Câu hỏi | Chiến lược tốt nhất cho câu này | Có chunk liên quan trong top-3? | Ghi chú |
|---|---------|-------------------------------|-------------------------------|---------|
| 1 | Conditions before a buyer can open a case | FixedSize (top-1) | Có — heading: top-3, recursive: top-2 | Cả top-3 của heading đều từ `buyer-open-case`, điểm 0.839/0.836/0.833 — mục "When can I open a case?" thua mục "How to open a case" (các bước) |
| 2 | Seller resolves case via Shop Manager | Mọi chiến lược (top-1) | Có | Heading: `seller-resolve-case#5` 0.901 — câu "dễ" vì query trùng gần hết heading |
| 3 | Refund amount under Purchase Protection (A/B) | Mọi chiến lược khi có filter | Có (với filter buyer) | **Không filter → top-1 là seller ($250), sai đối tượng**; filter buyer → `buyer-purchase-protection#0` (full refund) |
| 4 | Components of estimated delivery date | FixedSize (top-1) | Có — heading & recursive: top-2; sentence: miss | Mục "How do I *see* the EDD" (0.820) thắng mục "How is the EDD *calculated*" (0.805) |
| 5 | Seller refund process + Etsy Payments limit | Mọi chiến lược (top-1) | Có | Heading: mục "When can I issue a refund?" (180 days) top-1, các bước ở top-2 |

**Lọc bằng metadata có giúp ích không? Ở câu hỏi nào?**
> **[Phát — bằng chứng A/B Q3, heading chunker, gemini-embedding-001]** Không filter: top-1 `seller-purchase-protection#0` (0.847, "$250"), top-2 `seller-returns-refunds#2` (0.842), top-3 `buyer-purchase-protection#0` (0.829, "full refund") → agent trả lời theo góc seller dù gold là buyer. Filter `audience=buyer`: top-1 `buyer-purchase-protection#0` — đúng đối tượng, đúng đáp án; filter `seller`: top-1 `seller-purchase-protection#0`. Filter giúp rõ nhất ở Q3 vì hai tài liệu cùng từ vựng "Purchase Protection" nhưng khác đáp án; ở Q1/Q2/Q4/Q5 filter chủ yếu loại nhiễu (top-3 gọn hơn) chứ không đổi top-1. Đánh đổi: filter cứng theo `audience` sẽ bỏ sót nếu đáp án nằm ở file `both` hoặc file audience khác — corpus này không có trường hợp đó.

---

## 4. Thuyết trình (Demo) & Bài học nhóm — Nhóm (5 điểm)

**Những phân tích (insights) hay nhất nhóm sẽ trình bày:**
> **[Phát đề xuất]** (1) Chấm theo doc_id thổi phồng kết quả: heading chunker đúng file 5/5 (10/10) nhưng chấm theo nội dung chỉ 8/10 — khoảng cách 2 điểm nằm ở "đúng file, sai mục". (2) Overlap là biến quyết định, không phải kích thước chunk (FixedSize 500/50 = 9, 800/0 = 7). (3) Cosine không tách được đối tượng khi từ vựng trùng: cặp "buyer phải chờ 48h" vs "seller phải trả lời trong 48h" được 0.868 — cao hơn cả cặp đồng nghĩa thật (0.800); đó là lý do Q3 cần `metadata_filter`. (4) Mock embedder cho 1/10 với cùng pipeline — benchmark bằng mock là nhiễu.

**Bài học rút ra khi so sánh trong nhóm:**
> **[Phát — failure case Q1/Q4, heading chunker]** *Câu nào hỏng:* Q1 (điều kiện mở case) và Q4 (thành phần tính EDD). *Vì sao:* cả top-3 đều đúng file nhưng mục chứa đáp án đứng #3 (Q1) / #2 (Q4) — các mục trong cùng file cùng chủ đề nên cosine gần bằng nhau (0.839 vs 0.833; 0.820 vs 0.805), và mục "cách làm" (các bước thao tác, nhiều từ khoá) lấn át mục "điều kiện/công thức" ngắn hơn; thêm nữa heading chunker không có overlap nên mỗi thông tin chỉ có đúng một cơ hội lọt top-k. *Đề xuất sửa:* (a) thêm overlap 1–2 câu giữa mục liền kề; (b) rerank top-k theo độ khớp giữa query và **heading** (query "conditions…" ↔ heading "When can I…"); (c) chấm ở mức nội dung/marker thay vì doc_id để không bị đánh lừa.

**Nếu làm lại, nhóm sẽ thay đổi gì trong chiến lược dữ liệu (data strategy)?**
> **[Phát đề xuất]** Giữ corpus là **bản chép nguyên văn** trang nguồn (không rút gọn/diễn đạt lại) để gold answer trích được đúng chữ và heading giữ nguyên tên gốc; chốt **một embedder** cho cả nhóm ngay từ CP2 (mock chỉ để test); và thiết kế query/marker cùng lúc với clean data để mỗi marker chỉ xuất hiện trong đúng một mục — tránh marker quá phổ biến như "Shop Manager" (có trong nhiều file seller) làm chấm content-level dễ dãi.

---

## Tự Đánh Giá (Phần Nhóm)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Lựa chọn tài liệu (Document Set Quality) | / 10 |
| Thiết kế chiến lược (Strategy Design) | / 15 |
| Chất lượng truy xuất (Retrieval Quality) | / 10 |
| Thuyết trình (Demo) | / 5 |
| **Tổng phần nhóm** | **/ 40** |
