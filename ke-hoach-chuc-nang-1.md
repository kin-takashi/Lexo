# KẾ HOẠCH TRIỂN KHAI CHỨC NĂNG 1
## Tra cứu điều luật Việt Nam có lịch sử hiệu lực (chạy cục bộ)

> Tài liệu bàn giao cho phần code. Các con số về dung lượng, RAM là **ước lượng**, cần đo lại khi triển khai. Tên mô hình và phiên bản nên kiểm tra lại trên Hugging Face / Ollama trước khi cài.

---

## 1. Mục tiêu

Người dùng tra một điều luật (bằng số điều hoặc mô tả bằng lời) và nhận được:

1. Nội dung điều luật tại thời điểm hiện hành
2. Dòng thời gian các phiên bản: ban hành, hiệu lực từ ngày nào, sửa đổi bởi văn bản nào, hết hiệu lực khi nào
3. So sánh (diff) giữa các phiên bản
4. Xem điều luật tại một **ngày bất kỳ**
5. Xem quan hệ giữa các văn bản (sửa đổi / thay thế / bãi bỏ)

Phạm vi nội dung: chỉ **tham khảo**, không phải nguồn pháp lý chính thức, không đưa ra kết luận pháp lý.

---

## 2. Chức năng cụ thể

| # | Chức năng | Cách thực hiện |
|---|---|---|
| 1 | Tra chính xác ("Điều 173 BLHS 2015") | Truy vấn SQL theo metadata |
| 2 | Tìm theo mô tả bằng lời | Hybrid search: FTS5 (BM25) + vector, gộp bằng RRF |
| 3 | Dòng thời gian của một điều | Danh sách phiên bản kèm hiệu lực từ/đến và văn bản nguồn |
| 4 | So sánh hai phiên bản | Tính diff lúc truy vấn (không lưu sẵn) |
| 5 | Xem điều luật tại ngày X | Lọc phiên bản có `hieu_luc_tu <= X < hieu_luc_den` |
| 6 | Xem quan hệ văn bản | Truy vấn bảng quan hệ |

---

## 3. Kiến trúc tổng thể

```
NGUỒN VÀO (hai cổng)
  [A] Crawler web (tool thường, KHÔNG dùng LLM)
  [B] Upload file Word/PDF từ máy
        │
        ▼
Trích xuất text thuần (python-docx cho .docx; thư viện PDF; OCR nếu là bản scan)
        │
        ▼
LLM đọc hiểu qua API  ──►  JSON có cấu trúc:
   - metadata văn bản (số hiệu, loại, ngày ban hành, ngày hiệu lực)
   - cấu trúc Chương/Điều/Khoản/Điểm
   - các lệnh sửa đổi (điều nào, khoản nào, thao tác, nội dung mới)
        │
        ▼
NGƯỜI DUYỆT (bắt buộc): đối chiếu văn bản gốc và kết quả trích xuất, sửa tay nếu sai
        │
        ▼
CODE (xác định, không dùng LLM): áp lệnh sửa đổi, sinh phiên bản mới,
   đóng khoảng hiệu lực cũ, mở khoảng mới
        │
        ▼
LOCAL: tính embedding, ghi SQLite (+ FTS5 + sqlite-vec)
        │
        ▼
LOCAL: mọi truy vấn của người dùng
```

### Nguyên tắc thiết kế (bắt buộc giữ)

1. **LLM chỉ đọc hiểu và trích xuất ra JSON.** Không để LLM tự viết lại nguyên văn điều luật rồi ghi vào kho. Việc áp sửa đổi, tính khoảng hiệu lực, tính diff là **code xác định** làm.
2. **Mọi thứ vào kho đều qua người duyệt.** Đây là dữ liệu pháp lý, một lỗi trích xuất sẽ nằm im và cho kết quả sai về sau.
3. **Ghi nguồn cho mọi bản ghi**: file gốc nào, mô hình nào (tên + phiên bản), ngày nạp, ai duyệt.
4. **Tách dữ liệu thô khỏi dữ liệu đã xử lý.** Giữ nguyên file gốc trong thư mục `raw/`, để sửa parser thì chạy lại mà không phải tải lại.
5. **Tách cấu hình mô hình khỏi logic code** (tên mô hình, địa chỉ API, mức lượng tử hóa nằm trong file cấu hình), để đổi mô hình chỉ là sửa một dòng.
6. **Điều luật đã bãi bỏ vẫn giữ trong kho** (đóng khoảng hiệu lực), không xóa.

---

## 4. Phân chia local và API

| Bước | Chạy ở đâu | Lý do |
|---|---|---|
| Cào web | Tool thường, local | Không liên quan LLM |
| Upload/đọc file Word, PDF | Local | |
| Đọc hiểu, trích xuất (LLM) | **API** (chính), hoặc local Qwen làm phương án thay thế | Một lần cho mỗi văn bản, cần độ chính xác cao, dữ liệu công khai nên rủi ro riêng tư thấp |
| Embedding | **Local** | Nhẹ, không cần API |
| Lưu trữ, tìm kiếm, diff, xem theo ngày | **Local** | Toàn bộ vận hành của người dùng không phụ thuộc mạng |

Chỉ có **một điểm chạm API duy nhất** (bước đọc hiểu), không liên tục, dữ liệu công khai.

---

## 5. Lựa chọn công nghệ

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python | Theo môi trường hiện có |
| Kho dữ liệu | **SQLite** + FTS5 + **sqlite-vec** | Một file duy nhất, dễ sao lưu, dễ nộp kèm luận văn |
| Embedding | **bge-m3** (mặc định), thử thêm multilingual-e5, bi-encoder tiếng Việt dựa trên PhoBERT, Qwen3-Embedding | Chọn theo Recall@k đo trên bộ câu hỏi của bạn |
| Rerank (giai đoạn sau) | bge-reranker-v2-m3 | Chỉ thêm nếu hybrid chưa đủ tốt |
| Đọc file | python-docx, thư viện PDF, OCR nếu cần | |
| Tách từ / NER tiếng Việt | underthesea hoặc VnCoreNLP | Dùng khi làm bước che thông tin ở chức năng 2 |
| LLM đọc hiểu | API (Claude hoặc tương đương) | Ép đầu ra JSON theo schema |
| LLM local (thay thế / thử nghiệm) | **Qwen3-8B** (khởi đầu), lên **Qwen3-14B** rồi **32B** khi có điều kiện | Qwen3 **không có cỡ 7B**; chạy qua Ollama; mức lượng tử hóa Q5_K_M hoặc Q6_K nếu dư bộ nhớ, Q4_K_M nếu cần tiết kiệm |
| Tìm kiếm gần đúng (ANN) | Chưa cần ở quy mô này | Brute-force đủ nhanh; HNSW của sqlite-vec là phương án mở rộng |

### Lưu ý khi dùng Qwen3 local
- Qwen3 có **chế độ thinking**. Với việc trích xuất JSON, cần **tắt thinking** hoặc tách phần suy luận ra trước khi parse JSON, nếu không sẽ hỏng bước parse.
- Đổi từ Qwen2.5 sang Qwen3 là đổi cả thế hệ: **chạy lại bộ đánh giá** trước khi thay hẳn, đừng giả định prompt cũ cho kết quả y hệt.
- Đổi cỡ trong cùng một họ (8B lên 14B lên 32B) **không cần train lại**, chỉ đổi tên mô hình trong cấu hình.

---

## 6. Thiết kế cơ sở dữ liệu (một file SQLite)

**van_ban**
- id, so_hieu, ten, loai (luật / bộ luật / nghị định / nghị quyết...), ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc, trang_thai, nguon (URL hoặc tên file), file_goc (đường dẫn trong `raw/`), ngay_nap

**dieu**
- id, van_ban_id, so_dieu, tieu_de, chuong, muc (metadata cha để giữ ngữ cảnh)

**phien_ban_dieu**
- id, dieu_id, noi_dung, hieu_luc_tu, hieu_luc_den (NULL nếu còn hiệu lực), van_ban_tao_ra_id (văn bản sinh ra phiên bản này), mo_hinh_trich_xuat, nguoi_duyet, ngay_duyet, embedding

**quan_he_van_ban**
- id, van_ban_a_id, loai_quan_he (sua_doi / bo_sung / thay_the / bai_bo), van_ban_b_id, dieu_bi_tac_dong

**Bảng chỉ mục**
- `fts` (FTS5) trỏ vào `phien_ban_dieu.noi_dung` (+ tiêu đề, số điều)
- `vec` (sqlite-vec) chứa embedding của `phien_ban_dieu`

**Cấu trúc thư mục gợi ý**
```
project/
  config.yaml          # tên mô hình, API endpoint, đường dẫn
  raw/                 # file gốc (Word/PDF/HTML), không sửa
  inbox/               # file mới chờ nạp
  db/luat.sqlite
  src/
    ingest/            # crawler, upload, trích xuất text
    extract/           # gọi LLM, schema JSON, prompt
    review/            # giao diện duyệt
    apply/             # áp lệnh sửa đổi, dựng phiên bản (code xác định)
    index/             # embedding, FTS, vector
    query/             # tra chính xác, hybrid, theo ngày, diff
  eval/                # bộ câu hỏi và script đánh giá
```

---

## 7. Truy vấn

- **Tra chính xác**: parse "Điều 173 BLHS 2015" thành (số điều, luật, năm) rồi truy vấn SQL. Không cần mô hình.
- **Hybrid**: chạy FTS5 (BM25) và vector song song, gộp bằng Reciprocal Rank Fusion, tùy chọn rerank. Luôn **lọc theo ngày hiệu lực** để không trả về phiên bản đã hết hiệu lực (trừ khi người dùng chọn xem lịch sử).
- **Xem theo ngày**: lấy phiên bản có `hieu_luc_tu <= X < hieu_luc_den`.
- **Diff**: tính lúc truy vấn bằng thư viện diff, không lưu sẵn.
- **Cần kiểm soát**: câu hỏi và tài liệu phải qua **cùng một mô hình embedding** (và đúng tiền tố "query:"/"passage:" nếu dùng e5).

---

## 8. Quy trình nạp văn bản mới (cập nhật thủ công)

1. Bỏ file (Word/PDF) vào `inbox/`, hoặc chạy crawler
2. Trích xuất text thuần, lưu file gốc vào `raw/`
3. Chia văn bản theo **Điều/Chương** (không nhét cả bộ luật vào một lần gọi)
4. Gọi LLM (API), ép JSON theo schema
5. Hiển thị **hai cột**: văn bản gốc và kết quả trích xuất; người duyệt sửa tay rồi bấm lưu
6. Code áp lệnh sửa đổi lên phiên bản cũ, đóng/mở khoảng hiệu lực
7. Tính embedding cho các phiên bản mới, ghi vào kho
8. Ghi log: file nguồn, mô hình, người duyệt, ngày

**Lộ trình nạp dữ liệu (theo tầng)**
- Tầng 1: các bộ luật lớn (BLHS 2015, BLDS 2015, BLTTHS, BLTTDS...) và văn bản sửa đổi của chúng
- Tầng 2: nghị quyết hướng dẫn của Hội đồng Thẩm phán TANDTC và một số nghị định thường gặp
- Tầng 3: mở rộng dần

Nguồn nên ưu tiên: **vbpl.vn** (chính thống, có lược đồ quan hệ văn bản), công báo. Với trang thương mại (thuvienphapluat.vn) cần xem điều khoản sử dụng và bản quyền trước khi thu thập. Với crawler: có độ trễ giữa các request, ghi log, kiểm tra `robots.txt`.

---

## 9. Yêu cầu phần cứng

Con số là ước lượng, đo lại khi chạy thật.

### 9.1 Cấu hình tối thiểu (dùng API cho đọc hiểu, local chỉ chạy embedding + SQLite)
| Thành phần | RAM ước lượng |
|---|---|
| bge-m3 (embedding) | ~1.2GB |
| bge-reranker-v2-m3 (nếu dùng) | ~1.2GB |
| underthesea / VnCoreNLP | ~0.3–0.5GB |
| SQLite + sqlite-vec (dữ liệu vài chục nghìn vector) | vài trăm MB |
| Ứng dụng + hệ điều hành | tùy máy |

Tổng phần AI local khoảng **3–4GB**. Chạy được cả bằng **CPU**, GPU không bắt buộc (embedding cho vài chục nghìn đoạn vẫn xong trong thời gian chấp nhận được, chỉ chậm hơn khi nạp lần đầu).

### 9.2 Nếu chạy thêm LLM local (Qwen3 qua Ollama)
| Mô hình chính (Q4_K_M) | RAM/VRAM ước lượng | Tổng với phụ trợ |
|---|---|---|
| Qwen3-8B | ~5–7GB | ~8–10GB |
| Qwen3-14B | ~9–11GB | ~12–14GB |
| Qwen3-32B | ~19–22GB | ~22–25GB |

- Q5_K_M / Q6_K tốn thêm khoảng 15–35% so với Q4_K_M
- Ngữ cảnh dài làm tăng thêm (KV cache): 32k token có thể thêm vài GB. Cách tiết kiệm: chia văn bản theo Điều/Chương
- Chạy CPU thuần được nhưng chậm; có GPU thì trọng số nằm ở VRAM

**Khuyến nghị RAM máy:** 16GB là tối thiểu thực tế cho 8B/14B chạy cùng phụ trợ; 32GB thoải mái hơn. Với phương án chỉ dùng API cho đọc hiểu, 8GB đã đủ cho phần local.

### 9.3 Dung lượng ổ đĩa (ước lượng)
| Thành phần | Dung lượng |
|---|---|
| File Word gốc (các bộ luật cốt lõi + sửa đổi + hướng dẫn) | ~25–90MB |
| File SQLite (text + FTS5 + vector, ~20.000 phiên bản điều) | ~150–250MB |
| Mở rộng lớn (50.000–100.000 phiên bản) | ~500MB–1GB |
| Nếu lấy toàn bộ nghị định, thông tư (hàng chục nghìn văn bản) | ~2–6GB dữ liệu thô |
| Trọng số mô hình embedding | ~1–2.5GB mỗi mô hình |
| Trọng số Qwen3 lượng tử hóa | 8B ~5GB, 14B ~9GB, 32B ~20GB |

### 9.4 Mạng
- Cần mạng cho: bước gọi API đọc hiểu, crawler, tải mô hình lần đầu
- **Không cần mạng** cho: mọi truy vấn của người dùng cuối

---

## 10. Cách đánh giá (số liệu cho luận văn)

| Tác vụ | Chỉ số |
|---|---|
| Tra cứu điều luật từ câu hỏi bằng lời | Recall@k (k = 1, 5, 10), MRR, nDCG@k; so sánh FTS riêng / vector riêng / hybrid, và giữa các mô hình embedding |
| Hiệu lực theo thời gian ("Điều X ngày Y nội dung gì?") | Accuracy (so khớp chính xác); báo cáo riêng các ca sát mốc chuyển giao |
| Trích xuất lệnh sửa đổi | Precision/Recall/F1 theo từng lệnh; độ chính xác từng trường (số điều, số khoản, loại thao tác); exact match cho nội dung mới; **tỉ lệ không cần sửa tay** |
| Quan hệ văn bản | Accuracy, Macro-F1, confusion matrix |

- Bộ câu hỏi tra cứu: tự đặt 50–100 câu kèm điều luật đúng (gán nhãn tay, nhờ thêm một người kiểm chéo một phần)
- Nhãn cho hiệu lực theo thời gian và trích xuất sửa đổi **sinh gần như tự động** từ chính kho đã duyệt, kiểm tay một mẫu nhỏ
- Tách tập dev và test; có baseline (chỉ BM25; trích xuất bằng regex)
- Thực nghiệm đáng làm: so sánh cỡ mô hình (8B / 14B / 32B) và mức lượng tử hóa (Q4 / Q5 / Q6 / Q8), đo kèm RAM và độ trễ thực; so mô hình local với API "giáo viên"

### Đóng góp phụ (tùy chọn): công bố dataset
Xuất kho thành corpus có cấu trúc (JSONL/Parquet) kèm datasheet: nguồn, phạm vi, ngày chốt, giới hạn. Điểm khác biệt: **có phiên bản theo thời gian và quan hệ sửa đổi**. Cần kiểm tra bản quyền/nguồn và chia tập tránh rò rỉ. Công bố qua Hugging Face Datasets hoặc Zenodo.

### Hướng mở rộng (nếu còn thời gian): distillation
Dùng API làm "giáo viên" tạo cặp (văn bản → JSON đã duyệt), rồi fine-tune Qwen local bằng LoRA/QLoRA. Bộ cặp đã duyệt vừa là dữ liệu huấn luyện vừa là dữ liệu đánh giá. Cần đủ dữ liệu (vài trăm ví dụ trở lên) và GPU cho fine-tune.

---

## 11. Kế hoạch làm theo thứ tự

| Bước | Việc | Kết quả kiểm tra được |
|---|---|---|
| 1 | Dựng schema SQLite; nạp **một** bộ luật hoàn chỉnh (đề xuất BLHS 2015) bằng cách trích xuất + duyệt | Tra chính xác "Điều X" chạy được |
| 2 | Nạp văn bản sửa đổi của bộ luật đó; làm luồng LLM đọc + duyệt + dựng phiên bản | Xem theo ngày, dòng thời gian, diff chạy được |
| 3 | Thêm FTS5, embedding, sqlite-vec; hybrid search | Tìm theo mô tả bằng lời chạy được |
| 4 | Xây bộ câu hỏi đánh giá; đo Recall@k, MRR; so sánh mô hình embedding | Bảng kết quả thực nghiệm |
| 5 | Thêm giao diện (web hoặc chat) chỉ hỗ trợ tra cứu luật và phân tích câu hỏi | Bản demo end-to-end |
| 6 | Mở rộng sang các bộ luật khác, nghị quyết hướng dẫn | Kho lớn dần |
| 7 | (Tùy chọn) so sánh local và API, distillation, công bố dataset | Đóng góp mở rộng |

Mỗi bước cho ra một bản chạy được để trình thầy.

---

## 12. Agent chat (giao diện)

Phạm vi hẹp: chỉ trả lời dựa trên kho luật và phân tích câu hỏi đầu vào.

```
Câu người dùng
  → (1) Phân loại ý định: tra chính xác / tìm theo mô tả / xem theo ngày / so sánh / ngoài phạm vi
  → (2) Trích tham số: tên luật, số điều, ngày, mô tả tình huống   (ép JSON)
  → (3) Gọi công cụ truy vấn kho (code, không phải LLM)
  → (4) Sinh câu trả lời CHỈ dựa trên kết quả trả về, kèm trích dẫn điều luật
```

- Ràng buộc: **chỉ trình bày nội dung điều luật lấy từ kho**, không tự nhớ điều luật từ mô hình
- Từ chối lịch sự các câu ngoài phạm vi
- Luôn kèm cảnh báo: thông tin tham khảo, không phải tư vấn pháp lý
- Hiển thị **ngày cập nhật kho lần cuối** trên giao diện
- Bước (1) và (2) là bài toán nhỏ, mô hình cỡ nhỏ là đủ; bước (4) dùng mô hình lớn hơn nếu có

---

## 13. Rủi ro và giới hạn cần ghi rõ

- Kho chỉ đầy đủ đến mức đã nạp
- Phiên bản cũ của điều luật là **bản dựng lại** từ văn bản sửa đổi, cần ghi nguồn để truy vết
- LLM có thể đọc sai số điều/ngày; **bước người duyệt là biện pháp chính**, không được bỏ
- Mô hình local nhỏ dễ bịa điều luật nếu không ràng buộc chặt theo kết quả truy xuất
- Lượng tử hóa mạnh có thể làm mô hình diễn đạt lại thay vì chép nguyên văn: với bước trích xuất cần khớp chữ, **thử Q5/Q6/Q8 trên cùng mô hình** và so tỉ lệ khớp nguyên văn
- Bản quyền và điều khoản sử dụng của nguồn dữ liệu: ưu tiên nguồn chính thống, kiểm tra trước khi cào hàng loạt
- Thư viện Python: dùng môi trường ảo, khóa phiên bản trong `requirements.txt` để thực nghiệm tái lập được

---

## 14. Các điểm còn để mở (chốt khi bắt đầu code)

1. Chọn API cụ thể cho bước đọc hiểu, và xác nhận điều khoản dữ liệu của nhà cung cấp
2. Cấu hình máy thực tế (RAM, có GPU hay không) để chốt cỡ Qwen3 local
3. Phạm vi "full bộ luật" cuối cùng cho luận văn (đề xuất: luật cốt lõi + nghị quyết hướng dẫn, mở rộng dần)
4. Mô hình embedding chọn sau thực nghiệm
5. Giao diện: web đơn giản hay chat
6. Nhắm mục tiêu công bố (luận văn, hội nghị hay tạp chí) để quyết định mức đầu tư cho phần dataset và đánh giá
