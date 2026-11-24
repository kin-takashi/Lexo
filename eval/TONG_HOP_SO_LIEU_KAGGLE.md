# Lexo — Tổng hợp số liệu đo (Kaggle/Colab) dùng cho bài báo

Tạo ngày 2026-10-24 bằng script, đọc thẳng từ các file kết quả gốc (cột «Nguồn» ghi file). Không nhập tay số nào từ trí nhớ. File đi kèm `TONG_HOP_SO_LIEU_KAGGLE.csv` có cùng số liệu ở dạng dòng-dài (bảng, mô hình, tập, chỉ số, giá trị, nguồn) để vẽ biểu đồ.

## 0. Số liệu gốc nằm ở đâu, dạng gì

| Loại | Vị trí (trong `E:\Lexo`) | Dạng | Ghi chú |
|---|---|---|---|
| Đợt 1: đo 14 câu (qwen3:4b, qwen3:8b, LoRA cũ, tách lý tưởng) | `inbox/ket_qua/` và `inbox/ket_qua.zip` | `kq_nhieu_dev_*.md` (bảng), `tach_dev_*.json` (kết quả tách), `tach_dev_*.log.jsonl` (mỗi dòng một câu: số hành vi, số Điều đáp án, giây, lỗi, văn bản thô) | zip và thư mục giống nhau |
| Đợt 2: đo 34 câu (qwen3:8b, LoRA cũ, n50, n368, mốc trần) | `inbox/ket_qua_1/` và `inbox/ket_qua_1.zip` | như trên, thêm hậu tố `_tat_ca`, `_dn01-14`, `_dn15-34`; `Modelfile_*`; `thong_tin_n368.json` | `_14cau/` giữ mốc trần 14 câu cũ |
| Thông tin từng lần học LoRA | `inbox/lexo-qwen3-8b-1/thong_tin.json` (LoRA cũ), `inbox/lexo-qwen3-8b-sach-n50-final.zip` → `thong_tin.json` (n50), `inbox/lexo-qwen3-8b-sach-n368-final/thong_tin.json` | JSON: siêu tham số, val loss theo bước, số giây, SHA256 adapter, phiên bản thư viện | adapter `.safetensors` ~167 MB mỗi cái |
| Truy hồi 58 câu (chạy cục bộ, không phải Kaggle) | `eval/ket_qua.md` | Markdown: Hit@k, MRR, hạng từng câu | bộ câu `eval/cau_hoi_thu.json` |
| Kế hoạch / quy tắc đọc kết quả đăng ký trước | `train/sach/KE_HOACH_LORA_PHAN_CON_LAI.md`, `kaggle/KE_HOACH_KAGGLE_V2.md` | Markdown | mục 5 của file đầu là bảng đọc kết quả |
| Vòng 1 trên 90 vụ bản án (notebook v2) | **chưa có kết quả** | — | `inbox/kaggle_ket_qua/` chưa tồn tại; thư mục `kaggle/` mới chỉ có 3 notebook và kế hoạch |

Không có CSDL hay file CSV tổng hợp nào có sẵn trước đây: số liệu nằm rải trong các file `.md` và `.jsonl` ở trên. File này là bản gom đầu tiên.

## 1. Huấn luyện LoRA trên Kaggle (Qwen3-8B, QLoRA nf4, T4)

Siêu tham số giống nhau cả ba lần: r16, α32, dropout 0,05, all-linear, lr 2e-4 cosine, warmup 5%, 3 epoch, micro-batch 4 × grad-acc 2, max_len 512, hạt 42, loss chỉ trên phần trả lời, `enable_thinking=False`.

| | LoRA cũ | LoRA n50 | LoRA n368 |
|---|---|---|---|
| Ngày học (UTC) | 2026-10-15 | 2026-10-15 | 2026-10-17 |
| Mẫu học / val | 397 / 53 (đếm dòng `train/sft_train.jsonl`, `sft_val.jsonl`) | 50 / 51 | 368 / 51 |
| Số bước | 150 (3 epoch × 50) | 21 | 138 |
| Thời gian học (giây) | không ghi | 317.9 (≈15.1 s/bước) | 1101.3 (≈8.0 s/bước, ≈18.4 phút) |
| Val loss ban đầu | 1.8868 | 1.8783 | 1.8783 |
| Val loss cuối | 0.6143 | 0.7418 (epoch 3) | 0.5625 (epoch 2; epoch 3 = 0.5953) |
| Val loss thấp nhất đã đo | 0.5692 (bước 100) | 0.7417 | 0.5625 |
| Sinh thử 20 mẫu val: JSON hợp lệ / có khối think / đúng số hành vi | 20/20 / 0 / không ghi | 20/20 / 0 / 17/20 | 20/20 / 0 / 19/20 |
| Mẫu bị cắt do max_len | không ghi | 0 | 0 |
| Mô hình gốc ghim | `revision` null (không ghim) | `b968826d…` | `b968826d…` |
| transformers / peft | 5.19.0 / 0.21.2 | 5.19.0 / 0.21.2 | 5.20.1 / 0.21.2 |
| SHA256 adapter | `e2b3dd622651ec9a…` | `19cf3ea4c7e0a20f…` | `4251d70ae9ad6697…` |

Val loss theo bước (bước, loss):

- LoRA cũ: 0: 1.887; 25: 0.684; 50: 0.608; 75: 0.590; 100: 0.569; 125: 0.608; 150: 0.614
- LoRA n50: 0: 1.878; 3: 1.128; 6: 0.847; 7: 0.822; 9: 0.785; 12: 0.749; 14: 0.743; 15: 0.742; 18: 0.742; 21: 0.742
- LoRA n368: 0: 1.878; 23: 0.673; 46: 0.598; 69: 0.582; 92: 0.562; 115: 0.591; 138: 0.595

Nguồn: `inbox/lexo-qwen3-8b-1/thong_tin.json`, `inbox/lexo-qwen3-8b-sach-n50-final.zip/thong_tin.json`, `inbox/ket_qua_1/thong_tin_n368.json`.

## 2. Đo tách hành vi → truy hồi trên dev 34 câu nhiều Điều (đợt 2, Ollama 0.40.4, bge-m3, chế độ vector, mỗi hành vi 3 Điều)

Tập dev: `eval/bo_cau_hoi.json` (dn01–dn34, TB 2,2 Điều đáp án/câu). **Nhãn còn `nhap`: do Claude soạn, chưa được người dùng duyệt** (xem mục 7).

### 2.1 Bảng chính (tất cả 34 câu)

| Mô hình tách | Tìm đủ | Bao phủ | Chính xác | Hành vi có đáp án | Đúng số hành vi | Điều hiển thị TB | «Không tách» cùng số Điều: tìm đủ |
|---|---|---|---|---|---|---|---|
| qwen3:8b (chỉ lời nhắc) | 14/34 (41%) | 66% | 21% | 62% | 12/34 (35%) | 7.4 | 35% (hiển thị 7.4) |
| LoRA cũ (397 mẫu, có 31 mẫu trùng tổ hợp) | 21/34 (62%) | 76% | 28% | 78% | 29/34 (85%) | 6.1 | 35% (hiển thị 6.1) |
| LoRA n50 (sạch) | 11/34 (32%) | 61% | 26% | 67% | 23/34 (68%) | 5.7 | 32% (hiển thị 5.7) |
| LoRA n368 (sạch) | 17/34 (50%) | 71% | 27% | 76% | 24/34 (71%) | 5.9 | 35% (hiển thị 5.9) |
| Tách lý tưởng, viết tay (mốc trần) | 15/34 (44%) | 62% | 24% | 66% | 34/34 (100%) | 5.9 | 32% (hiển thị 5.9) |

Mốc «không tách» (cùng cho mọi mô hình vì không dùng mô hình tách): hiển thị 3 Điều: tìm đủ 26%, bao phủ 46%, chính xác 32%; hiển thị 6 Điều: tìm đủ 35%, bao phủ 57%, chính xác 20%; hiển thị 9 Điều: tìm đủ 44%, bao phủ 63%, chính xác 15%.

Định nghĩa: **tìm đủ** = mọi Điều đáp án đều nằm trong số Điều hiển thị (chỉ số chính); **bao phủ** = phần Điều đáp án được hiển thị; **chính xác** = phần Điều hiển thị là đáp án; **hành vi có đáp án** = phần hành vi tách ra có ít nhất một Điều đáp án trong 3 Điều đầu (đo tách thừa); **đúng số hành vi** = số hành vi tách ra bằng số Điều đáp án.

### 2.2 Tách theo hai nhóm câu

dn01–dn14: đã có từ trước; LoRA cũ có mẫu học trùng tổ hợp Điều với 6/14 câu này. dn15–dn34: thêm ngày 2026-10-16, tổ hợp Điều **không trùng** bất kỳ mẫu học nào của cả bốn mô hình (theo `KE_HOACH_LORA_PHAN_CON_LAI.md` mục 3), nên là phép so sánh sạch.

| Mô hình | Tìm đủ dn01–14 | Đúng số dn01–14 | Tìm đủ dn15–34 | Đúng số dn15–34 | Điều hiển thị TB (dn01–14 / dn15–34) |
|---|---|---|---|---|---|
| qwen3:8b (chỉ lời nhắc) | 5/14 (36%) | 5/14 (36%) | 9/20 (45%) | 7/20 (35%) | 7.4 / 7.4 |
| LoRA cũ (397 mẫu, có 31 mẫu trùng tổ hợp) | 8/14 (57%) | 13/14 (93%) | 13/20 (65%) | 16/20 (80%) | 5.6 / 6.5 |
| LoRA n50 (sạch) | 4/14 (29%) | 10/14 (71%) | 7/20 (35%) | 13/20 (65%) | 5.6 / 5.8 |
| LoRA n368 (sạch) | 7/14 (50%) | 10/14 (71%) | 10/20 (50%) | 14/20 (70%) | 6.1 / 5.7 |
| Tách lý tưởng (mốc trần) | 6/14 (43%) | 14/14 (100%) | 9/20 (45%) (suy ra từ 34 − 14) | 20/20 (100%) | — |

Nguồn: `inbox/ket_qua_1/kq_nhieu_dev_<mô hình>_{tat_ca,dn01-14,dn15-34}.md` (tìm đủ và các cột %), `inbox/ket_qua_1/tach_dev_<mô hình>_thuan_0vd.log.jsonl` (đúng số hành vi: đếm các câu có `so_hanh_vi == so_dieu_dap_an`, mọi câu `loi = null`).

## 3. So sánh cặp (McNemar chính xác, hai phía) — ba so sánh đã đăng ký trước + hai so sánh phụ

Cùng bộ câu cho mọi mô hình nên dùng kiểm cặp: đếm câu mà hai mô hình cho kết quả khác nhau. Cột «hơn/kém» là số câu chỉ mô hình thứ nhất đúng / chỉ mô hình thứ hai đúng.

| So sánh | Tập | Đúng số hành vi (hơn/kém, p) | Tìm đủ (hơn/kém, p) |
|---|---|---|---|
| ① n368 so với qwen3:8b (đăng ký trước) | 34 | 13/1, p = 0.0018 | 4/1, p = 0.3750 |
| ② n368 so với n50 (đăng ký trước) | 34 | 5/4, p = 1.0000 | 6/0, p = 0.0312 |
| ③ n368 so với LoRA cũ (đăng ký trước, chỉ dn15–34) | 20 (dn15–34) | 1/3, p = 0.6250 | 0/3, p = 0.2500 |
| n368 so với LoRA cũ (phụ) | 34 | 1/6, p = 0.1250 | 1/5, p = 0.2188 |
| n50 so với qwen3:8b (phụ) | 34 | 15/4, p = 0.0192 | 0/3, p = 0.2500 |

Không hiệu chỉnh nhiều phép kiểm (5 phép trên cùng một tập 34 câu). Nhãn dev chưa được duyệt và dev đã bị «nhìn» nhiều lần nên p-value chỉ để tham khảo; kết luận cuối phải dựa vào tập kiểm tra đóng băng chạy một lần.

Theo bảng đọc đăng ký trước (`KE_HOACH_LORA_PHAN_CON_LAI.md` mục 5): n368 đạt 24/34 đúng số hành vi, dưới ngưỡng 29/34 nhưng hơn qwen3:8b có ý nghĩa → rơi vào dòng «vùng giữa, chưa kết luận».

## 4. Đợt 1 — đo 14 câu (dn01–dn14, 15/10)

| Mô hình | Tìm đủ | Bao phủ | Chính xác | Hành vi có đáp án | Đúng số hành vi | Điều hiển thị TB | Giây TB/câu |
|---|---|---|---|---|---|---|---|
| qwen3:4b (chỉ lời nhắc) | 5/14 (36%) | 49% | 14% | 43% | 6/14 (43%) | 7.4 | 2.4 |
| qwen3:8b (chỉ lời nhắc) | 5/14 (36%) | 62% | 19% | 62% | 5/14 (36%) | 7.4 | 5.0 |
| LoRA cũ | 8/14 (57%) | 70% | 26% | 74% | 13/14 (93%) | 5.6 | 2.5 |
| Tách lý tưởng (mốc trần) | 6/14 (43%) | 56% | 21% | 56% | 14/14 (100%) | 5.8 | — |

Số 14 câu đợt 1 và số 34 câu đợt 2 không phải cùng một phép đo; chỉ dùng cột dn01–dn14 của mục 2.2 để đối chiếu. Trên dn01–14, qwen3:8b và LoRA cũ cho cùng số liệu tổng ở đợt 1 và đợt 2 (tìm đủ 36% và 57%).

## 5. Thời gian và độ ổn định khi tách (34 câu, T4, Ollama)

| Mô hình | Lỗi | Khối think | Giây TB | Giây trung vị | Giây lớn nhất | Tổng giây | Hành vi TB/câu |
|---|---|---|---|---|---|---|---|
| qwen3:8b (chỉ lời nhắc) | 0/34 | 0 | 6.0 | 3.0 | 99.0 | 203 | 3.00 |
| LoRA cũ (397 mẫu, có 31 mẫu trùng tổ hợp) | 0/34 | 0 | 2.5 | 2.5 | 4.1 | 83 | 2.29 |
| LoRA n50 (sạch) | 0/34 | 0 | 2.8 | 2.6 | 6.8 | 96 | 2.26 |
| LoRA n368 (sạch) | 0/34 | 0 | 2.4 | 2.3 | 4.7 | 82 | 2.24 |

Lần chạy qwen3:8b đầu có một câu mất khoảng 99 giây (có thể do nạp mô hình lần đầu; chưa xác minh), kéo trung bình lên; trung vị 3,0 giây gần với các mô hình LoRA. Đừng dùng số trung bình để so tốc độ.

## 6. Truy hồi 58 câu (chạy cục bộ, không phải Kaggle)

Nguồn: `eval/ket_qua.md`, bộ `eval/cau_hoi_thu.json` (58 câu, nhãn đã được người dùng duyệt), bge-m3 qua Ollama, 6351 chunk.

| Chế độ | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| hybrid | 57% | 84% | 88% | 93% | 0.706 |
| vector | 64% | 84% | 88% | 95% | 0.753 |
| fts | 52% | 67% | 76% | 78% | 0.619 |

Kết quả thử câu hỏi sinh sẵn (doc2query, qwen2.5:3b) xấu hơn mốc vector và đã bị loại; số liệu chỉ nằm trong hội thoại, **chưa lưu thành file**. Chạy lại với qwen3:8b chưa làm.

## 7. Lưu ý khi dùng trong bài báo

1. **Nhãn dev chưa duyệt.** `eval/bo_cau_hoi.json`: 104 câu `dev` đều `nguon = claude`, `trang_thai = nhap`. Cùng một người soạn với dữ liệu học nên nghiêng về lạc quan. Cần ≥ 10 câu do người dùng tự viết (`nguon = nguoi_dung`) và nhờ người khác duyệt trước khi trích số.
2. **Dev đã bị nhìn nhiều lần** (mỗi lần đo lại là một lần xem), nên không dùng số dev làm kết quả cuối. Kết luận chỉ nên dựa vào tập `kiem_tra` đóng băng, chạy đúng một lần khi mô hình và tham số đã chốt.
3. **Một hạt (42), một lần chạy mỗi cấu hình.** Chưa đo độ dao động giữa các hạt (kế hoạch C1: n50 hạt 43/44). Chênh dưới khoảng 7 câu coi là nhiễu theo bảng độ lớn ở `KE_HOACH_LORA_PHAN_CON_LAI.md` mục 5.
4. **LoRA cũ không ghim commit mô hình gốc và dùng transformers 5.19.0**; n50/n368 ghim `b968826d…`; n50 dùng transformers 5.19.0, n368 dùng 5.20.1. Tập val của LoRA cũ (53 mẫu) khác tập val của n50/n368 (51 mẫu) nên val loss không so trực tiếp được giữa LoRA cũ và hai bản sạch. Nêu các khác biệt này khi so LoRA cũ với hai bản sạch.
5. **LoRA cũ đứng đầu về «đúng số hành vi» (29/34) và «tìm đủ» (21/34), hơn n368 (24/34 và 17/34)**, kể cả trên dn15–34 là nhóm sạch (16/20 so với 14/20 đúng số; 13/20 so với 10/20 tìm đủ). Chênh lệch trên nhóm sạch nhỏ (2–3 câu) và không có ý nghĩa theo kiểm cặp ở mục 3. Chưa giải thích được vì sao bản sạch n368 không vượt LoRA cũ; kế hoạch C (hạt, số mẫu, bỏ tiền tố tên tội) chưa chạy.
6. **Mốc trần cho thấy nút thắt nằm ở truy hồi, không ở khâu tách**: tách lý tưởng đúng số hành vi 100% nhưng tìm đủ chỉ 44% (15/34), thấp hơn LoRA cũ (62%) và n368 (50%). Nghĩa là «đúng số hành vi» không suy ra «tìm đủ»; báo cáo cả hai chỉ số.
7. **Hợp nhất sang GGUF Q4_K_M** nên số đo là của mô hình lượng tử hóa, không phải adapter gốc.

## 8. Chưa có số (đừng điền khống)

- Vòng 1 đo 90 vụ bản án, Vòng 2 học chọn Điều, Vòng 3, và tập test của kế hoạch v2 (`kaggle/KE_HOACH_KAGGLE_V2.md`): chưa chạy, `inbox/kaggle_ket_qua/` chưa có.
- Thời gian học và số mẫu bị cắt của LoRA cũ (`thong_tin.json` của lần đó không có hai khóa này).
- Kiểm tra đóng băng (`kiem_tra`) cho khâu tách: chưa chạy.
