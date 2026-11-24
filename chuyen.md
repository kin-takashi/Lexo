# chuyen.md — Bàn giao dự án Lexo (cập nhật 2026-11-01, 22:30)

## 1. Dự án và quy tắc
- Lexo: công cụ tra cứu Bộ luật Hình sự (BLHS) offline, thư mục `E:\Lexo`. SQLite + FTS5, bge-m3 qua Ollama, Qwen3-8B QLoRA.
- Người dùng: Kintakashi, sinh viên năm cuối STU. Mục tiêu: một bài báo khoa học và hồ sơ thạc sĩ HCMUS tháng 5/2027.
- Mọi câu trả lời bằng tiếng Việt. Múi giờ Asia/Saigon. Email chỉ để nhận diện.
- Hai máy: desktop có GPU (đang liên kết, `E:\Lexo`), laptop không GPU (nơi bạn tạo hai zip Kaggle).
- Slash đã xử lý: `/ponytail` (dev lười, mức full; dòng kết nêu đã bỏ qua gì và rủi ro), `/graphify` (đồ thị code ở `graphify-out/`), `/explain-usage`.

## 2. Đã hoàn thành
- Tải HF `tmquan/cbba-toaan-gov-vn`, lọc BLHS, chia 70/30; gán nhãn 165.364 văn bản (train 115.651, test 49.713); che đáp án (che "nội dung sự việc"; mức án VKS và quyết định toà là đáp án).
- Bộ công cụ Kaggle V3 (`src/ban_an/cbba_kaggle.py`, `scripts/dong_goi_cbba_kaggle.py`, `scripts/phan_tich_cbba.py`, `kaggle/KE_HOACH_KAGGLE_V3.md`, ba notebook `lexo_hoc_cbba`, `lexo_gop_gguf_cbba`, `lexo_do_ban_an_cbba`).
- Số liệu thật (lần `--chi-chon`): pool train 103.965, test 49.658; học 3.526; dev 300 (dev_do 100); test 3.000; 189 Điều trong tập học (trung vị 15 văn bản/Điều, 84 Điều có <10); G0 0 lỗi; loại 7 văn bản học trùng 7/99 vụ test án lệ.
- Bạn đã tự tạo hai zip trên laptop: `lexo_hoc_chon_dieu_cbba.zip`, `lexo_do_ban_an_cbba.zip`.
- **Mới 1/11 — Chức năng 2 (giao diện phân tích vụ án):** xem mục 5.
- **Mới 1/11 — `scripts/xem_recall_zip.py`:** in bảng Recall@K và K đã chọn từ zip đo, cảnh báo nếu gói sinh bằng `--gia`, thoát mã 2 nếu Recall@30 dưới sàn 80%.

## 3. Giao thức V3 (khoá)
- Truy hồi: bge-m3 + FTS5, đoạn ~300 từ, RRF. K = K nhỏ nhất có "đủ đáp án trong top K" ≥ 90% trên học + dev, K ≤ 30. Sàn Recall@30 ≥ 80%, thấp hơn thì exit code 2 (sửa truy hồi trước, hoãn học).
- Qwen3-8B QLoRA xuất `{"dieu":[...]}`. Cổng G0–G4 chỉ kiểm tra kỹ thuật. Hai gói tách riêng (học / đo), không gắn gói đo vào notebook học.
- Test chạy đúng một lần với `cau_hinh_chot.json`; cấu hình `["A","C0","L"]` (A truy hồi thuần, C0 Qwen3-8B gốc, L LoRA). Không chọn checkpoint/K/prompt/EPOCH theo điểm dev/test.
- Tham số khoá: EPOCH 1 (~441 bước), micro-batch 1 × grad-acc 8, LR 2e-4 cosine, r16/α32, MAX_LEN 4096, seed 42, GIO_TOI_DA 9.0.
- R1 (chỉ trước khi có bất kỳ kết quả dev/test): `MAX_LEN=3072` và đóng gói lại `--tran 30`.
- R2: sau G4 đo giây/vụ của C0 và L trên 100 vụ dev; `N_max = 100×⌊32400/(g_C0+g_L)/100⌋`; `N_test = min(3000, N_max)`; nếu 1000 ≤ N_test < 3000 đóng gói lại chỉ gói đo với `--so-test N_test`; nếu < 1000 thì dừng và hỏi.
- Phân tích đăng ký trước (`phan_tich_cbba.py`): chỉ số chính L so với C0 trên "tìm đủ" (McNemar chính xác hai phía α=0,05 + bootstrap cặp seed 2026, 2000 lần); mô tả L so với A3/A5; phân theo cấp toà, số Điều, tần suất Điều hiếm, Điều chưa gặp, độ dài sự việc (≤500/501–1000/>1000 từ), năm.
- Chọn mẫu xác định, không dựa điểm số; gần trùng = 5-gram containment ≥ 0,5; `loc_giao_anle` loại văn bản học/dev gần trùng 99 vụ test án lệ.

## 4. Đặc thù môi trường
- SQLite trên mount lỗi disk I/O: chép chỉ mục sang `/tmp`. Không `rm` được trên mount (cần `device_request_delete_permission`; thay bằng làm rỗng file hoặc đưa vào `_to_delete/`).
- `device_bash` foreground tối đa 180 giây; job nền chết; `/tmp` của VM mất giữa các phiên. Không chép `scripts/env` (venv ~1.880 file).
- VM có Python 3.10, pytest, streamlit 1.64.0, numpy, yaml; không có Playwright. Chụp màn hình giao diện: chép mã + `db/luat.sqlite` + `db/chi_muc.sqlite` sang cloud qua `device_stage_files`, chạy Streamlit và Playwright ở cloud (đã làm 1/11).
- Chép file lên máy: stage vào thư mục MỚI dưới `/mnt/user-data/outputs/<dir>/`, rồi `device_commit_files`, kiểm sha256.
- Còn một file rỗng `E:\Lexo\_to_delete\shot\lexo_shot.tgz` (đã làm rỗng, xoá tay được).

## 5. Chức năng 2 — phân tích vụ án (làm 1/11)
Yêu cầu: nhập nội dung vụ án → kết quả giống lời cáo buộc của VKS: tội nào, ai phạm tội gì, vì sao.
- `src/agent/vu_an.py` (lớp xử lý): tìm Điều ứng viên (cả sự việc và từng hành vi, RRF, chỉ giữ Điều 108–425) → chọn Điều (mô hình LoRA nếu có trong Ollama, không thì thứ hạng tìm kiếm) → Qwen3 soạn JSON theo từng người từ nguyên văn Điều → kiểm: Điều ngoài danh sách bị bỏ, khoản không có bị bỏ, trích dẫn phải có nguyên văn trong sự việc (không thì ⚠️), tên người phải có trong sự việc. Thiếu mô hình soạn thì chỉ gợi ý Điều và nói rõ. Bản văn cáo trạng dựng bằng code, dùng từ "có dấu hiệu", không kết luận.
- `src/ui/app_vu_an.py` + `chay_phan_tich_vu_an.bat`: ô nhập, hai ví dụ, tiến độ từng bước, 4 tab (Bản cáo buộc tham khảo / Theo từng người / Điều luật liên quan / Chi tiết kỹ thuật), tải .txt và .json, thanh bên (ngày xảy ra hành vi, số Điều, đèn trạng thái).
- Test: `tests/test_vu_an.py` (18), `tests/test_ui_vu_an.py` (6). Toàn bộ test của dự án qua (đã chạy theo ba nhóm).
- Cấu hình: `config.yaml` mục `vu_an` (`chon_model` mặc định `qwen3-8b-lexo-chon-dieu-cbba-v1`, `soan_model` mặc định `llm_local.extract_model` = `qwen3:8b`).
- **Chưa kiểm chứng:** chất lượng thật khi chạy với Ollama + qwen3:8b trên máy bạn (mới thử bằng mô hình giả và kho BLHS thật); chưa có mô hình chọn Điều đã học; truy hồi chưa đo Recall@K thật.

## 6. Chưa có số đo thật
- Chưa thấy bảng Recall@K (nằm trong `cau_hinh.json` của zip đo trên laptop): chạy `python scripts/xem_recall_zip.py lexo_do_ban_an_cbba.zip` và gửi kết quả. Dưới sàn 80% thì phải sửa truy hồi trước.
- Chưa có số giờ thật của học (ước 2–5 giờ) và test (ước 5–10 giờ), chưa đo thông lượng Ollama cho R2.
- Rủi ro đã biết: EPOCH 1 có thể chưa đủ; nhãn do máy gán, chưa có người rà; test không lọc độ dài trong khi train ≤7.700 ký tự; còn sót thông tin cá nhân trong phán quyết đã che; gần trùng chỉ kiểm với học+dev, chưa với cả 115k train; hạn mức GPU Kaggle ~30 giờ/tuần cần tự kiểm lại.

## 7. Việc bạn làm tiếp cho V3
File giao việc cho chat Kaggle (học + test, từng chặng, điểm dừng, mẫu báo cáo, tin nhắn mở đầu): `kaggle/GIAO_VIEC_KAGGLE_TRAIN_TEST.md`.
1. Chạy `xem_recall_zip.py` trên zip đo, gửi bảng và dòng "Chọn: …".
2. Tải hai Dataset private `lexo-hoc-cbba`, `lexo-do-cbba` lên Kaggle.
3. Notebook theo thứ tự: học (thử rồi thật) → gộp GGUF → đo dev (G3/G4) → R2 → test một lần → `phan_tich_cbba.py`. Nên mở chat mới cho phần Kaggle, dùng tin nhắn đầu ở mục 10 của `KE_HOACH_KAGGLE_V3.md`.
4. Học xong thì `ollama create` mô hình chọn Điều và ghi tên vào `config.yaml` (`vu_an.chon_model`).

## 8. Việc tồn cũ (cần bạn đồng ý hoặc tự làm)
- Nhập văn bản HF đã gán nhãn vào `du_lieu.sqlite`; ghi "Hướng bài báo v2" vào Claude Doc `58d336ef-2c37-4620-bdd8-43e17eb0d286` (mục 10); chạy `build_index.py --tat-ca` (thiếu chỉ mục BLHS 1999, giao diện đang cảnh báo); hỏi thầy về PII/API và việc dùng lại phán quyết; nhờ sinh viên luật rà nhãn mù; quyết định dùng 99 vụ test án lệ làm test độc lập thứ hai không; quyết định trần 50 hay nhiều hơn.
- Chưa commit git (chỉ đề nghị): các file mới `src/agent/vu_an.py`, `src/ui/app_vu_an.py`, `chay_phan_tich_vu_an.bat`, `scripts/xem_recall_zip.py`, `tests/test_vu_an.py`, `tests/test_ui_vu_an.py`, `chuyen.md`, phần mới của README; cân nhắc thêm `graphify-out/` vào `.gitignore`.

## 9. Định hướng
Chạy Kaggle theo V3 và so L với C0 trên "tìm đủ" (báo cả kết quả xấu) → bài báo kèm test độc lập 99 vụ án lệ và lượt rà nhãn của sinh viên luật → ghép mô hình chọn Điều vào Chức năng 2 của Lexo (đã có giao diện), chạy local trên máy 16 GB, sau đó mở rộng sang các luật khác.
