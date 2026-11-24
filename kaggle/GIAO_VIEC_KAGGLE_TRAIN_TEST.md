# Lexo — Giao việc cho chat Kaggle: học (train) và đo (test) V3

Dán file này vào một chat MỚI, cùng `KE_HOACH_KAGGLE_V3.md` và ba notebook (`lexo_hoc_cbba.ipynb`, `lexo_gop_gguf_cbba.ipynb`, `lexo_do_ban_an_cbba.ipynb`).
Kế hoạch V3 là **bản gốc về tham số và quy tắc**; file này chỉ nói **chat này làm gì, theo chặng nào, dừng khi nào, báo gì về**. Nếu hai file mâu thuẫn, theo kế hoạch V3 và hỏi lại.
Soạn ngày 2026-11-01. Học và test **chưa chạy lần nào**; mọi con số giờ dưới đây là ước lượng.

## 0. Vai trò

| Ai | Làm gì |
|---|---|
| **Chat Kaggle (chat này)** | Hướng dẫn từng bước, đọc lỗi, đề xuất sửa tối thiểu, tính R2, soạn báo cáo từng chặng. Không tự đổi tham số đã khóa. |
| **Người phụ trách (Kintakashi)** | Bấm chạy trên Kaggle, dán kết quả vào chat, **duyệt** các điểm dừng ghi «CẦN DUYỆT». |
| **Chat gốc (dự án Lexo)** | Giữ mã nguồn, đóng gói lại khi cần (R1/R2), chạy `phan_tich_cbba.py` trên laptop. Quay về đó khi gặp điểm «VỀ CHAT GỐC». |

Mỗi chặng kết thúc bằng một **báo cáo** theo mẫu mục 6. Chưa có báo cáo và chưa được duyệt thì chưa sang chặng sau.

## 1. Bối cảnh ngắn

Lexo tra cứu Bộ luật Hình sự cục bộ. Mô hình cần học: **Qwen3-8B QLoRA, đọc sự việc một bản án + danh sách Điều ứng viên (từ truy hồi bge-m3 + FTS5), trả `{"dieu": [...]}`**.
Mục tiêu khoa học: so **L** (LoRA) với **C0** (Qwen3-8B gốc, cùng ứng viên) trên «tìm đủ» (mọi Điều đáp án đều được chọn), trên 3.000 vụ test. Kết quả xấu cũng được báo cáo.

Dữ liệu (đã đóng gói trên laptop, hai zip):
- `lexo_hoc_chon_dieu_cbba.zip` → Dataset private `lexo-hoc-cbba`: 3.526 bản án học + 300 dev (val).
- `lexo_do_ban_an_cbba.zip` → Dataset private `lexo-do-cbba`: 3.000 vụ test + 100 vụ dev để đo, kèm mã nguồn và chỉ mục.
(Tên file gói là `..._do_ban_an_cbba`, không phải `..._do_chon_dieu_cbba`; notebook tìm gói theo file đánh dấu bên trong.)

## 2. Điều kiện bắt đầu (người phụ trách xác nhận, chat này chỉ kiểm)

| # | Kiểm | Đạt khi |
|---|---|---|
| a | Chạy trên laptop: `python scripts\xem_recall_zip.py lexo_do_ban_an_cbba.zip`, dán kết quả vào chat | Không có cảnh báo `--gia`; thoát mã 0 (đủ đáp án trong top 30 ≥ 80%); ghi lại K và chế độ ứng viên đã chọn |
| b | Hai Dataset trên Kaggle ở chế độ **private** | Đúng tên, đúng zip, mỗi cái chứa file đánh dấu (`LEXO_HOC_CHON_DIEU.md`, `LEXO_DO_BAN_AN.md`) |
| c | Tài khoản Kaggle có GPU T4 và còn hạn mức | Xem trang tài khoản; kế hoạch giả định ~12 giờ/phiên, ~30 giờ/tuần (**phải tự kiểm lại**) |

Nếu (a) thoát mã 2 (dưới sàn) hoặc có cảnh báo `--gia`: **VỀ CHAT GỐC**, không học. Nếu thiếu bảng Recall@K: dừng, đừng đoán.

## 3. Các chặng

### Chặng 1 — Học thử (`lexo_hoc_cbba`, `CHE_DO = "thu"`)
- Kaggle: GPU T4, Internet bật; chỉ gắn Dataset `lexo-hoc-cbba` (không gắn `lexo-do-cbba`, không gắn hai gói học).
- Ô cấu hình: giữ `CHE_DO = "thu"`; **không** sửa `EPOCH`, `LR`, `LORA_R`, `MAX_LEN`, `MICRO_BS`, `GRAD_ACC`, `SEED`. Chạy tương tác (Run All).
- Chạy: G0 (SHA256, không trùng test, lời nhắc khớp) + học 2 bước trên 16 mẫu dài nhất.
- Đạt khi: G0 sạch; không OOM; ghi lại **giây/bước và VRAM đỉnh** (lưu ý: 16 mẫu dài nhất là cận trên, không phải trung bình).
- Dừng khi: G0 báo rò rỉ hoặc SHA lệch → **VỀ CHAT GỐC**. OOM → mục 4 hàng «OOM».
- **CẦN DUYỆT** trước chặng 2.

### Chặng 2 — Học thật (`CHE_DO = "that"`, Save Version → Save & Run All)
- Ô cấu hình: chỉ đổi `CHE_DO = "that"`. EPOCH 1 (~441 bước cập nhật), `GIO_TOI_DA = 9.0`.
- Sau 10 bước notebook tự in «dự kiến … giờ». Nếu quá 9 giờ nó dừng và ghi `<TEN>_DUNG.json`: áp **R1** (kế hoạch V3, mục 4): (a) `MAX_LEN = 3072`; (b) nếu vẫn quá thì đóng gói lại với `--tran 30` (**VỀ CHAT GỐC**, laptop) rồi học lại từ đầu. Chỉ vì thời gian/VRAM, chỉ **trước** khi có bất kỳ kết quả dev/test nào.
- Đạt khi (G1): val loss cuối < bước 0, không NaN; 20 mẫu val: JSON hợp lệ 20/20, mọi Điều nằm trong ứng viên, 0 khối think.
- Mang về: `lexo-qwen3-8b-chon-dieu-cbba-v1.zip` (adapter + `thong_tin.json`). Không có checkpoint nào khác để chọn.
- Chưa đạt G1 → **không** chạy lại để «cải thiện»; báo cáo nguyên trạng và hỏi (**VỀ CHAT GỐC**).
- **CẦN DUYỆT** trước chặng 3.

### Chặng 3 — Gộp GGUF (`lexo_gop_gguf_cbba`)
- Kaggle: CPU, Internet bật; input = Output của chặng 2. Chạy tất cả.
- Đạt khi (G2): kiến trúc `qwen3`, 399 tensor, có chat template; `merge_info.json` ghi kích thước, SHA256, commit llama.cpp. Tên Ollama sẽ là `qwen3-8b-lexo-chon-dieu-cbba-v1`.
- Mang về: `merge_info.json` và file GGUF Q4_K_M (đưa về laptop; dùng cho Chức năng 2 sau này).

### Chặng 4 — Đo dev (`lexo_do_ban_an_cbba`, G3/G4)
- Kaggle: GPU T4, Internet bật; input = Dataset `lexo-do-cbba` + Output của chặng 3. Chỉ bật `CHAY_LORA_DEV = True`; `CHAY_VONG_1 = False` (V3 không có Vòng 1), `CHAY_DOI_K = False`, `CHAY_TEST = False`, `DA_CHOT = False`.
- Chạy A, C0, L trên 100 vụ dev.
- Đạt khi: G3 (3 vụ: `ollama ps` 100% GPU, `num_ctx` 8192, 0 lỗi, 0 think, 0 «có thể bị cắt») và G4 (100 vụ: 0 lỗi, 0 think, 0 bị cắt). Điểm dev **chỉ để xem, không dùng để quyết định gì**.
- Ghi lại bảng tổng: `giây/vụ` trung bình của C0 (`g_C0`) và L (`g_L`).
- Mang về: `ket_qua_dev_qwen3-8b-lexo-chon-dieu-cbba-v1.zip`.

### Chặng 5 — Tính R2 và chốt cỡ test (chat này tính, người phụ trách duyệt)
`N_max = 100 × ⌊32.400 / (g_C0 + g_L) / 100⌋`; `N_test = min(3.000, N_max)`. Không dùng điểm dev.

| `N_test` | Làm |
|---|---|
| 3.000 | dùng gói đo hiện có |
| 1.000 ≤ N < 3.000 | **VỀ CHAT GỐC (laptop):** `python scripts\dong_goi_cbba_kaggle.py --so-test N_test` rồi tải lên làm phiên bản mới của `lexo-do-cbba`; gói học không đổi |
| < 1.000 | dừng, hỏi; không chạy một phần, không tự chọn cỡ nhỏ hơn |

Chat này chỉ được sang chặng 6 khi người phụ trách gõ đúng một câu: **«Chốt test N_test = <số>, cấu hình A, C0, L»**.

### Chặng 6 — Test, chạy MỘT lần duy nhất
- Kaggle: như chặng 4 (đã cập nhật phiên bản Dataset nếu có R2). Đặt `CHAY_TEST = True`, `DA_CHOT = True`; các cờ khác `False`. Save Version → Save & Run All.
- Notebook ghi `cau_hinh_chot.json` một lần; nếu file đã có và khác thì từ chối chạy. **Không** xóa file đó để chạy lại.
- Đạt khi: 0 lỗi kỹ thuật, 0 think, 0 bị cắt, log sạch. Vụ nào lỗi tính là «không tìm đủ», không chạy bù.
- Mang về: `ket_qua_test.zip` (có `cau_hinh_chot.json`). Chép **bảng tổng** vào báo cáo **trước**, rồi mới xem từng vụ sai.
- Nếu phiên chết giữa chừng: báo nguyên văn, **VỀ CHAT GỐC** để quyết định (không tự chạy lại).

### Chặng 7 — Phân tích (laptop, chat gốc)
`python scripts\phan_tich_cbba.py --goi inbox\kaggle_cbba\lexo_do_ban_an_cbba --ket-qua <thư mục chứa C0.jsonl, L.jsonl> --chot <cau_hinh_chot.json>` → `phan_tich.md`.
So sánh chính duy nhất có kiểm định: **L so với C0 trên «tìm đủ»**, McNemar chính xác hai phía α = 0,05 + bootstrap cặp (seed 2026, 2.000 lần). Còn lại chỉ mô tả.

## 4. Gặp sự cố thì làm gì

| Tình huống | Làm | Không làm |
|---|---|---|
| Lỗi cài thư viện / không có mạng | Kiểm Internet đã bật; giữ đúng phiên bản trong `PHIEN_BAN`; báo nguyên văn lỗi | Nâng phiên bản bừa |
| OOM khi học | Chỉ R1(a) `MAX_LEN = 3072`, báo số mẫu bị cắt (ghi trong `thong_tin.json`) | Đổi `r`, `LR`, batch, EPOCH |
| Dự kiến > 9 giờ | R1 như chặng 2 | Giảm EPOCH, bỏ mẫu bằng tay |
| Phiên 12 giờ sắp hết | Để notebook tự dừng và lưu (`<TEN>_DUNG.json`); báo cáo | Chạy tiếp bằng cách bỏ cổng |
| `ollama ps` không 100% GPU (G3) | Báo nguyên văn `ollama ps`, kiểm `num_ctx`, kiểm GPU đã bật | Chạy test khi G3 chưa đạt |
| Hết hạn mức GPU tuần | Dừng, ghi mốc đã xong, hẹn tuần sau | Dồn bằng cách đổi tham số |
| Lỗi chưa gặp | Nguyên văn lỗi, nguyên nhân gốc, sửa **tối thiểu** (không đổi hành vi tính điểm) | Sửa mã đo để «cho qua» |

## 5. Cấm (rút từ kế hoạch V3 mục 7)

- Không gắn gói đo vào notebook học; không gắn hai gói học cùng lúc.
- Không chạy test trước khi có câu chốt ở chặng 5; không chạy lại test.
- Không chọn checkpoint, K, chế độ ứng viên, lời nhắc, EPOCH theo điểm dev hay test.
- Không dùng 99 vụ test án lệ (giữ làm test độc lập thứ hai, cần quyết định riêng).
- Không công khai Dataset, adapter, GGUF (bản án đã che nhưng chưa quét hết thông tin cá nhân còn sót).
- Ghi lại mọi lần chạy, kể cả lần xấu. Không xóa kết quả xấu.

## 6. Mẫu báo cáo sau mỗi chặng (chat này soạn, người phụ trách dán về chat gốc)

```
CHẶNG <số>: <tên>    ngày giờ (Asia/Saigon): ...    phiên bản notebook / Dataset: ...
Cài đặt Kaggle: GPU ..., Internet ..., input: ...
Ô đã chỉnh so với bản gốc: <liệt kê, hoặc «không»>
Kết quả cổng: G? đạt / không đạt  (số liệu: ...)
Số đo: giây/bước ..., VRAM đỉnh ..., giờ thực ..., val loss bước 0 → cuối ..., g_C0 ..., g_L ...
Tệp mang về: <tên, kích thước, sha256 nếu có>
Lỗi gặp: <nguyên văn> | nguyên nhân | cách sửa tối thiểu | có đổi tham số không: không
Đề xuất bước tiếp: ...   CẦN DUYỆT / VỀ CHAT GỐC / tiếp tục
```
Nhật ký chạy (mỗi phiên một dòng, thêm cả lần hỏng): `ngày | notebook | cờ đã bật | thời gian | kết quả | ghi chú`.

## 7. Tin nhắn đầu tiên cho chat Kaggle

> Đồ án Lexo (tra cứu Bộ luật Hình sự). Đính kèm: `GIAO_VIEC_KAGGLE_TRAIN_TEST.md`, `KE_HOACH_KAGGLE_V3.md`, ba notebook V3. Hai Dataset private `lexo-hoc-cbba` và `lexo-do-cbba` đã lên Kaggle.
> Bảng Recall@K của gói đo: <dán kết quả của `xem_recall_zip.py`>.
> Hãy dẫn mình làm **Chặng 1** (học thử). Mình chỉ có laptop, GPU là Kaggle T4. Làm theo file giao việc: không đổi tham số đã khóa, khi gặp lỗi đưa nguyên văn lỗi + nguyên nhân gốc + cách sửa tối thiểu,
> sau mỗi chặng soạn báo cáo theo mẫu mục 6 và chờ mình duyệt; không chạy test cho tới khi mình gõ đúng câu chốt ở chặng 5.

## 8. Sau khi xong (chat gốc)

- Báo cáo bằng số, kể cả xấu; ghi hạn chế đã biết (kế hoạch V3 mục 9).
- `ollama create qwen3-8b-lexo-chon-dieu-cbba-v1` từ GGUF; Chức năng 2 (`chay_phan_tich_vu_an.bat`) tự dùng mô hình này ở bước chọn Điều (khóa `vu_an.chon_model` trong `config.yaml`).
- Việc còn mở không thuộc chat Kaggle: rà nhãn bởi sinh viên luật, hỏi thầy về thông tin cá nhân còn sót, quyết định dùng 99 vụ test án lệ.
