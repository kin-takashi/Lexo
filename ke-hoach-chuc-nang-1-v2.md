# KẾ HOẠCH TRIỂN KHAI CHỨC NĂNG 1 (v2)
## Tra cứu điều luật Việt Nam có lịch sử hiệu lực (chạy cục bộ)

> Bản v2 — sửa theo review kỹ thuật. Các thay đổi so với v1 được đánh dấu **[SỬA]**. Con số về dung lượng, RAM vẫn là ước lượng. Ngày tháng cụ thể của văn bản pháp luật (ví dụ mốc hiệu lực BLHS 2015) cần tự kiểm lại trên vbpl.vn trước khi đưa vào báo cáo — không lấy nguyên văn từ tài liệu này.

---

## 0. Các quyết định đã chốt ở bản v2

| Vấn đề | Quyết định |
|---|---|
| Đơn vị lưu trữ nhỏ nhất | **Điểm** (a, b, c...) là đơn vị nhỏ nhất có phiên bản và hiệu lực riêng; Điều/Khoản không có Điểm thì chính chúng là đơn vị lá |
| LLM có được chép nguyên văn để ghi vào kho không | **Không.** Nội dung gốc do **code parse bằng regex** từ văn bản luật. LLM chỉ trả **lệnh sửa đổi** (metadata + thao tác), không trả lại nguyên văn điều luật hiện hành |
| Bước 4 của agent (sinh câu trả lời cho câu hỏi mô tả tự do) | Dùng **LLM local nhỏ** diễn giải, bị ràng buộc chỉ dùng nội dung đã truy xuất từ kho — không gọi API, giữ cam kết offline cho người dùng cuối |
| Đối chiếu độc lập với văn bản hợp nhất chính thức | Làm cho **bộ luật thử nghiệm đầu tiên** (BLHS 2015) để làm bằng chứng phương pháp đúng, không bắt buộc cho toàn bộ dữ liệu |

---

## 1. Mục tiêu

Người dùng tra một điều luật (bằng số điều hoặc mô tả bằng lời) và nhận được:

1. Nội dung điều luật tại thời điểm hiện hành (dựng từ Điều/Khoản/Điểm)
2. Dòng thời gian các phiên bản ở mức Điểm/Khoản: ban hành, hiệu lực từ ngày nào, sửa đổi bởi văn bản nào, hết hiệu lực khi nào
3. So sánh (diff) giữa các phiên bản
4. Xem điều luật tại một **ngày bất kỳ**
5. Xem quan hệ giữa các văn bản (sửa đổi / bổ sung / thay thế / bãi bỏ / hoãn hiệu lực / hướng dẫn / đình chỉ)

Phạm vi nội dung: chỉ **tham khảo**, không phải nguồn pháp lý chính thức, không đưa ra kết luận pháp lý.

---

## 2. Chức năng cụ thể

| # | Chức năng | Cách thực hiện |
|---|---|---|
| 1 | Tra chính xác ("Điều 173 BLHS 2015") | Truy vấn SQL theo `ten_viet_tat` + `so_dieu` |
| 2 | Tìm theo mô tả bằng lời | Hybrid search: FTS5 (BM25) + vector, gộp bằng RRF, **lọc theo ngày hiệu lực trước khi tính khoảng cách vector** |
| 3 | Dòng thời gian của một Điều/Khoản/Điểm | Danh sách phiên bản kèm hiệu lực từ/đến và văn bản nguồn |
| 4 | So sánh hai phiên bản | Tính diff lúc truy vấn (không lưu sẵn) |
| 5 | Xem điều luật tại ngày X | `hieu_luc_tu <= X AND (hieu_luc_den IS NULL OR X < hieu_luc_den)` **[SỬA — v1 sai logic NULL]** |
| 6 | Xem quan hệ văn bản | Truy vấn bảng `quan_he_van_ban` |

---

## 3. Kiến trúc tổng thể **[SỬA — tách rõ vai trò LLM vs code]**

```
NGUỒN VÀO (hai cổng)
  [A] Crawler web (tool thường, KHÔNG dùng LLM)
  [B] Upload file Word/PDF từ máy
        │
        ▼
Trích xuất text thuần (python-docx, thư viện PDF, OCR nếu cần)
        │
        ▼
CODE (regex, xác định): parse cấu trúc Chương/Điều/Khoản/Điểm
   từ văn bản GỐC (luật ban hành lần đầu) → dựng cây đơn vị luật
   + nội dung lá — KHÔNG qua LLM cho bước này
        │
        ▼
Với VĂN BẢN SỬA ĐỔI: LLM đọc hiểu qua API
   → CHỈ xuất lệnh sửa đổi (JSON): đơn vị bị tác động, loại thao tác,
     nội dung mới (nếu có), KHÔNG xuất lại toàn bộ cấu trúc luật gốc
        │
        ▼
VALIDATOR TỰ ĐỘNG (code, chạy trước khi hiển thị người duyệt):
   - số điều liên tục, không nhảy cóc bất thường
   - ngày hợp lệ (hiệu lực không sớm hơn ban hành)
   - lệnh trỏ tới đơn vị (điều/khoản/điểm) có tồn tại trong kho
   - nội dung mới đối chiếu khớp nguyên văn nguồn → gắn cờ nếu không khớp
        │
        ▼
NGƯỜI DUYỆT (bắt buộc): xem cờ cảnh báo của validator, đối chiếu văn bản
   gốc và lệnh trích xuất, sửa tay nếu sai, duyệt hoặc từ chối
        │
        ▼
CODE (xác định): áp lệnh đã duyệt lên đơn vị cũ, sinh phiên bản mới,
   đóng khoảng hiệu lực cũ, mở khoảng mới, ghi lenh_sua_doi
        │
        ▼
LOCAL: tính embedding, ghi SQLite (+ FTS5 + sqlite-vec)
        │
        ▼
LOCAL: mọi truy vấn của người dùng (tra cứu). Câu hỏi mô tả tự do
   dùng thêm LLM local nhỏ để phân loại ý định / diễn giải kết quả —
   vẫn không cần mạng.
```

### Nguyên tắc thiết kế (bắt buộc giữ)

1. **LLM không chép lại nguyên văn luật để ghi vào kho.** Với văn bản gốc, nội dung do **code regex** parse trực tiếp. Với văn bản sửa đổi, LLM chỉ xuất **lệnh sửa đổi có cấu trúc** (đơn vị bị tác động + thao tác + nội dung mới nếu có); việc áp lệnh, tính khoảng hiệu lực, tính diff là code xác định làm. **[SỬA — v1 mâu thuẫn giữa việc bắt LLM xuất cấu trúc và cấm LLM viết lại nguyên văn]**
2. **Mọi lệnh sửa đổi đều qua validator tự động rồi mới đến người duyệt.**
3. **Ghi nguồn cho mọi bản ghi**: file gốc nào, mô hình nào (tên + phiên bản), ngày nạp, ai duyệt — lưu trong `lenh_sua_doi` và `log_nap`.
4. **Tách dữ liệu thô khỏi dữ liệu đã xử lý.** Giữ nguyên file gốc trong `raw/`.
5. **Tách cấu hình mô hình khỏi logic code** (tên mô hình, API endpoint trong file cấu hình, **API key trong `.env`, không trong `config.yaml`** — xem mục 6).
6. **Đơn vị luật đã bãi bỏ vẫn giữ trong kho** (đóng khoảng hiệu lực), không xóa.
7. **Đối chiếu độc lập với văn bản hợp nhất chính thức** cho bộ luật thử nghiệm đầu tiên (mục 10).

---

## 4. Phân chia local và API

| Bước | Chạy ở đâu | Lý do |
|---|---|---|
| Cào web | Tool thường, local | Không liên quan LLM |
| Parse cấu trúc văn bản gốc (Chương/Điều/Khoản/Điểm) | **Code (regex), local** | Tiêu đề luật Việt Nam rất đều, không cần LLM, giảm mạnh khối lượng duyệt tay |
| Đọc hiểu văn bản **sửa đổi** → lệnh sửa đổi | **API** (chính), Qwen local làm phương án thay thế/thử nghiệm | Cần độ chính xác cao cho bước quan trọng nhất; dữ liệu công khai nên rủi ro riêng tư thấp |
| Validator tự động | Code, local | Trước khi đưa ra người duyệt |
| Embedding | Local | Nhẹ, không cần API |
| Lưu trữ, tìm kiếm, diff, xem theo ngày | Local | Toàn bộ vận hành của người dùng không phụ thuộc mạng |
| Agent — bước 1,2 (phân loại ý định, trích tham số) | **LLM local nhỏ** (1.7B–4B) | Việc nhỏ, không cần API |
| Agent — bước 4, khi tra chính xác | **Không dùng LLM** — trả nguyên văn + trích dẫn, format bằng code | Giữ cam kết offline tuyệt đối cho tra cứu chính xác |
| Agent — bước 4, khi câu hỏi mô tả tự do cần diễn giải | **LLM local nhỏ**, ràng buộc chỉ dùng nội dung đã truy xuất | Vẫn offline; không gọi API lúc người dùng truy vấn **[SỬA — v1 để agent gọi API ở bước truy vấn, vỡ cam kết "một điểm chạm API"]** |

Điểm chạm API chỉ còn ở **bước đọc hiểu văn bản sửa đổi lúc nạp dữ liệu** — không liên tục, không xảy ra lúc người dùng cuối truy vấn.

---

## 5. Tập thao tác sửa đổi (bổ sung — v1 chưa liệt kê) **[SỬA]**

| Mã thao tác | Ý nghĩa | Trường cần |
|---|---|---|
| `sua_doi` | Thay nội dung một Khoản/Điểm đã tồn tại | đơn vị đích, nội dung mới |
| `bo_sung` | Thêm Khoản/Điểm mới | đơn vị cha, vị trí chèn, nội dung mới |
| `bai_bo` | Xóa hiệu lực một Điều/Khoản/Điểm | đơn vị đích |
| `thay_cum_tu` | Thay cụm từ "A" bằng "B" trong một hoặc nhiều đơn vị (rất phổ biến trong luật sửa đổi) | cụm từ cũ, cụm từ mới, phạm vi áp dụng (một điều / toàn luật) |
| `danh_so_lai` | Đánh số lại Khoản/Điểm khi có chèn hoặc xóa | đơn vị cha, ánh xạ số cũ → số mới |
| `hoan_hieu_luc` | Hoãn ngày có hiệu lực của một văn bản/điều (dùng nghị quyết riêng) | văn bản/đơn vị đích, ngày hiệu lực mới |

Mọi lệnh có trường **`noi_dung_moi`** đều được validator đối chiếu khớp nguyên văn với văn bản nguồn (mục 3), gắn cờ `khop_nguyen_van = false` nếu không khớp để người duyệt chú ý trước.

---

## 6. Lựa chọn công nghệ

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Ngôn ngữ | **Python 3.10.x**, Windows **[SỬA — v1 chỉ ghi "theo môi trường hiện có"]** | Ghim phiên bản trong `requirements.txt` để tái lập được |
| Kho dữ liệu | **SQLite** + FTS5 + **sqlite-vec** | Một file, dễ sao lưu; **kiểm tra sớm** việc Python `sqlite3` trên Windows có bật `enable_load_extension` không — sqlite-vec còn ở bản 0.x, chưa ổn định lâu dài **[SỬA]** |
| Phương án dự phòng vector search | **numpy brute-force** nếu sqlite-vec không load được | Ở quy mô vài chục nghìn vector vẫn đủ nhanh |
| Embedding | bge-m3 (mặc định), thử multilingual-e5, bi-encoder tiếng Việt (PhoBERT), Qwen3-Embedding | Chọn theo Recall@k đo trên bộ câu hỏi |
| Rerank (giai đoạn sau) | bge-reranker-v2-m3 | Chỉ thêm nếu hybrid chưa đủ tốt |
| Đọc file | python-docx, thư viện PDF, OCR nếu cần | |
| LLM đọc hiểu văn bản sửa đổi | API (Claude hoặc tương đương) | Chỉ trả lệnh sửa đổi dạng JSON, không trả lại nguyên văn luật |
| LLM local (agent bước 1,2,4; hoặc phương án thay thế cho trích xuất) | **Qwen3-8B** | **[SỬA]** Với GPU 8GB VRAM: Qwen3-14B Q4 (~9GB) **không nằm gọn trong VRAM**, 32B càng không. 8B là mức chính khả thi chạy hoàn toàn trên GPU này; 14B/32B chỉ dùng được nếu offload một phần lên CPU (chậm) hoặc qua API |
| Tìm kiếm gần đúng (ANN) | Chưa cần ở quy mô này | HNSW của sqlite-vec là phương án mở rộng khi dữ liệu lớn |
| Bí mật (API key) | **`.env`**, không để trong `config.yaml` | `.gitignore` chặn `.env`, `raw/`, `db/` **[SỬA]** |

### Ghi chú GPU 8GB VRAM
Lộ trình "8B → 14B → 32B" trong bản v1 cần ghi rõ giới hạn: trên máy GPU 8GB, **chỉ 8B chạy gọn local**. Muốn thử 14B/32B để so sánh chất lượng cho luận văn, cần chạy qua API tương đương (nếu nhà cung cấp có sẵn) hoặc thuê GPU rời — không giả định máy hiện tại tự nâng cấp được.

---

## 7. Thiết kế cơ sở dữ liệu (một file SQLite) **[SỬA — thiết kế lại toàn bộ theo cây phân cấp]**

### 7.1 Văn bản

**van_ban**
- id, so_hieu, **ten_viet_tat** (BLHS, BLDS... — bắt buộc, tra chính xác cần cột này), ten_day_du, loai (luật / bộ luật / nghị định / nghị quyết...), ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc, **trang_thai** (`con_hieu_luc` / `het_hieu_luc` / `chua_co_hieu_luc` / `het_hieu_luc_mot_phan`), nguon, file_goc, ngay_nap

### 7.2 Cây đơn vị luật (thay cho bảng `dieu` phẳng ở v1)

**don_vi_luat** — một node trong cây Chương → Điều → Khoản → Điểm
- id, van_ban_id, cha_id (NULL nếu là Điều gốc, ngược lại trỏ đơn vị cha)
- loai (`chuong` / `muc` / `dieu` / `khoan` / `diem`)
- ky_hieu — **TEXT**, không phải số (ví dụ "173", "173a", "2", "a") **[SỬA — v1 dùng kiểu số cho so_dieu]**
- tieu_de (chỉ Điều mới có, có thể NULL)
- thu_tu (để sắp xếp hiển thị)

**phien_ban_noi_dung** — chỉ gắn vào node **lá** (Điều không chia Khoản, hoặc Khoản không chia Điểm, hoặc Điểm)
- id, don_vi_id (FK → don_vi_luat)
- noi_dung
- hieu_luc_tu, hieu_luc_den (NULL nếu là phiên bản hiện hành; quy ước: `hieu_luc_den` = ngày `hieu_luc_tu` của phiên bản kế tiếp) **[SỬA — ghi rõ quy ước, v1 chỉ ngụ ý]**
- van_ban_tao_ra_id (văn bản/lệnh sinh ra phiên bản này)
- mo_hinh_trich_xuat (tên + phiên bản mô hình, nếu do LLM hỗ trợ; NULL nếu do code regex parse từ văn bản gốc)
- **doi_chieu_hop_nhat** (khớp / không khớp / chưa đối chiếu — kết quả so với văn bản hợp nhất chính thức, mục 10)
- nguoi_duyet, ngay_duyet

**Không có cột `embedding` riêng** — bỏ trùng lặp với bảng `vec` **[SỬA]**. Vector nằm trong bảng `vec` (sqlite-vec), khóa bằng `rowid = phien_ban_noi_dung.id`.

### 7.3 Lệnh sửa đổi (bảng mới, v1 thiếu) **[SỬA]**

**lenh_sua_doi** — lưu MỌI lệnh đã trích xuất, kể cả trước khi duyệt; đây là bảng dùng để truy vết, chạy lại khi sửa code áp lệnh, và làm nhãn đánh giá trực tiếp (không vòng tròn, vì nó ghi lại quyết định của người duyệt, không phải suy ra ngược từ kho)
- id, van_ban_nguon_id (văn bản chứa lệnh này)
- don_vi_id (đơn vị đích — NULL nếu là `bo_sung` tạo đơn vị hoàn toàn mới)
- loai_thao_tac (theo mục 5: `sua_doi` / `bo_sung` / `bai_bo` / `thay_cum_tu` / `danh_so_lai` / `hoan_hieu_luc`)
- vi_tri_moi (dùng cho `bo_sung`)
- cum_tu_cu, cum_tu_moi (dùng cho `thay_cum_tu`)
- noi_dung_moi_llm (nguyên văn LLM trả về, giữ lại để đối chiếu)
- **khop_nguyen_van** (boolean — kết quả validator tự động)
- trang_thai_duyet (`cho_duyet` / `da_duyet` / `da_sua` / `tu_choi`)
- nguoi_duyet, ngay_duyet, ghi_chu_duyet

### 7.4 Quan hệ văn bản

**quan_he_van_ban**
- id, van_ban_a_id, **loai_quan_he** (`sua_doi` / `bo_sung` / `thay_the` / `bai_bo` / `hoan_hieu_luc` / `huong_dan` / `dinh_chi`) **[SỬA — v1 chỉ có 4 loại, thiếu 3 loại quan trọng]**, van_ban_b_id, don_vi_bi_tac_dong_id (trỏ vào `don_vi_luat`, không chỉ ghi tên điều dạng text)

### 7.5 Log nạp dữ liệu (bảng mới, v1 nói tới nhưng không có bảng) **[SỬA]**

**log_nap**
- id, file_nguon, duong_dan_raw, ngay_nap, mo_hinh_su_dung, ket_qua (`thanh_cong` / `loi`), ghi_chu

### 7.6 Bảng chỉ mục
- `fts` (FTS5) trỏ vào `phien_ban_noi_dung.noi_dung` (kèm số hiệu đơn vị, tên văn bản để tra theo từ khóa)
- `vec` (sqlite-vec), `rowid = phien_ban_noi_dung.id`

### 7.7 Cấu trúc thư mục **[SỬA — đổi tên, thêm tests/requirements]**
```
Lexo/
  .env                 # API key — KHÔNG commit
  .gitignore           # .env, raw/, db/
  config.yaml          # tên mô hình, endpoint (không chứa key), đường dẫn
  requirements.txt      # khóa phiên bản thư viện
  README.md
  raw/                 # file gốc, không sửa
  inbox/               # file mới chờ nạp
  db/luat.sqlite
  src/
    ingest/            # crawler, upload, trích xuất text
    parse/             # regex parse cấu trúc văn bản gốc (code, không LLM)
    extract/           # gọi LLM cho văn bản sửa đổi, schema JSON, prompt
    validate/          # validator tự động trước duyệt
    review/            # giao diện duyệt (bản tối thiểu làm từ bước 1)
    apply/             # áp lệnh đã duyệt, dựng phiên bản
    index/             # embedding, FTS, vector
    query/             # tra chính xác, hybrid, theo ngày, diff
    agent/             # phân loại ý định, trích tham số (LLM local nhỏ)
  eval/                # bộ câu hỏi và script đánh giá
  tests/               # unit test cho parser, validator, apply
```

---

## 8. Truy vấn

- **Tra chính xác**: parse "Điều 173 BLHS 2015" → tra `ten_viet_tat` + `ky_hieu` trong `don_vi_luat`. Không cần mô hình.
- **Hybrid**: FTS5 (BM25) + vector song song, gộp bằng RRF. **Lọc theo ngày hiệu lực TRƯỚC khi tính khoảng cách vector**, không lọc sau kNN — lọc sau có thể loại mất kết quả đúng nằm ngoài top-k ban đầu. **[SỬA]**
- **Xem theo ngày**: `hieu_luc_tu <= X AND (hieu_luc_den IS NULL OR X < hieu_luc_den)`. **[SỬA]**
- **Diff**: tính lúc truy vấn, không lưu sẵn.
- Câu hỏi và tài liệu phải qua **cùng một mô hình embedding**.

---

## 9. Quy trình nạp văn bản mới

### Văn bản gốc (luật ban hành lần đầu)
1. Bỏ file vào `inbox/`, hoặc crawler tải về
2. Trích xuất text thuần, lưu file gốc vào `raw/`
3. **Code regex parse trực tiếp** cấu trúc Chương/Điều/Khoản/Điểm → ghi `don_vi_luat` + `phien_ban_noi_dung` (không qua LLM)
4. Validator tự động kiểm tra tính liên tục số điều/khoản
5. Người duyệt xác nhận nhanh (khối lượng thấp vì không phải sửa lỗi LLM)
6. Tính embedding, ghi vào kho

### Văn bản sửa đổi
1. Bỏ file vào `inbox/`, hoặc crawler tải về
2. Trích xuất text thuần
3. Gọi LLM (API), ép JSON theo schema lệnh sửa đổi (mục 5) — **không yêu cầu LLM trả lại nguyên văn cấu trúc luật**
4. **Validator tự động** chạy trước khi hiển thị: số điều/khoản hợp lệ, ngày hợp lệ, đơn vị đích tồn tại, đối chiếu nguyên văn — gắn cờ nếu sai
5. **Giao diện duyệt hai cột** (văn bản gốc | lệnh trích xuất + cờ validator): người duyệt sửa tay, duyệt hoặc từ chối từng lệnh, ghi vào `lenh_sua_doi`
6. Code áp lệnh đã duyệt lên `don_vi_luat`/`phien_ban_noi_dung`, đóng/mở khoảng hiệu lực
7. Tính embedding cho phiên bản mới, ghi vào kho
8. Ghi `log_nap`

**[SỬA]** Giao diện duyệt tối thiểu (bản hai cột đơn giản) đưa vào **ngay từ bước 1–2** của kế hoạch triển khai (mục 11), không đợi đến bước 5 như bản v1.

### Đối chiếu độc lập (mục A.5 review — quyết định: làm cho bộ luật thử nghiệm đầu tiên)
Với **BLHS 2015** (bộ luật ở bước 1), sau khi dựng xong toàn bộ phiên bản (gốc + các lần sửa đổi), **đối chiếu bản dựng lại với văn bản hợp nhất chính thức** do cơ quan có thẩm quyền công bố (nếu có, tra trên vbpl.vn). Ghi tỉ lệ khớp làm bằng chứng phương pháp đúng — dùng khi trình bày/bảo vệ để tránh lập luận vòng tròn ("nhãn tự sinh từ chính kho"). Không bắt buộc lặp lại việc này cho mọi bộ luật khác trong phạm vi luận văn; nêu rõ đây là giới hạn đã biết.

**Lộ trình nạp dữ liệu (theo tầng)**
- Tầng 1: BLHS 2015 và các văn bản sửa đổi của nó (bộ luật thử nghiệm, có đối chiếu độc lập)
- Tầng 2: các bộ luật lớn khác (BLDS 2015, BLTTHS, BLTTDS...) + nghị quyết hướng dẫn của TANDTC
- Tầng 3: mở rộng dần

Nguồn ưu tiên: **vbpl.vn**. Với nguồn thương mại (thuvienphapluat.vn), kiểm tra điều khoản sử dụng/bản quyền trước khi thu thập.

---

## 10. Mô hình hiệu lực — các ca cần phủ **[MỤC MỚI — v1 chưa xử lý]**

Hiệu lực không chỉ nằm ở cấp văn bản. Cần phủ được:

1. **Hoãn hiệu lực toàn văn bản**: một luật ban hành với ngày hiệu lực dự kiến, sau đó bị lùi bằng nghị quyết riêng trước khi luật kịp có hiệu lực. Xử lý bằng `quan_he_van_ban.loai_quan_he = hoan_hieu_luc`, cập nhật `van_ban.ngay_hieu_luc` và `trang_thai = chua_co_hieu_luc` cho đến mốc mới.
   - *Ví dụ cần tự kiểm chứng*: BLHS 2015 (bộ luật dùng ở bước 1) được cho là từng bị lùi hiệu lực bằng một nghị quyết riêng của Quốc hội trước khi luật kịp thi hành. **Ngày tháng và số hiệu nghị quyết chính xác cần tra lại trên vbpl.vn**, không dùng số liệu nhớ lại chưa kiểm chứng.
2. **Hiệu lực từng phần trong cùng một văn bản**: một số điều có hiệu lực sớm hơn/muộn hơn phần còn lại. Xử lý ở cấp `phien_ban_noi_dung.hieu_luc_tu` của từng đơn vị, không dùng chung một ngày hiệu lực cấp văn bản cho mọi điều.
3. **Hết hiệu lực một phần**: văn bản còn hiệu lực nhưng một số điều đã bị bãi bỏ. Phản ánh qua `trang_thai = het_hieu_luc_mot_phan` ở cấp văn bản, và từng đơn vị bị bãi bỏ có `hieu_luc_den` riêng.
4. **Đình chỉ hiệu lực tạm thời** (`dinh_chi`) và **văn bản hướng dẫn thi hành** (`huong_dan`, không làm đổi nội dung nhưng liên quan chặt) — lưu như quan hệ riêng, không lẫn với `sua_doi`.

---

## 11. Yêu cầu phần cứng

### 11.1 Cấu hình tối thiểu (dùng API cho đọc hiểu văn bản sửa đổi, local chỉ chạy embedding + agent nhỏ + SQLite)
| Thành phần | RAM ước lượng |
|---|---|
| bge-m3 (embedding) | ~1.2GB |
| bge-reranker-v2-m3 (nếu dùng) | ~1.2GB |
| Qwen3 nhỏ (1.7B–4B, cho agent bước 1/2/4) | ~2–3GB |
| SQLite + sqlite-vec | vài trăm MB |

Tổng phần AI local khoảng **4–6GB**. CPU đủ dùng, GPU không bắt buộc cho cấu hình này.

### 11.2 Nếu thử Qwen3-8B cho bước trích xuất (phương án thay thế API)
| Mô hình (Q4_K_M) | VRAM ước lượng |
|---|---|
| Qwen3-8B | ~5–7GB |

**[SỬA]** Với GPU **8GB VRAM**: Qwen3-8B là mức tối đa chạy gọn hoàn toàn trên GPU này. **Qwen3-14B (~9GB) và 32B (~20GB) không vừa VRAM**, chỉ chạy được bằng cách offload một phần lên CPU (chậm hơn đáng kể) — ghi rõ giới hạn này trong luận văn thay vì giả định nâng cấp tự do theo lộ trình 8B→14B→32B.

### 11.3 Dung lượng ổ đĩa (ước lượng, không đổi nhiều so với v1)
| Thành phần | Dung lượng |
|---|---|
| File Word gốc (bộ luật cốt lõi + sửa đổi + hướng dẫn) | ~25–90MB |
| File SQLite (~20.000 đơn vị lá, gồm text + FTS5 + vector) | ~150–250MB |
| Mở rộng lớn hơn | ~500MB–1GB |
| Trọng số Qwen3-8B lượng tử hóa | ~5GB |

### 11.4 Mạng
- Cần mạng cho: gọi API đọc hiểu văn bản sửa đổi, crawler, tải mô hình lần đầu
- **Không cần mạng** cho: mọi truy vấn của người dùng cuối (kể cả agent bước 1/2/4, vì dùng LLM local nhỏ)

---

## 12. Cách đánh giá

| Tác vụ | Chỉ số |
|---|---|
| Tra cứu điều luật từ câu hỏi bằng lời | Recall@k (k=1,5,10), MRR, nDCG@k; so FTS riêng / vector riêng / hybrid, và giữa các mô hình embedding |
| Hiệu lực theo thời gian | Accuracy so khớp chính xác; báo cáo riêng các ca sát mốc chuyển giao và ca hoãn hiệu lực (mục 10) |
| Trích xuất lệnh sửa đổi | Precision/Recall/F1 theo từng lệnh (dùng trực tiếp bảng `lenh_sua_doi` làm nhãn, không cần sinh nhãn riêng); độ chính xác từng trường; **tỉ lệ khớp nguyên văn tự động** (`khop_nguyen_van`); tỉ lệ không cần sửa tay |
| Quan hệ văn bản | Accuracy, Macro-F1, confusion matrix (7 loại quan hệ theo mục 7.4) |
| Độ tin cậy của bản dựng lại | Tỉ lệ khớp với văn bản hợp nhất chính thức, đo trên BLHS 2015 (mục 9) |

- Bộ câu hỏi tra cứu: 50–100 câu tự đặt kèm đáp án đúng, nhờ một người kiểm chéo một phần
- Tách tập dev/test; có baseline (BM25 thuần; trích xuất bằng regex/luật đơn giản)
- Thực nghiệm đáng làm: so sánh mức lượng tử hóa (Q4/Q5/Q6/Q8) của Qwen3-8B (cỡ duy nhất vừa VRAM 8GB) trên tác vụ trích xuất, đo RAM + độ trễ thực tế; so mô hình local với API "giáo viên"

### Người duyệt **[MỤC MỚI — theo review]**
Ghi rõ trong luận văn: ai là người thực hiện bước duyệt (chính bạn hay có sự tham gia của người có nền tảng pháp lý), vì đây là biện pháp kiểm soát chất lượng chính của toàn hệ thống. Nếu người duyệt không có nền tảng pháp lý chuyên sâu, cần nêu rõ đây là giới hạn của luận văn, không che giấu.

---

## 13. Kế hoạch làm theo thứ tự **[SỬA — đưa giao diện duyệt lên sớm]**

| Bước | Việc | Kết quả kiểm tra được |
|---|---|---|
| 1 | Dựng schema SQLite (mục 7); viết parser regex cho văn bản gốc; nạp BLHS 2015 (văn bản gốc); **giao diện duyệt tối thiểu (2 cột)** | Tra chính xác "Điều X" chạy được |
| 2 | Nạp văn bản sửa đổi của BLHS 2015: LLM trích lệnh → validator → duyệt → áp lệnh | Dòng thời gian, xem theo ngày, diff chạy được |
| 3 | Đối chiếu bản dựng lại với văn bản hợp nhất chính thức của BLHS 2015 | Số liệu tỉ lệ khớp |
| 4 | Thêm FTS5, embedding, sqlite-vec (hoặc numpy brute-force dự phòng); hybrid search | Tìm theo mô tả bằng lời chạy được |
| 5 | Xây bộ câu hỏi đánh giá; đo Recall@k, MRR; so sánh mô hình embedding | Bảng kết quả thực nghiệm |
| 6 | Agent: LLM local nhỏ cho phân loại ý định/trích tham số; bước 4 trả nguyên văn (tra chính xác) hoặc diễn giải local (mô tả tự do) | Bản demo end-to-end, không cần mạng lúc dùng |
| 7 | Mở rộng sang các bộ luật khác, nghị quyết hướng dẫn | Kho lớn dần |
| 8 | (Tùy chọn) so sánh mức lượng tử hóa, distillation, công bố dataset | Đóng góp mở rộng |

Mỗi bước cho ra một bản chạy được để trình thầy. Cần bổ sung mốc thời gian cụ thể (ngày trình thầy cho từng bước) khi có lịch học kỳ.

---

## 14. Agent chat (giao diện) **[SỬA — tách rõ có/không dùng LLM theo loại câu hỏi]**

```
Câu người dùng
  → (1) Phân loại ý định [LLM local nhỏ]: tra chính xác / tìm theo mô tả /
        xem theo ngày / so sánh / ngoài phạm vi
  → (2) Trích tham số [LLM local nhỏ, ép JSON]: tên luật, số điều, ngày, mô tả
  → (3) Gọi công cụ truy vấn kho (code, không LLM)
  → (4a) Nếu là tra chính xác: trả nguyên văn từ kho + trích dẫn, KHÔNG dùng LLM
  → (4b) Nếu là câu hỏi mô tả cần diễn giải: LLM local nhỏ diễn giải,
         RÀNG BUỘC chỉ dùng nội dung đã truy xuất, không tự thêm
```

- Không có bước nào trong agent gọi API — toàn bộ chạy local, giữ đúng cam kết "truy vấn người dùng không cần mạng"
- Từ chối lịch sự câu hỏi ngoài phạm vi
- Luôn kèm cảnh báo: thông tin tham khảo, không phải tư vấn pháp lý
- Hiển thị ngày cập nhật kho lần cuối trên giao diện

---

## 15. Rủi ro và giới hạn cần ghi rõ

- Kho chỉ đầy đủ đến mức đã nạp
- Phiên bản cũ là **bản dựng lại** từ lệnh sửa đổi, đã đối chiếu độc lập cho BLHS 2015 nhưng **chưa đối chiếu cho các bộ luật khác** — nêu rõ đây là giới hạn phạm vi
- LLM có thể đọc sai đơn vị/ngày; validator + người duyệt là biện pháp chính, không được bỏ qua
- Người duyệt không nhất thiết có nền tảng pháp lý chuyên sâu — nêu rõ nếu đúng vậy
- GPU 8GB giới hạn LLM local ở mức 8B; so sánh với mô hình lớn hơn cần qua API
- sqlite-vec là thư viện còn non (0.x); có phương án dự phòng numpy brute-force
- Bản quyền và điều khoản sử dụng nguồn dữ liệu: ưu tiên nguồn chính thống
- Môi trường Python khóa phiên bản trong `requirements.txt`

---

## 16. Các điểm còn để mở (chốt khi bắt đầu code)

1. Chọn API cụ thể cho bước đọc hiểu văn bản sửa đổi, xác nhận điều khoản dữ liệu
2. JSON schema chính xác cho đầu ra trích xuất (đơn vị đích, loại thao tác, các trường theo mục 5) — cần viết thành đặc tả riêng cho phần code
3. Tiêu chí nghiệm thu cụ thể cho từng bước ở mục 13 (ví dụ: bước 1 coi là xong khi tra được bao nhiêu % điều đúng)
4. Mốc thời gian trình thầy cho từng bước
5. Mô hình embedding chọn sau thực nghiệm
6. Xác nhận số hiệu và ngày tháng chính xác của nghị quyết hoãn hiệu lực BLHS 2015 (mục 10) trên vbpl.vn trước khi đưa vào báo cáo
7. Nhắm mục tiêu công bố (luận văn / hội nghị / tạp chí) để quyết định mức đầu tư cho dataset và đánh giá

---

## Phụ lục: Đối chiếu với review — mục nào đã xử lý

| # dòng trong review | Xử lý ở đâu trong v2 |
|---|---|
| 2–11 (đơn vị lưu trữ, thao tác sửa đổi, LLM không chép nguyên văn) | Mục 5, 7.2, 7.3, nguyên tắc thiết kế #1 |
| 12–17 (agent vỡ cam kết offline) | Mục 4, 14 |
| 18–24 (mô hình hiệu lực chưa phủ ca thật) | Mục 10 |
| 25–30 (schema thiếu bảng) | Mục 7.3, 7.4, 7.5, 7.2 (bỏ cột embedding trùng) |
| 31–33 (thiếu validator, đối chiếu độc lập) | Mục 3 (validator), mục 9 (đối chiếu độc lập), mục 0 (quyết định phạm vi) |
| 35 (giao diện duyệt cần sớm) | Mục 9, mục 13 bước 1 |
| 36 (phạm vi underthesea/chức năng 2) | Loại khỏi tài liệu này — thuộc chức năng 2 |
| 37–39 (môi trường, sqlite-vec) | Mục 6 |
| 40 (lọc ngày trước kNN) | Mục 8 |
| 41–44 (repo, .env, cấu trúc thư mục) | Mục 7.7, nguyên tắc #5 |
| 45 (đặc tả code, tiêu chí nghiệm thu, mốc thời gian) | Mục 16, còn để mở — cần làm riêng |
| 46 (GPU 8GB) | Mục 6, 11.2 |
| 47 (người duyệt là ai) | Mục 12 |
