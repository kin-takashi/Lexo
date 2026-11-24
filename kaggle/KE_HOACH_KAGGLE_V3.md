# Lexo — Kế hoạch Kaggle v3: học và đo «chọn Điều từ ứng viên» trên mẫu con bản án cbba

Dán file này vào chat Kaggle. V3 giữ nguyên giao thức Vòng 2 của V2 (`KE_HOACH_KAGGLE_V2.md`: truy hồi ứng viên → Qwen3-8B QLoRA chọn Điều →
cổng G0–G4 chỉ xét kỹ thuật → test chạy một lần với cấu hình đã khóa); chỉ **thay dữ liệu**: từ 90 vụ train án lệ sang một mẫu con của
165.364 bản án BLHS đã gán nhãn (`tmquan/cbba-toaan-gov-vn`). File này nói **chạy cái gì, theo thứ tự nào, kiểm gì, mang gì về, và những
tham số đã khóa trước khi có số**.

---

## 0. Tham số đã khóa (quyết định trước khi có bất kỳ số nào của V3)

Số thật lấy từ lần chạy `--chi-chon` trên dữ liệu thật (29/10/2026, hạt 2026). Mọi thứ dưới đây **không đổi theo điểm**.

| Mục | Giá trị |
|---|---|
| Nguồn | 115.651 train + 49.713 test sau gán nhãn và che (`inbox/cbba_blhs/nhan/`); năm bản án 2018–2026; mọi cấp xét xử |
| Pool sau lọc | train 103.965 (bỏ 11.590 văn bản quá 7.700 ký tự), test 49.658 = 44.865 nhóm vụ |
| Tập học | **3.526** bản án (trần ≈ 50 văn bản mỗi Điều, chọn Điều hiếm trước; vụ nhiều Điều tính cho mọi Điều của nó nên vài Điều vượt 50, lớn nhất 110); 189 Điều, trung vị 15 văn bản/Điều, 84 Điều có dưới 10 văn bản |
| Dev | **300** bản án, nguyên nhóm vụ, phân bố tự nhiên (khác tập học vì tập học bị trần); 300 dùng làm val của notebook học, 100 đầu dùng cho G3/G4 |
| Test | **3.000** vụ, mỗi nhóm vụ đúng một văn bản, thứ tự theo băm cố định; không lọc độ dài. Cấp: 2.610 sơ thẩm, 389 phúc thẩm, 1 giám đốc thẩm; 215 vụ nhiều Điều; 2 vụ có Điều chưa gặp ở học + dev |
| Loại gần-trùng | độ chứa 5-gram ≥ 0,5: dev so với học (0 bị bỏ), test so với học + dev (4 ứng viên bị bỏ). Văn bản trùng chữ train/test bị loại khỏi pool |
| Loại trùng test án lệ | 7 văn bản học trùng y hệt (độ chứa 1,0) với 7 trong 99 vụ test của bộ bản án án lệ, đã loại; 99 vụ đó **giữ nguyên làm test độc lập thứ hai, chưa dùng** |
| G0 (rò rỉ) | 0 lỗi: id, nhóm vụ, băm, độ chứa 5-gram giữa 3.826 mẫu học + dev và 3.000 vụ test |
| Mô hình / học | Qwen3-8B QLoRA, r 16, alpha 32, dropout 0,05, LR 2e-4 cosine, warmup 0,05, micro-batch 1 × grad-acc 8, `MAX_LEN` 4096, hạt 42 (như n368/V2) |
| **EPOCH** | **1** (≈ 441 bước cập nhật). V2 đặt 3 epoch cho 69 vụ; với 3.526 mẫu và trần 9 giờ, 1 epoch là lựa chọn có trước, không dò theo điểm. Chỉ có một checkpoint (cuối epoch); val loss vẫn đo ở bước 0, giữa và cuối |
| Ứng viên | bge-m3 + FTS5, từng đoạn ~300 từ, RRF; chế độ + K chọn bằng script trên **học + dev** (K nhỏ nhất có «đủ đáp án trong top K» ≥ 90%, K ≤ 30); sàn: đủ đáp án trong top 30 ≥ 80% |
| Test chạy | `["A", "C0", "L"]` một lần: A = truy hồi thuần; C0 = Qwen3-8B gốc chọn Điều từ cùng ứng viên; L = LoRA cbba. Không có B0 / B1 (tách hành vi) vì quá chậm ở cỡ test này |

## 1. Trên laptop (một lần)

1. Mở Ollama, đã `ollama pull bge-m3`. Chỉ mục: `db\chi_muc.sqlite` (đúng bản đã dùng để gán nhãn).
2. Xem lại mẫu chọn (vài phút, không cần Ollama):
   `python scripts\dong_goi_cbba_kaggle.py --chi-chon` → `inbox\kaggle_cbba\chon_mau.json`, `bao_cao_chon.md`.
3. Đóng gói đầy đủ (sinh ứng viên bằng bge-m3: **ước 1,5–4 giờ, chưa đo**; tự lưu tiếp, chạy lại thì đọc cache `_tam\xep_hang.jsonl`):
   `python scripts\dong_goi_cbba_kaggle.py`
   → `inbox\kaggle_cbba\lexo_hoc_chon_dieu_cbba.zip`, `lexo_do_ban_an_cbba.zip`, ba notebook `*_cbba.ipynb`, file này. In bảng Recall@K trên học + dev (không in gì về test).
   - Thoát **0**: có đủ hai gói.
   - Thoát **2**: ứng viên dưới sàn (đủ đáp án trong top 30 < 80%). Gói đo vẫn được ghi, gói học thì không. Sửa truy hồi trước, hoãn học.
   - Thoát **1**: G0 phát hiện rò rỉ hoặc dữ liệu lỗi. Dừng, báo về chat gốc.
4. Notebook V3 sinh từ notebook V2 bằng `python scripts\tao_notebook_cbba.py` (đã chạy sẵn; chạy lại nếu sửa notebook V2; lỗi thì không ghi file nào).
5. Thử khô không cần Ollama: thêm `--gia` (vector băm giả, zip có hậu tố `_GIA`, **không** đem lên Kaggle).

## 2. Tạo Dataset private trên Kaggle

| Dataset (gợi ý tên) | Tải lên | Gắn vào |
|---|---|---|
| `lexo-hoc-cbba` | `lexo_hoc_chon_dieu_cbba.zip` | notebook học (**chỉ** notebook học, **chỉ** gói này) |
| `lexo-do-cbba` | `lexo_do_ban_an_cbba.zip` | notebook đo |

Không cần GGUF n368 (V3 không chạy B1). Kaggle tự giải nén zip; notebook tìm gói theo file đánh dấu (`LEXO_HOC_CHON_DIEU.md`, `LEXO_DO_BAN_AN.md`)
và chạy `sha256sum -c SHA256SUMS` trước mọi việc. Để **private**: dữ liệu là bản án đã che nhưng chưa quét hết thông tin cá nhân còn sót.

## 3. Thứ tự chạy

| # | Notebook | Cài đặt | Bật | Cổng | Mang về |
|---|---|---|---|---|---|
| 1 | `lexo_hoc_cbba` | GPU T4, Internet | `CHE_DO = "thu"` (tương tác) rồi `"that"` (Save & Run All) | G0, G1 | `lexo-qwen3-8b-chon-dieu-cbba-v1.zip` |
| 2 | `lexo_gop_gguf_cbba` | CPU, Internet; input = Output của #1 | | G2 | `merge_info.json` |
| 3 | `lexo_do_ban_an_cbba` | GPU T4, Internet; thêm input = Output của #2 | `CHAY_LORA_DEV = True` (A, C0, L trên 100 vụ dev) | G3, G4 | `ket_qua_dev_qwen3-8b-lexo-chon-dieu-cbba-v1.zip` |
| 4 | — (chat gốc) | | Áp dụng R2; nếu cắt cỡ test thì đóng gói lại gói đo (mục 4) | | `cau_hinh_chot` điền sẵn |
| 5 | `lexo_do_ban_an_cbba` | như #3 | `CHAY_TEST = True`, `DA_CHOT = True`, tắt phần khác | — | `ket_qua_test.zip` |
| 6 | laptop | | `python scripts\phan_tich_cbba.py ...` (mục 6) | | `phan_tich.md` |

Lượt dài (học, test) chạy bằng **Save Version → Save & Run All**. Kaggle thường giới hạn GPU khoảng 30 giờ mỗi tuần và 12 giờ mỗi phiên
(xem lại trên tài khoản của bạn): học + dev + test có thể phải trải qua hơn một tuần; không dồn bằng cách đổi tham số.

Ước lượng giờ (**chưa đo, chỉ để lập kế hoạch**): học 2–5 giờ; dev 100 vụ × 2 mô hình khoảng 0,5–1 giờ; test 3.000 vụ × 2 mô hình khoảng 5–10 giờ,
sát giới hạn, nên có R2.

## 4. Quy tắc đã khóa

**R1 — thời gian học.** Sau 10 bước notebook học tự ước tổng giờ; quá `GIO_TOI_DA = 9` thì dừng và ghi `<TEN>_DUNG.json`. Khi đó, theo thứ tự, và chỉ vì lý do
thời gian/VRAM (không vì điểm): (a) `MAX_LEN = 3072` (số mẫu bị cắt ghi trong `thong_tin.json`); (b) nếu vẫn quá, đóng gói lại với `--tran 30` rồi học lại từ đầu.
Cả hai chỉ được làm **trước khi** có bất kỳ kết quả dev/test nào. Không đổi EPOCH, LR, r, lời nhắc, K.

**R2 — cỡ test.** Sau G4, lấy `giây/vụ` trung bình của C0 và L trên 100 vụ dev (bảng tổng của notebook đo): `g_C0`, `g_L`.
`N_max = 100 × ⌊32.400 / (g_C0 + g_L) / 100⌋` (32.400 giây = 9 giờ, chừa 3 giờ cho cài Ollama, kéo mô hình, đóng gói).
`N_test = min(3.000, N_max)`.
- `N_test = 3.000`: dùng gói đo hiện có.
- `1.000 ≤ N_test < 3.000`: đóng gói lại **chỉ gói đo** bằng `python scripts\dong_goi_cbba_kaggle.py --so-test N_test` (cùng danh sách, lấy `N_test` vụ đầu theo thứ tự băm
  cố định; ứng viên đã có cache), tải lên làm phiên bản mới của `lexo-do-cbba`. Gói học không đổi, không tải lại.
- `N_test < 1.000`: dừng, hỏi người phụ trách; không tự chọn cỡ nhỏ hơn, không chạy một phần.
Không dùng điểm dev để quyết định R2.

**Chọn checkpoint:** chỉ có điểm cuối epoch. **Chọn K / chế độ ứng viên:** do script trên học + dev, không dùng test.

## 5. Cổng (chỉ xét kỹ thuật, không xét điểm dev)

Như V2 (mục 3 của `KE_HOACH_KAGGLE_V2.md`), có hai khác biệt: không có Vòng 1 nên `CHAY_VONG_1` luôn `False`; G1 đối chiếu val loss cuối so với bước 0 (không có «điểm sớm hơn» để chọn).

| Cổng | Đạt khi |
|---|---|
| G0 | SHA256SUMS OK; 0 dòng trùng mã / băm / 5-gram với test; train ∩ val = ∅; lời nhắc khớp từng ký tự; 0 câu trả lời bị cắt (mẫu quá `MAX_LEN` chỉ bị cắt bớt sự việc, có ghi số) |
| G1 | val loss cuối < bước 0, không NaN; 20 mẫu val: JSON hợp lệ 20/20, mọi Điều trong ứng viên, 0 khối think |
| G2 | kiến trúc `qwen3`, 399 tensor, có chat template; kích thước, SHA256, commit llama.cpp trong `merge_info.json` |
| G3 | 3 vụ dev: `ollama ps` 100% GPU, `num_ctx` 8192, 0 lỗi, 0 think, 0 «có thể bị cắt», không có «truncating», `prompt_eval_count` khớp số token tự đếm (lệch ≤ 8) |
| G4 | 100 vụ dev: 0 lỗi, 0 think, 0 bị cắt. Tìm đủ / khớp đúng trên dev **chỉ để xem** |

## 6. Phân tích đã đăng ký trước

- **So sánh chính (duy nhất có kiểm định):** **L so với C0 trên «tìm đủ»** (mọi Điều đáp án đều được hiển thị), cùng các vụ, McNemar chính xác hai phía, α = 0,05, kèm khoảng tin cậy
  bootstrap cặp của hiệu (hạt 2026, 2.000 lần lấy mẫu). Vụ lỗi tính là không tìm đủ.
- **Mô tả, không kiểm định:** L so với A3 / A5 (hiển thị thẳng 3 / 5 Điều đầu của truy hồi; đối chiếu cùng «Điều hiển thị TB»); khớp đúng, bao phủ, chính xác; tìm đủ theo cấp xét xử, số Điều đáp án,
  tần suất Điều hiếm nhất trong tập học, Điều chưa gặp, độ dài sự việc gốc, năm; trung bình vĩ mô theo Điều (Điều có ≥ 5 vụ, mỗi Điều một phiếu);
  số vụ lỗi / quá giờ / giây mỗi vụ.
- Mọi khoảng tin cậy chỉ để mô tả độ bất định. Mọi kết quả, kể cả xấu (L không hơn C0), được báo cáo; không học lại để cải thiện điểm test.
- Minh họa độ chính xác (giả định, không phải kết quả): với 3.000 vụ và khoảng 15% vụ hai bên khác nhau, khoảng tin cậy 95% của hiệu rộng cỡ ±1,4 điểm phần trăm.

## 7. Cấm

- Không gắn gói đo (`lexo-do-cbba`) vào notebook học; không gắn hai gói học cùng lúc.
- Không chạy tập test trước khi chốt, không chạy lại test. `cau_hinh_chot.json` ghi một lần; script đo từ chối file chốt khác.
- Không chọn checkpoint, K, chế độ ứng viên, lời nhắc, EPOCH theo điểm dev hay test. Hai đường lui duy nhất là R1(a), R1(b), và chỉ vì thời gian.
- Không dùng 99 vụ test án lệ cho tới khi có quyết định riêng (nếu dùng: mô hình đã khóa, chạy một lần, báo cáo tách khỏi test cbba).
- Không công khai Dataset, adapter hay GGUF khi chưa có ý kiến về thông tin cá nhân còn sót trong bản án.
- Ghi lại mọi lần chạy, kể cả lần xấu.

## 8. Mang về laptop (`inbox\kaggle_ket_qua\`)

- Học: `lexo-qwen3-8b-chon-dieu-cbba-v1.zip` (adapter + `thong_tin.json`: val loss theo bước, số bước, số giây, commit mô hình gốc, số mẫu bị cắt, phiên bản thư viện, K, số lần chèn
  đáp án, hash file ứng viên). Nếu dừng sớm: `<TEN>_DUNG.json`.
- `merge_info.json`; `ket_qua_dev_...zip`.
- Test: `ket_qua_test.zip` (có `cau_hinh_chot.json`). Chép bảng tổng vào tài liệu trước, rồi mới xem từng vụ sai. Sau đó:
  `python scripts\phan_tich_cbba.py --goi inbox\kaggle_cbba\lexo_do_ban_an_cbba --ket-qua <thư mục chứa C0.jsonl, L.jsonl> --chot <cau_hinh_chot.json>`
  → `phan_tich.md` cạnh kết quả. Thêm `--tap dev` cho dev (chỉ để xem).
- Ghi chú mọi lỗi gặp: nguyên văn lỗi, nguyên nhân, cách sửa tối thiểu.

## 9. Hạn chế đã biết (ghi vào bài)

- Nhãn là các Điều BLHS trong quyết định/đáp án của bản án; có thể gồm Điều chung của vụ nhiều bị cáo; nhiễu nhãn chưa ước lượng.
- Tập học giới hạn ≤ 7.700 ký tự và có trần mỗi Điều; test không lọc độ dài và theo phân bố tự nhiên (đa số Điều phổ biến). Nên báo cả điểm vĩ mô theo Điều và theo độ dài.
- Gần-trùng chỉ kiểm giữa học + dev và test, và với 99 vụ test án lệ; chưa kiểm với toàn bộ 115.651 train. Không loại trừ được việc Qwen3 đã thấy văn bản công khai lúc tiền huấn luyện.
- Chỉ mục luật là BLHS 2015 (và sửa đổi); Điều có hiệu lực theo ngày bản án được tra theo `ngay_tra_cuu`; bản án trước 2018 bị loại.
- EPOCH 1 có thể học chưa đủ; đã khóa trước, không chỉnh. Một hạt (42), một lần chạy: chưa đo phương sai giữa các hạt.
- Chưa quét hết thông tin cá nhân còn sót sau che; Dataset để private.

## 10. Tin nhắn đầu tiên gợi ý cho chat Kaggle

> Mình làm đồ án Lexo (tra cứu Bộ luật Hình sự, chạy local). Đính kèm `KE_HOACH_KAGGLE_V3.md` và ba notebook (`lexo_hoc_cbba.ipynb`, `lexo_gop_gguf_cbba.ipynb`,
> `lexo_do_ban_an_cbba.ipynb`); hai gói dữ liệu đã lên Kaggle thành Dataset private (`lexo-hoc-cbba`, `lexo-do-cbba`).
> Việc lần này: bước #1 (notebook học, `CHE_DO = "thu"` trước, rồi `"that"`). Mình chỉ có laptop, GPU là Kaggle T4. Khi gặp lỗi, đưa nguyên văn lỗi, nguyên nhân gốc
> và cách sửa tối thiểu; không đổi siêu tham số ngoài quy tắc R1/R2 trong kế hoạch; không gắn gói đo vào notebook học; không chạy tập test.
