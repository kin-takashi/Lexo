# Lexo — Kế hoạch LoRA phần còn lại (sau lần diễn tập n50) và cách đo trên dev mở rộng

Dán file này vào chat Kaggle/Colab cùng `KE_HOACH_HOC_50.md` và `lexo_ban_giao_colab_kaggle.md`. File này **không lặp lại** những gì đã có ở `KE_HOACH_HOC_50.md` (dữ liệu, siêu tham số, các cổng G1–G4, cách chạy đo); nó chỉ nói: (1) n50 cho biết gì, (2) việc còn lại của LoRA theo thứ tự, (3) bộ đo mới 34 tình huống và cách chạy, (4) quy tắc đọc kết quả đã hiệu chỉnh theo cỡ mẫu mới.

Cách mình hiểu yêu cầu: lập kế hoạch cho phần LoRA còn lại (Giai đoạn B trở đi) và đóng gói 20 câu hỏi mới thành MỘT file (`lexo_cau_hoi_moi.zip`) để phủ lên bộ đo trên Kaggle.

---

## 1. Hiện trạng sau n50 (dev 14 câu, Ollama 0.40.4)

| Cấu hình | Tìm đủ | Bao phủ | Chính xác | Hành vi có đáp án | Đúng số hành vi | Điều hiển thị TB |
|---|---|---|---|---|---|---|
| 8B chỉ lời nhắc | 5/14 | 62% | 19% | 62% | 5/14 | 7.4 |
| Tách lý tưởng (viết tay) | 6/14 | 56% | 21% | 56% | 14/14 | 5.8 |
| LoRA cũ (31 mẫu học trùng tổ hợp) | 8/14 | 70% | 26% | 74% | 13/14 | 5.6 |
| **LoRA n50 (sạch)** | **4/14** | 56% | 23% | 67% | **10/14** | 5.6 |

Kỹ thuật (n50): 21 bước, 318 s (15,1 s/bước), val loss 1,878 → 0,742 (gần phẳng hai epoch cuối), JSON hợp lệ 20/20, 0 khối think, đúng số hành vi 17/20 trên mẫu val; adapter sha256 `19cf3ea4c7e0a20f4e8c22ae0afdc0ca9b99a44cda0325aa386c33bbe12bf474`; mô hình gốc ghim ở `b968826d9c46dd6066d109eabc6255188de91218`; mẫu dài nhất 319 token nên `max_len` 512 an toàn (0 mẫu bị cắt).

Đọc đúng (đừng đọc quá):
- Đã học được một phần **quy ước tách** (đúng số hành vi 10/14 so với 5/14 của mô hình gốc; Fisher p = 0,13, chưa đủ để khẳng định ở n = 14).
- **Chưa** thấy lợi ích ở "tìm đủ" (4/14 so với 5/14, p = 1,0). Mức 8/14 của LoRA cũ nằm hết ở ba câu có mẫu học trùng (dn02, dn05, dn06); trên 8 câu không trùng LoRA cũ và mô hình gốc cùng 4/8.
- Nút thắt của "tìm đủ" là **truy hồi theo hành vi** (khi tách đúng, top 3 đúng khoảng 74% mỗi hành vi → tìm đủ ≈ 0,74^2,1 ≈ 53%), không phải khâu tách.
- n50 chỉ có 21 bước cập nhật; chưa biết là "ít mẫu" hay "ít bước" gây ra điều trên. Cách duy nhất để biết là Giai đoạn B.

Hệ quả cho kế hoạch: mục tiêu của LoRA còn lại là **có một con số sạch cho khâu tách** (n368), không phải đuổi theo điểm "tìm đủ" trên dev.

---

## 2. Thứ tự việc còn lại

| Bước | Việc | Điều kiện sang bước sau |
|---|---|---|
| **B** | Học `sft_train_sach.jsonl` (368 mẫu), val `sft_val_sach.jsonl`, hạt 42 → hợp nhất → GGUF → Ollama | Qua G1–G4 |
| **Đo** | Phủ `lexo_cau_hoi_moi.zip`, đo 4 mô hình trên dev 34 câu (mục 4) | Có đủ file mục 7 |
| **Quyết** | Đọc bảng theo mục 5, chốt: giữ n368 làm mô hình tách hay cần thêm Giai đoạn C | Làm ở chat gốc |
| C (tùy) | Chỉ khi kết quả rơi vào vùng giữa ở mục 5: n50 hạt 43/44, n100, n200, bản bỏ tiền tố | — |

### Giai đoạn B — học đủ sạch (việc chính)

Giữ nguyên y hệt `KE_HOACH_HOC_50.md` mục 3 (Qwen3-8B ghim đúng mã commit ở trên, QLoRA nf4 + double quant, r16/α32/dropout 0,05, all-linear, lr 2e-4 cosine, warmup 5%, 3 epoch, micro-batch 4 × grad-acc 2, hạt 42, loss chỉ trên assistant, `enable_thinking=False`, `HE_THONG` khớp từng ký tự). Chỉ khác:

| Mục | Giá trị |
|---|---|
| Dữ liệu | `sft_train_sach.jsonl` (368 mẫu, 729 hành vi, 297 Điều); val `sft_val_sach.jsonl` (51 mẫu). Kiểm `sha256sum -c SHA256SUMS` trong `lexo_hoc_sach.zip`: OK cả 6 file |
| Số bước | 46 bước/epoch × 3 = **138 bước** |
| Đo val loss | `eval_steps = 23` → bước 23, 46, 69, 92, 115, 138 (trùng cuối mỗi epoch ở 46, 92, 138) |
| Lưu adapter | `save_steps = 46` → ba điểm: cuối epoch 1, 2, 3 (mỗi cái ~160 MB; để trong `/kaggle/working`) |
| Chọn adapter | **Val loss thấp nhất** trong ba điểm; nếu hai điểm chênh dưới 0,01 thì lấy điểm sớm hơn. Cấm chọn theo điểm dev. Lần cũ val loss thấp nhất ở bước 100 rồi tăng nên phải theo dõi quá khớp |
| `max_len` | giữ 512 (mẫu dài nhất 319 token), nhưng **vẫn đếm token thật và in số mẫu bị cắt = 0** trước khi học |
| Thời gian | ước tính ≈ 35 phút (15,1 s/bước × 138 bước; chỉ là ngoại suy từ n50, chưa đo). Ghi lại thời gian thật để lần sau ước tính |
| Tên | adapter `lexo-qwen3-8b-sach-n368`; Ollama `qwen3-8b-lexo-sach-n368` (tên phải chứa "qwen3") |

Cổng sau khi học (không xét điểm dev):
- **G1**: val loss giảm, không NaN; sinh thử 20 mẫu val → `json_hop_le` 20/20, `co_khoi_think` 0. Ghi (không dùng làm cổng) số mẫu đúng số hành vi trên 20 mẫu đó (n50: 17/20).
- **G2**: hợp nhất → GGUF Q4_K_M (notebook CPU như lần trước): kiến trúc qwen3, 399 tensor, có chat template; ghi kích thước, SHA256, mã commit llama.cpp vào `merge_info.json`.
- **G3**: `tach_hanh_vi.py --chi-id dn01,dn02,dn13` (lưu ý: ở script tách `--chi-id` chỉ nhận danh sách cách nhau dấu phẩy, không nhận khoảng): 3/3 `loi=None`, không có `<think>`, `ollama ps` cho thấy nằm trên GPU.
- **G4**: ở bước đo (mục 4): **34/34** câu `loi=None`, 0 khối think.

### Giai đoạn C — tùy chọn (chỉ làm khi cần, theo thứ tự ưu tiên)

| Chạy | Dùng để | Chi phí học ước tính (15,1 s/bước) | Ghi chú |
|---|---|---|---|
| C1. n50 hạt 43 và 44 | Đo độ dao động giữa các hạt: xem 10/14 của n50 là "tín hiệu" hay "may" | ≈ 5 phút mỗi lần, nhưng mỗi lần vẫn phải hợp nhất + đo | Rẻ nhất để hiểu độ nhiễu; nên làm trước C2 nếu B cho kết quả mập mờ |
| C2. n100, n200 | Vẽ đường cong "số mẫu → kết quả" (50/100/200/368 lồng nhau) | n100 ≈ 38 bước ≈ 10 phút; n200 ≈ 75 bước ≈ 19 phút | Đường cong lẫn lộn "ít mẫu" với "ít bước" (giữ 3 epoch cho mọi n) |
| C3. Bản bỏ tiền tố tên tội | Trả lời: tiền tố ("Hiếp dâm: …", ở 46% hành vi) giúp hay hại truy hồi? Lần cũ 3/6 câu sai là do tên tội sai | như B | **Dữ liệu bản này chưa làm**: xin ở chat gốc (cần sinh từ cùng danh sách 368 mẫu, cùng hạt, để so sánh công bằng) |

Chưa đề xuất: đổi siêu tham số (r, lr, epoch), học trên bộ đo, học thêm mẫu mới. Mọi thay đổi như vậy làm mất khả năng so sánh với n50/n368.

---

## 3. Bộ đo mở rộng: `lexo_cau_hoi_moi.zip`

Một file zip (38,5 KB, sha256 `d5d4b42ad9f4f206a9ec6ccabc9c8a05628158a6c76d650e42a701765e54d76d`) phủ lên `lexo_eval_colab.zip`. Đã so từng file với gói cũ: ngoài 4 file dưới đây mọi file giống hệt.

| File trong gói | Thay đổi |
|---|---|
| `eval/bo_cau_hoi.json` | 350 → 370 câu; dev nhiều Điều **14 → 34 tình huống, 74 Điều đáp án** (thêm dn15–dn34) |
| `eval/tach_ly_tuong_dev.json` | thêm hành vi viết tay cho dn15–dn34 (mốc "tách lý tưởng"), đủ 34 |
| `scripts/danh_gia_nhieu.py` | thêm `--chi-id` (nhận khoảng như `dn01-dn14` hoặc danh sách) |
| `src/index/bo_cau_hoi.py` | thêm hàm `loc_theo_id` |

Cách phủ: giải nén `lexo_eval_colab.zip` như thường, rồi chạy **một ô** dán nguyên `o_phu_len_kaggle.py` (có trong gói). Ô tự tìm gói (thư mục Kaggle đã giải nén hoặc file zip) bằng file `LEXO_CAU_HOI_MOI.md`, kiểm SHA256 nguồn, chép đè 4 file, kiểm lại, và **dừng nếu số đếm không đúng 34 tình huống / 74 Điều / 370 câu**. Đã chạy thử trong môi trường giả lập Kaggle (cả hai trường hợp: tự giải nén và chỉ có zip; hash hỏng thì dừng).

Về 20 câu mới:
- Tổ hợp Điều của cả 20 câu **không trùng** tổ hợp nào trong 450 mẫu học (kiểm bằng `mau_trung`: 0 trùng) và không trùng 40 câu nhiều Điều cũ; không có mẫu học nào bị loại thêm so với 31 mẫu đã loại. Vì vậy dn15–dn34 **sạch cho cả bốn mô hình**, kể cả LoRA cũ. Trong khi dn01–dn14 chỉ sạch với mô hình mới (LoRA cũ trùng 6/14).
- Câu hỏi không chứa "điều / khoản / bộ luật"; hành vi là mô tả đời thường, không kèm tên tội.
- Do Claude soạn, nhãn còn `nhap` (chờ người dùng duyệt, xem `eval/xem_duyet_dev_mo_rong.md`). Cùng một người soạn với dữ liệu học nên nghiêng về lạc quan.

---

## 4. Cách đo trên dev 34 câu (thay Ô 7 của `lexo_chay_thu_colab.ipynb`)

Bốn mô hình, mỗi mô hình tách **một lần** trên cả 34 câu rồi chấm **ba báo cáo** từ cùng một file dự đoán (toàn bộ, dn01–dn14, dn15–dn34):

| Mô hình | Tên Ollama | Nguồn |
|---|---|---|
| Gốc, chỉ lời nhắc | `qwen3:8b` | `ollama pull` |
| LoRA cũ | `qwen3-8b-lexo-tach` | `qwen3-8b-lexo-q4_k_m.gguf` (sha256 đầu `f8c17781…`, như Ô 2 của notebook) |
| LoRA n50 (sạch) | `qwen3-8b-lexo-sach-n50` | GGUF n50 còn trên Kaggle; nếu mất, hợp nhất lại từ adapter n50 (`lexo-qwen3-8b-sach-n50-final.zip`) |
| LoRA n368 (sạch) | `qwen3-8b-lexo-sach-n368` | kết quả Giai đoạn B |

```bash
%%bash
cd /content/lexo        # hoặc thư mục dự án trên Kaggle
for mo in qwen3:8b qwen3-8b-lexo-tach qwen3-8b-lexo-sach-n50 qwen3-8b-lexo-sach-n368; do
  t=$(echo "$mo" | tr ':' '-')
  P="eval/tach_dev_${t}_thuan_0vd.json"
  python scripts/tach_hanh_vi.py --tap dev --model "$mo" --kieu thuan --vi-du 0 --khong-no-think
  ollama stop "$mo"
  python scripts/danh_gia_nhieu.py --tap dev --du-doan "$P" --chi-tiet --luu "eval/kq_nhieu_dev_${t}_tat_ca.md"
  python scripts/danh_gia_nhieu.py --tap dev --du-doan "$P" --chi-id dn01-dn14 --chi-tiet --luu "eval/kq_nhieu_dev_${t}_dn01-14.md"
  python scripts/danh_gia_nhieu.py --tap dev --du-doan "$P" --chi-id dn15-dn34 --chi-tiet --luu "eval/kq_nhieu_dev_${t}_dn15-34.md"
  # nếu hết đĩa: ollama rm "$mo" (trừ qwen3:8b) sau khi xong mô hình đó
done
# mốc trần: hành vi viết tay
python scripts/danh_gia_nhieu.py --tap dev --du-doan eval/tach_ly_tuong_dev.json --chi-tiet --luu eval/kq_nhieu_dev_tran_tat_ca.md > /dev/null
```

Lưu ý:
- Cờ giữ y hệt lần trước: `--kieu thuan --vi-du 0 --khong-no-think`. Chạy lại `qwen3:8b` **cùng lượt** (cùng phiên bản Ollama).
- Các file `eval/tach_dev_*_thuan_0vd*` và `eval/kq_nhieu_dev_*` hiện có chỉ phủ 14 câu và sẽ bị **ghi đè** khi chạy lại (tập dev được phép ghi đè). **Trước khi chạy**, chép chúng sang `eval/_14cau/` (kể cả kết quả n50 trên Kaggle). Bản 14 câu của lần chạy Colab trước (4B, 8B, LoRA cũ, tách lý tưởng) đã có ở `inbox/ket_qua/` trên laptop. Không so số 14 câu cũ với số 34 câu mới như cùng một phép đo; số 14 câu cũ chỉ để đối chiếu cho dn01–dn14.
- Mỗi lần tách có `*.log.jsonl` (số hành vi, số Điều đáp án, giây, lỗi từng câu): đó là nguồn cho kiểm cặp ở mục 5. `--chi-tiet` liệt kê câu thiếu Điều: đó là nguồn "tìm đủ" từng câu.
- Với 34 câu, TB 2,18 Điều đáp án/câu; số "Điều hiển thị" sẽ khác chút so với 14 câu vì số hành vi TB khác.

---

## 5. Cách đọc kết quả (ghi trước khi có số)

**Chỉ số chính cho khâu tách: "đúng số hành vi"** (/34), phụ: Điều hiển thị TB, hành vi có đáp án. "Tìm đủ" là chỉ số hạ nguồn bị truy hồi chi phối nên chỉ báo cáo, không dùng để chọn mô hình tách.

**So sánh đã đăng ký trước (chỉ 3, còn lại là mô tả):**
1. n368 so với `qwen3:8b` chỉ lời nhắc, trên 34 câu (LoRA có học được quy ước tách không?).
2. n368 so với n50, trên 34 câu (thêm mẫu có giúp không?).
3. n368 so với LoRA cũ, **chỉ trên dn15–dn34** (mẫu trùng có thực sự tạo ra lợi thế của LoRA cũ không?).

**Độ lớn chênh đủ tin** (Fisher hai phía, hai nhóm độc lập; tính cho nền khoảng 30–60%):

| Cỡ mẫu | Chênh cần để p < 0,05 | để p < 0,10 |
|---|---|---|
| 14 (cũ) | 6–7 câu | 6 |
| 20 (dn15–dn34) | 7–8 câu | 6–7 |
| 34 (toàn bộ) | 9–10 câu | 8 |

Cùng bộ câu cho mọi mô hình, nên dùng **kiểm cặp** (McNemar chính xác, trên d câu mà hai mô hình cho kết quả khác nhau): bên thắng cần ít nhất 8/8 (d = 8), 9/10 (d = 10), 10/12 (d = 12), 12/14 (d = 14), 13/16 (d = 16), 15/20 (d = 20) để p < 0,05. Khoảng Wilson 95% cho một tỷ lệ: 17/34 → 34–66%; 10/20 → 30–70%. Tức là **mọi chênh dưới ~7 câu coi là nhiễu**.

| Nếu thấy (n368, 34 câu) | Thì | Làm gì |
|---|---|---|
| Đúng số hành vi ≥ 29/34, Điều hiển thị TB ≤ 6,5, hơn `qwen3:8b` có ý nghĩa theo kiểm cặp | LoRA học được quy ước tách, không dựa vào mẫu trùng | Giữ n368 làm mô hình tách; dồn công sang truy hồi theo hành vi |
| Đúng số hành vi ≥ 29/34 nhưng tìm đủ không hơn `qwen3:8b` quá 3 câu | Tách tốt, nút thắt ở truy hồi | Như trên; báo cáo trung thực rằng lợi ích LoRA là ở số hành vi/độ dài, chưa ở "tìm đủ" |
| Đúng số hành vi chỉ ngang `qwen3:8b` (chênh dưới ~5 câu) | Lợi ích LoRA cũ chủ yếu do mẫu trùng | Báo số sạch; xem lại dữ liệu và lời nhắc; bỏ ý định thêm LoRA |
| Vùng giữa (n368 hơn `qwen3:8b` nhưng < 29/34) | Chưa kết luận | Làm C1 (hạt 43/44) để biết nhiễu, rồi C2 |
| n368 hơn n50 ≥ 9 câu "đúng số" (hoặc kiểm cặp p < 0,05) | Còn dốc lên | Thêm mẫu nhiều hành vi (3–5 hành vi) vào dữ liệu |
| n368 và n50 chênh ≤ 3 câu | Bão hòa; thêm mẫu cùng kiểu không giúp | Không thêm mẫu; đầu tư truy hồi |
| LoRA cũ ≈ n368 trên dn15–dn34 (chênh ≤ 3 câu) | 31 mẫu trùng không phải nguồn lợi chính trên câu mới | Ghi nhận; mốc 8/14 cũ chỉ là hiệu ứng trên các câu trùng |
| LoRA cũ vượt n368 ≥ 7 câu trên dn15–dn34 | Việc loại 31 mẫu hoặc đổi cách chọn đã làm mất thứ gì đó | Báo ngay cho chat gốc; không tự chạy thêm |

Dự đoán (chỉ là đoán, chưa đo): n368 nằm giữa n50 và LoRA cũ ở "đúng số hành vi" (khoảng 24–31/34); "tìm đủ" của mọi cấu hình khoảng 35–55%, vì truy hồi theo hành vi chỉ đạt ~74%.

Bảng điền (đủ 34 câu; phần dn15–dn34 là so sánh sạch bốn chiều):

| Mô hình | Tìm đủ /34 | Đúng số hành vi /34 | Điều hiển thị TB | Tìm đủ dn01–14 /14 | Tìm đủ dn15–34 /20 | Đúng số dn15–34 /20 | Bao phủ % | Chính xác % |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b (chạy lại) | | | | | | | | |
| LoRA cũ | | | | | | | | |
| sach-n50 | | | | | | | | |
| sach-n368 | | | | | | | | |
| Tách lý tưởng (mốc trần) | | 34/34 | | | | 20/20 | | |

---

## 6. Mang về chat gốc

Từng lần học: thư mục adapter (`adapter_model.safetensors`, `adapter_config.json`, `thong_tin.json` gồm val loss theo bước, số bước, số giây, mã commit mô hình gốc, số mẫu bị cắt, phiên bản thư viện), `merge_info.json`, SHA256 của GGUF.

Từng mô hình đo: `kq_nhieu_dev_<m>_{tat_ca,dn01-14,dn15-34}.md`, `tach_dev_<m>_thuan_0vd.json`, `tach_dev_<m>_thuan_0vd.log.jsonl`, `kq_nhieu_dev_tran_tat_ca.md`, đoạn `ollama --version`, ghi chú mọi lỗi và cách sửa. Chưa xóa GGUF cũ trước khi bản mới qua G3.

---

## 7. Cấm kỵ và rủi ro

Cấm:
- `lexo_cau_hoi_moi.zip` (cũng như `lexo_eval_colab.zip`) chứa chữ của mọi câu đo, kể cả tập kiểm tra đóng băng: **không bao giờ** đưa vào notebook học. Notebook học chỉ nhận `lexo_hoc_sach.zip`.
- Không chọn adapter/epoch/siêu tham số theo điểm dev; chọn theo val loss. Ghi lại **mọi** lần chạy, kể cả lần xấu.
- Không chạy `kiem_tra`, `xac_nhan`, `phu` ở đây. Không sinh mẫu học từ câu của bộ đo. Không đổi siêu tham số ngoài mục 2.
- Không xóa hay ghi đè bản 14 câu cũ (`eval/_14cau/`, `ket_qua/`).

Rủi ro đã biết:
- Dev đã bị "nhìn" nhiều lần (mỗi lần đo lại là thêm một lần), nên số trên dev nghiêng lạc quan; 20 câu mới giảm nhưng không xóa điều này. Kết luận cuối chỉ dựa vào `kiem_tra` đóng băng, chạy một lần khi mô hình và tham số đã chốt.
- Câu mới và dữ liệu học cùng do Claude soạn, nhãn còn `nhap`, chưa có luật sư xem; mới chỉ có 0 câu do người dùng tự viết (cần ≥ 10 câu `nguon = nguoi_dung`).
- Tập học rộng mà nông (729 hành vi trên 297 Điều); lệch độ dài nhẹ (câu đo dài hơn câu học ~20%).
- Phiên bản Ollama/llama.cpp đổi có thể đổi chút kết quả: chạy lại `qwen3:8b` cùng lượt.

Việc ở chat gốc (không thuộc LoRA, làm song song): bạn duyệt 60 câu `nhap` (40 cũ + 20 mới); thêm kiểm tra "tập học ↔ bộ đo trùng tổ hợp Điều" vào `scripts/kiem_tra_train.py`; cải thiện truy hồi theo hành vi (reranker, m lớn hơn, cách viết truy vấn), chỉ chỉnh trên dev; sau cùng chạy `kiem_tra` đóng băng đúng một lần.

---

## 8. Tin nhắn đầu tiên gợi ý cho chat Kaggle/Colab

> Mình đang làm đồ án Lexo (tra cứu luật hình sự VN, chạy local). Đính kèm: `KE_HOACH_LORA_PHAN_CON_LAI.md`, `KE_HOACH_HOC_50.md`, `lexo_ban_giao_colab_kaggle.md`, `lexo_hoc_sach.zip` (dữ liệu học sạch, có SHA256SUMS), `lexo_eval_colab.zip`, `lexo_cau_hoi_moi.zip` (phủ bộ đo mở rộng 34 câu dev) và `lexo_chay_thu_colab.ipynb`. Việc: (1) làm **Giai đoạn B** (học LoRA Qwen3-8B trên `sft_train_sach.jsonl`, val `sft_val_sach.jsonl`, hạt 42) và qua G1–G3; (2) đo bốn mô hình trên dev 34 câu theo mục 4 và điền bảng mục 5; (3) báo mình các file cần mang về (mục 6). Mình chỉ dùng laptop, GPU là Kaggle/Colab T4. Khi gặp lỗi, đưa nguyên văn lỗi, nguyên nhân gốc và cách sửa tối thiểu; không đổi siêu tham số ngoài kế hoạch; không đưa `lexo_cau_hoi_moi.zip` hay `lexo_eval_colab.zip` vào notebook học.
