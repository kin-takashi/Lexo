# Lexo — Kế hoạch học LoRA sạch (diễn tập 50 mẫu → học đủ) và các bước kiểm tra

Dán file này vào chat mới (chat xử lý Colab/Kaggle). Đọc kèm `lexo_ban_giao_colab_kaggle.md` (vai trò, lỗi thường gặp, cấm kỵ chung). File này chỉ nói **lần học tiếp theo** và **cách kiểm tra nó**.

Cách mình hiểu yêu cầu: chọn 50 mẫu học từ kho có sẵn (`train/tinh_huong.json`, không sinh thêm), dùng làm lần diễn tập; kế hoạch gồm cả các bước kiểm tra.

---

## 1. Vì sao làm lần học này

- Lần học trước (`lexo-qwen3-8b-1`) cho 8/14 câu dev "tìm đủ" (mô hình gốc 5/14), nhưng **6/14 câu dev và 11/26 câu kiem_tra nhiều Điều có một mẫu học trùng đúng tổ hợp Điều** (31 mẫu học; lúc đầu đếm 30 và 10/26, thiếu trường hợp chỉ khớp theo Điều đầu tiên). Mức hơn mô hình gốc nằm hết ở ba câu có mẫu trùng (dn02, dn05, dn06); trên 8 câu không trùng, LoRA và mô hình gốc cùng 4/8. Chưa kết luận được LoRA tốt hơn trên tình huống mới.
- Việc cần làm: học lại trên dữ liệu **đã loại mẫu trùng**, để có con số sạch.
- Lần 50 mẫu là **diễn tập rẻ**: chạy trơn cả chuỗi học → hợp nhất → GGUF → Ollama → đo trên dev trước khi tốn công học đủ; đồng thời cho điểm đầu của đường cong "số mẫu → kết quả".

Ba câu hỏi lần này trả lời:
1. Khi bỏ mẫu trùng, LoRA còn hơn mô hình gốc không? (so với mốc ở mục 5)
2. Cần bao nhiêu mẫu? (50 / 100 / 200 / 368)
3. (Tùy chọn) Tiền tố tên tội ("Hiếp dâm: …") giúp hay hại? Lần trước 3/6 câu sai là do tên tội sai.

---

## 2. Dữ liệu (ĐÃ XONG, sinh bằng `python scripts/chon_mau_hoc.py`, hạt 42)

Thư mục `train/sach/` (đã đóng gói `lexo_hoc_sach.zip`; kiểm mã băm theo `SHA256SUMS`):

| File | Mẫu | Hành vi | Điều khác nhau | Số hành vi/mẫu (1 / 2 / 3 / 4+) |
|---|---|---|---|---|
| `sft_train_n50.jsonl` | 50 | 99 | 82 | 13 / 28 / 6 / 3 |
| `sft_train_n100.jsonl` | 100 | 196 | 138 | 26 / 57 / 12 / 5 |
| `sft_train_n200.jsonl` | 200 | 398 | 224 | 51 / 113 / 24 / 12 |
| `sft_train_sach.jsonl` (đủ) | 368 | 729 | 297 | 95 / 207 / 45 / 21 |
| `sft_val_sach.jsonl` (chỉ theo dõi loss) | 51 | 99 | 71 | 11 / 33 / 6 / 1 |
| `xep_hang.json` | hạt, thứ tự, 31 id bị loại, mã băm nguồn | | | |

Cách chọn (không dùng nội dung bộ đo, chỉ so danh sách Điều đáp án):
- Kho 450 mẫu → loại 31 mẫu có tập Điều trùng một câu nhiều Điều của bộ đo (29 ở phần train, 2 ở val) → còn 419 = 368 train + 51 val. Val giữ cách chia cũ (băm theo id).
- 31 id bị loại: t002 t003 t004 t005 t017 t018 t043 t046 t057 t067 t085 t136 t139 t156 t165 t219 t248 t256 t273 t337 t353 t354 t357 t358 t367 t368 t378 t400 t410 t429 t434 (t003 chỉ trùng khi tính theo Điều đầu tiên; loại luôn cho chắc).
- Tập con **lồng nhau**: xếp hạng 368 mẫu một lần, phân tầng theo số hành vi, rồi lấy k mẫu đầu → n50 ⊂ n100 ⊂ n200 ⊂ đủ. Đã kiểm: chạy lại ra cùng mã băm; mỗi dòng giống hệt dòng trong `sft_train.jsonl` gốc; 0 mẫu trùng bộ đo; train và val không giao nhau.
- 50 id của n50: t006 t030 t040 t041 t044 t053 t061 t063 t065 t070 t072 t074 t076 t083 t098 t114 t122 t142 t143 t149 t152 t153 t167 t169 t171 t190 t202 t223 t224 t241 t250 t254 t257 t259 t262 t271 t275 t297 t302 t313 t319 t322 t329 t346 t347 t369 t370 t374 t426 t444

Mã băm SHA256:
```
756fc931520933c3de9b8dfe446a845c1511632b7ef64838e21d3d5809849554  sft_train_n50.jsonl
d01141f0031c4e32af9ce99a774a9cf7bafc9d92e9877f96f8d1624db97a1d39  sft_train_n100.jsonl
4e3c65ac8e2bf8e540473ea88c9439ad5bdcf2f7695ffb9f97a8d2e9d41cc632  sft_train_n200.jsonl
8755721748c92055956d4024456871dcac1d89117c354ea9c60ddd6931de959f  sft_train_sach.jsonl
4acc133295a9dc77508e6c8c1c7a6d6f16e3859d4680f07af35c4abcecacefd2  sft_val_sach.jsonl
f5c5aca1c2bd012ae06a898996b023ea8fe42161f3946733c58da4673317f4ea  xep_hang.json
```

Điều cần biết về dữ liệu (ảnh hưởng cách đọc kết quả):
- **Rộng mà nông**: 729 hành vi trải trên 297 Điều (mỗi Điều chỉ 2–3 hành vi). Mô hình không thể học thuộc "hành vi → Điều"; nó học **quy ước tách** (đếm hành vi, độ dài, tình tiết). Đích học không có số Điều.
- Có tiền tố tên tội ở 46% hành vi (332/729; n50: 46/99). Phần còn lại không có.
- Độ dài: tình huống học TB 180–190 ký tự (tối đa 332); câu nhiều Điều của bộ đo TB 227 ký tự (dev 239; tối đa 297), tức dài hơn ~20%. Lệch nhẹ, ghi nhận, không xử lý.
- Cả 3 vai (system + tình huống + đích) tối đa 1051 ký tự (n50: 949). `max_len` = 512 có thể cắt một vài mẫu → phải đếm token thật (bước 1.1).

---

## 3. Kế hoạch học

Thứ tự và cổng chuyển giai đoạn (cổng chỉ xét kỹ thuật, không xét điểm dev, để khỏi chỉnh theo dev):

| Giai đoạn | Chạy | Mục đích | Sang giai đoạn sau khi |
|---|---|---|---|
| A. Diễn tập | `n50`, hạt 42 | Chạy trơn cả chuỗi; điểm đầu đường cong | Qua cổng G1–G4 (mục 4) |
| B. Học đủ sạch | `sft_train_sach` (368) | **Mô hình có giá trị** để so sánh với mốc | Qua G1–G4 |
| C. Tùy chọn | `n100`, `n200`; n50 thêm hạt 43, 44; bản bỏ tiền tố (dữ liệu bản này chưa làm, xin từ chat gốc) | Đường cong; đo độ dao động giữa các hạt; câu hỏi 3 | Chỉ khi A, B xong và còn thời gian |

**Giữ nguyên** so với lần trước (để so sánh công bằng): Qwen/Qwen3-8B, QLoRA nf4 + double quant (compute fp16), r 16, alpha 32, dropout 0.05, target all-linear, lr 2e-4 cosine, warmup 5%, 3 epoch, micro-batch 4 × grad-acc 2, hạt 42, loss chỉ trên assistant, `enable_thinking=False` (khối think rỗng), **system prompt khớp từng ký tự** với `HE_THONG` trong dữ liệu (đã nằm sẵn trong từng dòng).

**Đổi** (và ghi đủ vào `thong_tin.json`):
1. Dữ liệu: các file ở mục 2 (không dùng `sft_train.jsonl`/`sft_val.jsonl` cũ).
2. Ghim phiên bản mô hình gốc: lần trước `revision = null`. Lần này ghi lại mã commit thực dùng (ví dụ `model.config._commit_hash`) và dùng lại đúng mã đó cho mọi lần sau, kể cả lúc hợp nhất.
3. Đếm token thật trước khi học; nếu mẫu dài nhất > 480 token thì nâng `max_len` (640 hoặc 768) và ghi lại; không để cắt âm thầm.
4. Đo val loss ~8 lần mỗi lượt học (n50 ≈ 20 bước nên đo mỗi 3 bước; đủ ≈ 138 bước nên đo mỗi 17–23 bước).
5. Ghi thêm: số bước, số giây học, số mẫu bị cắt (phải 0), phiên bản thư viện.
6. Lần học đủ: lưu adapter cuối epoch 2 và epoch 3; **chọn theo val loss thấp nhất** (chênh dưới 0.01 thì lấy epoch sớm hơn), tuyệt đối không chọn theo điểm dev.

Số bước ước tính (3 epoch, 8 mẫu/bước): n50 ≈ 20, n100 ≈ 38, n200 ≈ 75, đủ ≈ 138 (lần trước 397 mẫu = 150 bước, khớp). **Lưu ý**: n50 được cập nhật ít bước hơn nhiều, nên đường cong lẫn lộn "ít mẫu" với "ít bước"; ghi nhận, không sửa (đổi epoch giữa các lần sẽ làm mất so sánh).

Tên: adapter `lexo-qwen3-8b-sach-n50`, `lexo-qwen3-8b-sach-n368` (…`-n100`, `-n200`); Ollama `qwen3-8b-lexo-sach-n50`, … (**tên phải chứa "qwen3"**, vì `la_model_nghi` nhận theo tên).

---

## 4. Các bước kiểm tra (mỗi lần học đều chạy đủ, theo thứ tự)

**Bước 0 — Dữ liệu (đã xong ở máy gốc).** Xác định (chạy lại cùng mã băm), lồng nhau, 0 trùng bộ đo, mỗi dòng khớp bản gốc, 5 test mới qua (`tests/test_chon_mau.py`). Việc còn lại: ở chỗ học, `sha256sum -c SHA256SUMS` phải báo OK cả 6 file.

**Bước 1 — Trước khi học (GPU).**
- 1.1 Đếm token toàn bộ train + val bằng đúng hàm dựng chuỗi của notebook học; in tối đa/trung bình/số mẫu > `max_len`. Phải 0 mẫu bị cắt.
- 1.2 In phiên bản torch/transformers/peft/bitsandbytes, mã commit mô hình gốc.
- 1.3 Học thử 2 bước để thấy loss không NaN, rồi mới chạy thật.

**Bước 2 — Cổng G1, sau khi học.**
- Val loss giảm rõ so với bước 0, không có NaN.
- Sinh thử 20 mẫu val: `json_hop_le` 20/20, `co_khoi_think` 0 (mốc lần trước: 20/20 và 0).
- Lưu adapter + `thong_tin.json` + đường val loss theo bước. Lần trước val loss thấp nhất ở bước 100 (0.569) rồi tăng lên 0.614 ở bước 150: dấu hiệu quá khớp sau epoch 2 → theo dõi lần đủ.

**Bước 3 — Cổng G2, hợp nhất → GGUF Q4_K_M** (notebook Kaggle CPU như lần trước): kiến trúc qwen3, 399 tensor, có chat template, ghi kích thước + SHA256 + mã commit llama.cpp vào `merge_info.json`.

**Bước 4 — Cổng G3, chạy thử 3 câu** (`--chi-id dn01,dn02,dn13`): `ollama create` từ GGUF dùng lại khuôn mẫu của `qwen3:8b`; 3/3 `loi=None`, không có `<think>`, `ollama ps` cho thấy nằm trên GPU.

**Bước 5 — Cổng G4 + đo A/B trên 14 câu dev** (notebook `lexo_chay_thu_colab.ipynb`, ô 7). Cờ giữ y hệt lần trước: `--tap dev --kieu thuan --vi-du 0 --khong-no-think`; sau mỗi mô hình `ollama stop`; rồi `danh_gia_nhieu.py --tap dev --chi-tiet --luu`. Chạy cùng lượt: `qwen3:8b` (mô hình gốc, để cùng phiên bản Ollama), mô hình mới, và nếu muốn mô hình cũ `qwen3-8b-lexo-tach`. G4: 14/14 câu `loi=None`, 0 khối think.

**Bước 6 — Điền bảng kết quả** (mục 6) và gửi về chat gốc cùng các file ở mục 7.

**Bước 7 — Phân tích lỗi theo câu** (làm ở chat gốc có mã nguồn): với mỗi câu còn thiếu Điều, phân loại: (a) tên tội sai/bịa, (b) tách đúng nhưng tìm trượt top 3, (c) sót hành vi, (d) thừa hành vi. Đối chiếu với danh sách câu từng có mẫu trùng (dn01, dn02, dn05, dn06, dn07, dn11).

**Bước 8 — Chưa làm ở đây:** chạy kiem_tra khóa đúng một lần (`--da-chot`) chỉ sau khi tham số và mô hình đã chốt. Không nằm trong kế hoạch này.

---

## 5. Mốc để so sánh (dev, 14 câu, cùng bộ đo, Ollama 0.40.4)

| Cấu hình | Tìm đủ | Bao phủ | Chính xác | Đúng số hành vi | Điều hiển thị TB |
|---|---|---|---|---|---|
| Chỉ lời nhắc, 4B | 5/14 (36%) | 49% | 14% | 6/14 | 7.4 (tách thừa) |
| Chỉ lời nhắc, 8B | 5/14 (36%) | 62% | 19% | 5/14 | 7.4 (tách thừa) |
| Không tách, cùng số Điều hiển thị | 4/14 (29%) | 46% | 13–17% | – | 5.6–7.4 |
| Tách lý tưởng (người soạn viết hành vi) | 6/14 (43%) | 56% | 21% | 14/14 | 5.8 |
| 8B + LoRA cũ (có 31 mẫu trùng) | **8/14 (57%)** | 70% | 26% | **13/14 (93%)** | 5.6 |

Bao phủ và chính xác là trung bình theo câu. Hàng "không tách" lấy theo ngân sách Điều của bản tách (ở ngân sách 5.8 của tách lý tưởng là 3/14).

Khi tách đúng, tìm Điều theo hành vi (top 3) đúng khoảng 74% → tìm đủ ≈ 0.74^2.1 ≈ 53% (đo được 57%): **nút thắt hiện là truy hồi, không phải khâu tách.**

---

## 6. Cách đọc kết quả (ghi trước khi có số, để khỏi chữa cháy sau)

Với n = 14, một câu ≈ 7 điểm phần trăm. Fisher hai phía: 8/14 so 4/14 → p = 0.25; 9/14 so 5/14 → p = 0.26; 10/14 so 5/14 → p = 0.13. **Chênh dưới 3 câu về "tìm đủ" coi như nhiễu.** Chỉ số ổn định hơn để phân biệt: **đúng số hành vi** (13/14 so 5/14 có p = 0.004) và **Điều hiển thị TB**. Báo cả bao phủ và chính xác (%).

| Nếu thấy (mô hình đủ sạch, n368) | Thì | Làm gì |
|---|---|---|
| Đúng số hành vi ≥ 12/14 và Điều hiển thị TB ≤ 6.5 | LoRA học được quy ước tách, không phụ thuộc mẫu trùng | Giữ; chuyển sang cải thiện truy hồi |
| Đúng số hành vi ≈ mô hình gốc (≤ 7/14) | Lợi ích lần trước chủ yếu từ mẫu trùng | Báo cáo con số sạch; xem lại dữ liệu và prompt |
| Tìm đủ ≥ 8/14 nhưng đúng số hành vi thấp | Chưa rõ (nhiễu hoặc đường khác) | Mở rộng dev (mục 8) rồi đo lại |
| n200 và n368 chênh ≤ 1 câu tìm đủ và ≤ 1 câu đúng số | Bão hòa: thêm mẫu cùng kiểu không giúp | Đầu tư truy hồi/reranker, không thêm mẫu |
| n50 thấp hơn rõ n368 (đúng số hơn 3 câu) | Đường cong còn lên | Thêm mẫu nhiều hành vi (3–5 hành vi) |

Dự đoán (chỉ là đoán, chưa đo): n50 nằm giữa mô hình gốc và n368 ở "đúng số hành vi".

Bảng điền (mỗi dòng một mô hình):

| Mô hình | Tìm đủ /14 | Bao phủ % | Chính xác % | Đúng số hành vi /14 | Điều hiển thị TB | Câu thiếu |
|---|---|---|---|---|---|---|
| qwen3:8b (chạy lại) | | | | | | |
| sach-n50 | | | | | | |
| sach-n368 | | | | | | |

---

## 7. Mang về chat gốc

Từng lần học: thư mục adapter (`adapter_model.safetensors`, `adapter_config.json`, `thong_tin.json` với val loss theo bước, số bước, số giây, mã commit mô hình gốc), `merge_info.json`, `kq_nhieu_dev_*.md`, `tach_dev_*.json`, `tach_dev_*.log.jsonl`, đoạn `ollama --version`, ghi chú mọi lỗi gặp và cách sửa. **Chưa xóa GGUF cũ** trước khi bản mới qua G3.

---

## 8. Cấm kỵ và rủi ro

Cấm:
- Không đưa `eval/bo_cau_hoi.json` (hay bất kỳ câu dev/kiem_tra/xac_nhan/phu) vào notebook học. Notebook học chỉ nhận `lexo_hoc_sach.zip`; `lexo_eval_colab.zip` (có bộ đo) chỉ dùng ở notebook đo, sau khi đã có GGUF.
- Không chọn adapter/epoch/siêu tham số theo điểm dev. Chọn theo val loss; ghi lại **mọi** lần chạy (kể cả lần xấu).
- Không chạy kiem_tra, xac_nhan, phu ở đây. Không sinh mẫu học từ câu của bộ đo.
- Không đổi siêu tham số giữa các lần ngoài những gì ghi ở mục 3.

Rủi ro đã biết:
- n = 14 quá nhỏ; mỗi lần đo lại trên cùng dev là thêm một lần "nhìn dev" → nghiêng về lạc quan. Kết luận cuối chỉ dựa kiem_tra khóa.
- Lệch độ dài (mục 2), tập học rộng-nông.
- Phiên bản Ollama/llama.cpp đổi có thể đổi chút kết quả: chạy lại `qwen3:8b` cùng lượt.
- Kaggle/Colab: lỗi thường gặp đã ghi trong `lexo_ban_giao_colab_kaggle.md` (đường dẫn `/kaggle/input/datasets/<user>/<slug>/…`, zip tự giải nén, `/kaggle/input` chỉ đọc, hết RAM/VRAM, fp16 NaN, mất kết nối).

Việc ở chat gốc (có mã nguồn), song song hoặc sau:
- Soạn thêm 15–20 câu dev nhiều Điều **có tổ hợp không trùng mẫu học** (kiểm bằng `mau_trung`), bạn duyệt trước khi dùng.
- Thêm kiểm tra "tập học ↔ bộ đo trùng tổ hợp Điều" vào `scripts/kiem_tra_train.py` (hiện mới có script riêng `chon_mau_hoc.py`).
- Bản bỏ tiền tố tên tội (câu hỏi 3) và cải thiện truy hồi theo hành vi (reranker, m lớn hơn), chỉ chỉnh trên dev.

---

## 9. Tin nhắn đầu tiên gợi ý cho chat mới

> Mình đang làm đồ án Lexo (tra cứu luật hình sự VN, chạy local). Đính kèm: `KE_HOACH_HOC_50.md`, `lexo_ban_giao_colab_kaggle.md`, `lexo_hoc_sach.zip` (dữ liệu học sạch, có SHA256SUMS), `lexo_eval_colab.zip` và `lexo_chay_thu_colab.ipynb` (để đo). Việc: làm **Giai đoạn A** (học LoRA Qwen3-8B trên `sft_train_n50.jsonl`, val `sft_val_sach.jsonl`), qua các cổng G1–G4, rồi báo mình các file cần mang về. Mình chỉ dùng laptop, GPU là Kaggle/Colab T4. Khi gặp lỗi, đưa nguyên văn lỗi, nguyên nhân gốc và cách sửa tối thiểu; không đổi siêu tham số ngoài kế hoạch.
