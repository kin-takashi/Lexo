# Lexo — Kế hoạch Kaggle v2: chọn Điều từ ứng viên, đo trên bản án

Dán file này vào chat Kaggle. Lý do, ngưỡng đọc kết quả và ba so sánh đăng ký trước nằm trong tài liệu
«Lexo — Quy trình train trên Kaggle»: https://claude.ai/artifact/Vzyz88TCa718vsTpHooMtn. File này chỉ nói **chạy cái gì, theo thứ tự nào,
kiểm gì, mang gì về**.

---

## 0. Trên laptop (một lần)

1. Mở Ollama, đã `ollama pull bge-m3`.
2. `python scripts\dong_goi_kaggle.py` → `inbox\kaggle\`: `lexo_do_ban_an.zip`, `lexo_hoc_chon_dieu.zip`, ba notebook, file này.
   Script in bảng Recall@K trên 90 vụ train (không in gì về test) và chọn chế độ ứng viên + K.
   - Thoát **0**: có đủ hai gói.
   - Thoát **2**: ứng viên dưới sàn (đủ đáp án trong top 30 < 80%). Gói đo vẫn được ghi, gói học thì không. Theo kế hoạch:
     vẫn chạy Vòng 1 để có số, nhưng sửa truy hồi trước khi sang Vòng 2.
   - Thoát **1**: G0 phát hiện rò rỉ test hoặc dữ liệu lỗi. Dừng, báo về chat gốc.
3. Chia thật: 69 vụ học / 21 vụ dev (cả nhóm vụ đi cùng nhau nên không đúng 70/20).

## 1. Tạo Dataset private trên Kaggle

| Dataset (gợi ý tên) | Tải lên | Gắn vào |
|---|---|---|
| `lexo-do-ban-an` | `lexo_do_ban_an.zip` | notebook đo |
| `lexo-hoc-chon-dieu` | `lexo_hoc_chon_dieu.zip` | notebook học (**chỉ** notebook học) |
| GGUF n368 (đã có từ lần trước) | `…n368…q4_k_m.gguf` | notebook đo, cho B1 |

Kaggle tự giải nén zip; notebook tìm gói theo file đánh dấu (`LEXO_DO_BAN_AN.md`, `LEXO_HOC_CHON_DIEU.md`) và chạy
`sha256sum -c SHA256SUMS` trước mọi việc, nên đường dẫn `/kaggle/input/...` không quan trọng. Import notebook: File → Import Notebook.

## 2. Thứ tự chạy

| # | Notebook | Cài đặt | Bật | Cổng | Mang về |
|---|---|---|---|---|---|
| 1 | `lexo_do_ban_an` | GPU T4, Internet | `CHAY_VONG_1 = True` | chạy thử 3 vụ sạch về kỹ thuật | `ket_qua_train90.zip` |
| 2 | — (chat gốc) | | | đọc Vòng 1 theo bảng trong tài liệu | quyết định sang Vòng 2 |
| 3 | `lexo_hoc_chon_dieu` | GPU T4, Internet | `CHE_DO = "thu"` (tương tác) rồi `"that"` (Save & Run All) | G0, G1 | `lexo-qwen3-8b-chon-dieu-v1.zip` |
| 4 | `lexo_gop_gguf` | CPU, Internet; input = Output của #3 | | G2 | `merge_info.json` |
| 5 | `lexo_do_ban_an` | thêm input = Output của #4 | `CHAY_LORA_DEV = True`, tắt Vòng 1 | G3, G4 | `ket_qua_dev_qwen3-8b-lexo-chon-dieu-v1.zip` |
| 6 | (tùy chọn) Vòng 3 | | C1 → C3 (`CHAY_DOI_K`) → C2 | như #3–#5 | như trên |
| 7 | `lexo_do_ban_an` | đủ GGUF | `CHAY_TEST = True`, `DA_CHOT = True` (sau khi chốt ở chat gốc) | — | `ket_qua_test.zip` |

Lượt dài (Vòng 1 ước 2–3 giờ, học đủ ước 2–4 giờ, lượt test) chạy bằng **Save Version → Save & Run All**: chạy nền, đóng trình duyệt
vẫn chạy, Output được giữ. Các con số giờ là ước lượng, chưa đo.

Vòng 3: C1 đổi trong notebook học `DU_LIEU = "train_tong_hop"`, `TEN = "lexo-qwen3-8b-chon-dieu-c1"`; C2 đổi `SEED = 43` (44),
`TEN = "lexo-qwen3-8b-chon-dieu-v1-s43"`. Notebook gộp và notebook đo đổi `TEN` / `MO_HINH_LORA` / `MAU_GGUF_LORA` cho khớp.
Mọi lần của Vòng 3 phải xong trước lượt test.

## 3. Cổng (chỉ xét kỹ thuật, không xét điểm dev)

| Cổng | Ở đâu | Đạt khi |
|---|---|---|
| G0 | lúc đóng gói + ô 1, 3 notebook học | SHA256SUMS OK; 0 dòng trùng mã / băm / 5-gram với test; train ∩ val = ∅; lời nhắc khớp từng ký tự; đếm token thật, **0 câu trả lời bị cắt** (mẫu quá `MAX_LEN` chỉ bị cắt bớt sự việc, có ghi số) |
| G1 | ô 7 notebook học | val loss giảm so với bước 0, không NaN; sinh 20 mẫu val: JSON hợp lệ 20/20, mọi Điều trong ứng viên, 0 khối think |
| G2 | notebook gộp | kiến trúc `qwen3`, 399 tensor, có chat template; kích thước, SHA256, commit llama.cpp trong `merge_info.json` |
| G3 | notebook đo, 3 vụ dev | `ollama ps` báo 100% GPU, `num_ctx` 8192, 0 lỗi, 0 think, 0 «có thể bị cắt», nhật ký Ollama không có «truncating», `prompt_eval_count` khớp số token tự đếm (lệch ≤ 8) |
| G4 | notebook đo, cả dev | 0 lỗi, 0 think, 0 bị cắt. Tìm đủ / khớp đúng trên dev **chỉ để xem**, không dùng để chọn mô hình |

Chọn checkpoint: val loss thấp nhất trong các điểm cuối epoch; chênh dưới 0,01 thì lấy điểm sớm hơn.

## 4. Notebook đã lo sẵn / lỗi hay gặp

- **2×T4**: notebook học đặt `CUDA_VISIBLE_DEVICES=0` (tránh DataParallel với mô hình 4-bit).
- **Bộ nhớ**: logits chỉ tính ở phần trả lời và `lm_head` (đóng băng) giữ fp16; cả hai không đổi phép tính so với n368.
  Chế độ `thu` học 2 bước trên 16 mẫu dài nhất và in VRAM đỉnh. Nếu vẫn hết VRAM: `MAX_LEN = 3072` (sự việc tự cắt thêm ở chỗ nối,
  số mẫu bị cắt ghi vào `thong_tin.json`), **không đổi gì khác**.
- **Thời gian**: sau 10 bước notebook học ước tổng giờ; quá 9 giờ thì dừng, ghi `<TEN>_DUNG.json`. Báo về chat gốc, không tự đổi siêu tham số.
- **Ollama cắt ngầm** khi ngữ cảnh nhỏ: notebook đo đặt `num_ctx` 8192, `OLLAMA_NUM_PARALLEL=1`, đánh dấu vụ có `prompt_eval_count` sát
  `num_ctx` và lọc nhật ký tìm «truncating» (`ollama_canh_bao.txt`).
- **Quá giờ một vụ** (900 giây): vụ đó ghi lỗi «quá …s», lượt chạy đi tiếp. Lỗi hoặc quá giờ ở hơn 5% số vụ của B1 là một kết quả cần ghi vào bài.
- **Chạy tiếp**: kết quả ghi `.jsonl` sau từng vụ; chạy lại ô trong cùng phiên chỉ làm các vụ còn thiếu.
- **Output Kaggle có giới hạn dung lượng** (khoảng 20 GB): mô hình gốc, checkpoint, mô hình Ollama nằm ở thư mục tạm; Output chỉ có adapter,
  GGUF Q4_K_M (~5 GB), kết quả.
- Ollama ghim `0.40.4` như các lần đo dev 34 câu. Nếu bản đó không cài được: `OLLAMA_VERSION = ""` và ghi lại phiên bản thật
  (đã có trong `moi_truong.json`). Tên mô hình trong Ollama phải chứa `qwen3`.
- Thư viện học ghim đúng bản n368: transformers 5.20.1, peft 0.21.2, bitsandbytes 0.50.2, accelerate 1.15.0.

## 5. Cấm

- Không gắn gói đo (`lexo-do-ban-an`) vào notebook học. Notebook học dừng nếu thấy nó.
- Không chạy tập test trước khi chốt, không chạy lại test. `cau_hinh_chot.json` được ghi một lần; script đo từ chối chạy test với file chốt khác.
- Không chọn checkpoint, K, lời nhắc theo điểm dev hay test. Không đổi siêu tham số ngoài `MAX_LEN` dự phòng ở mục 4.
- Ghi lại mọi lần chạy, kể cả lần xấu.

## 6. Mang về laptop (`inbox/kaggle_ket_qua/`)

- Vòng 1: `ket_qua_train90.zip` (gồm `A`… `C0.jsonl`, `bao_cao.md`, `tom_tat.json`, `moi_truong.json`, `ollama_canh_bao.txt`).
- Vòng 2: `lexo-qwen3-8b-chon-dieu-v1.zip` (adapter đã chọn + `thong_tin.json`: val loss theo bước, số bước, số giây, commit mô hình gốc,
  số mẫu bị cắt, phiên bản thư viện, K, số lần chèn đáp án, hash file ứng viên), `merge_info.json`,
  `ket_qua_dev_qwen3-8b-lexo-chon-dieu-v1.zip`. Nếu dừng sớm: `<TEN>_DUNG.json`.
- Test: `ket_qua_test.zip` (có `cau_hinh_chot.json`). Chép bảng tổng vào tài liệu trước, rồi mới xem từng vụ sai.
- Ghi chú mọi lỗi gặp: nguyên văn lỗi, nguyên nhân, cách sửa tối thiểu. Chưa xóa GGUF cũ trước khi bản mới qua G3.

## 7. Tin nhắn đầu tiên gợi ý cho chat Kaggle

> Mình làm đồ án Lexo (tra cứu Bộ luật Hình sự, chạy local). Đính kèm `KE_HOACH_KAGGLE_V2.md` và ba notebook
> (`lexo_do_ban_an.ipynb`, `lexo_hoc_chon_dieu.ipynb`, `lexo_gop_gguf.ipynb`); hai gói dữ liệu đã lên Kaggle thành Dataset private.
> Việc lần này: bước #1 (Vòng 1 trên 90 vụ train). Mình chỉ có laptop, GPU là Kaggle T4. Khi gặp lỗi, đưa nguyên văn lỗi, nguyên nhân gốc
> và cách sửa tối thiểu; không đổi siêu tham số ngoài kế hoạch; không gắn gói đo vào notebook học; không chạy tập test.
