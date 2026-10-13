# Lexo

Tra cứu điều luật Việt Nam có lịch sử hiệu lực, chạy cục bộ. Thiết kế: xem `ke-hoach-chuc-nang-1-v2.md`.

## Cài đặt (Windows, Python 3.10.x)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env       # rồi điền API key vào .env (không commit)
python scripts/check_env.py  # kiểm tra sqlite3, FTS5, sqlite-vec, GPU, Ollama
python scripts/init_db.py      # tạo db/luat.sqlite theo schema
pytest
```

## Bước 1 — nạp văn bản gốc (ví dụ BLHS 2015)

```powershell
python scripts/parse_base_law.py "inbox/Bộ-luật-100-2015-QH13.docx" --ten-viet-tat BLHS   # parse + validator -> raw/100-2015-QH13/parsed.json
streamlit run src/review/app_base_law.py                                                  # người duyệt: xử lý cờ, đối chiếu 30 Điều mẫu, bấm Duyệt
python scripts/ingest_base_law.py 100-2015-QH13                                           # chỉ nạp nếu đã duyệt hợp lệ
python scripts/lookup.py "Điều 317 BLHS 2015"                                             # tra chính xác (thêm --ngay YYYY-MM-DD để xem theo ngày)
```

## Bước 2 — áp luật sửa đổi lên văn bản gốc (BLHS 2015 + Luật 12/2017/QH14, 86/2025/QH15, 59/2024/QH15)

CSDL đã đổi sang schema v2 nên **tạo lại một lần** (file cũ được sao lưu, không mất): `python scripts/init_db.py --reset`, rồi nạp lại văn bản gốc (Bước 1).

Nguyên tắc: văn bản gốc là "khung"; mỗi lệnh sửa đổi (sửa đổi / bổ sung / bãi bỏ / thay-bỏ-chèn cụm từ) tạo **phiên bản mới có khoảng hiệu lực `[từ, đến)`** và ghi rõ luật nào, Điều/khoản nào của luật đó đã tạo ra nó. Không có gì bị xoá đè, nên xem lại bản cũ theo ngày được. Phiên bản là dữ liệu dẫn xuất, dựng lại từ các lệnh **đã duyệt**.

```powershell
# 1. Parse 3 luật sửa đổi (cấu trúc + validator; chỉ ghi nhận phần sửa BLHS, phần sửa luật khác chỉ được liệt kê)
python scripts/parse_amending_law.py "inbox/Luật-12-2017-QH14.docx"
python scripts/parse_amending_law.py "inbox/86_2025_QH15_662377.docx"
python scripts/parse_amending_law.py "inbox/59_2024_QH15_606865.docx"

# 2. Trích lệnh (regex, không dùng LLM) và nạp vào CSDL ở trạng thái CHỜ DUYỆT. Mục nào không hiểu sẽ được in ra, không tự đoán.
python scripts/extract_commands.py 12-2017-QH14 86-2025-QH15 59-2024-QH15 --nap

# 3. Xem trước (chạy thử trên bản sao, không đổi CSDL thật), rồi đối chiếu từng lệnh với văn bản luật sửa đổi
python scripts/apply_commands.py tong-quan 100/2015/QH13
python scripts/apply_commands.py xem-truoc 100/2015/QH13 --luu db/xem_truoc.sqlite      # tra thử: lookup.py ... --db db/xem_truoc.sqlite
python scripts/apply_commands.py bao-cao 100/2015/QH13 12/2017/QH14                       # -> raw/12-2017-QH14/lenh_cho_duyet.md

# 4. Duyệt (do NGƯỜI quyết định, ghi tên + ngày vào CSDL) rồi áp dụng
python scripts/apply_commands.py duyet 100/2015/QH13 12/2017/QH14 --nguoi "Tên bạn" --ghi-chu "đã đối chiếu ..."
python scripts/apply_commands.py ap-dung 100/2015/QH13
```

Tra cứu (mặc định là **bản hiện hành**, kèm nguồn sửa đổi của từng khoản/điểm):

```powershell
python scripts/lookup.py "Điều 173 BLHS"                              # hiện hành; ghi rõ khoản/điểm nào do luật nào sửa, hiệu lực từ ngày nào
python scripts/lookup.py "Điều 173 BLHS" --ngay 2017-12-31            # xem bản cũ đang có hiệu lực tại ngày đó
python scripts/lookup.py "Điều 173 BLHS" --lich-su                    # mọi lần sửa đổi của Điều
python scripts/lookup.py "Điều 173 BLHS" --so-sanh 2017-12-31 2018-01-01
python scripts/lookup.py "Điều 173 BLHS" --chuyen-tiep                # kèm nguyên văn điều khoản hiệu lực/chuyển tiếp của các luật sửa đổi
```

Giới hạn đã biết (hệ thống không tự suy ra, chỉ hiển thị):
- Điều khoản chuyển tiếp / hồi tố có lợi chỉ được lưu và hiển thị nguyên văn; hệ thống không tự quyết "điều luật nào áp dụng cho hành vi nào".
- Ngày bắt đầu hiệu lực của BLHS 2015 đang lấy theo chính văn bản (01/07/2016). Thực tế đã được nghị quyết của Quốc hội hoãn; cần nạp nghị quyết đó (lệnh `hoan_hieu_luc`) để tra ở các ngày trước mốc thực tế cho đúng. Lookup có in cảnh báo khi chưa có.
- Lệnh "đánh số lại" chưa hỗ trợ (báo là chưa hiểu). Các heuristic sửa từ ngữ (khoảng trắng, chữ hoa đầu câu) chỉ kiểm chứng đầy đủ khi đối chiếu với văn bản hợp nhất (Bước 3).
- Mục bộ trích lệnh không hiểu chỉ nằm trong `raw/<slug>/commands.json` và `log_nap.ghi_chu`, chưa có giao diện duyệt riêng.

## Bước 3 — đối chiếu với văn bản hợp nhất chính thức, hiệu đính, xuất bộ luật hiện hành

Mục đích: kiểm tra **độc lập** bản hệ thống dựng (văn bản gốc + luật sửa đổi đã duyệt) với văn bản hợp nhất (VBHN) do Văn phòng Quốc hội xác thực, và ghi lại tỷ lệ khớp làm bằng chứng phương pháp. Không dùng LLM.

Nguồn đối chiếu (PDF có chữ trên Cổng Công báo, đặt trong `raw/<thư mục>/`; không cần OCR):

| Thư mục trong `raw/` | Văn bản | Vai trò |
|---|---|---|
| `135-VBHN-VPQH` | [VBHN 135/VBHN-VPQH](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-135-vbhn-vpqh-46165.htm) hợp nhất BLHS + Luật 12/2017 + 59/2024 + 86/2025 | đối chiếu **bản hiện hành** |
| `01-VBHN-VPQH` | [VBHN 01/VBHN-VPQH](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-01-vbhn-vpqh-24866.htm) hợp nhất BLHS + Luật 12/2017 | đối chiếu mốc 01/01/2018; bản đồng thuận |
| `11-VBHN-VPQH` | [VBHN 11/VBHN-VPQH](https://congbao.chinhphu.vn/van-ban/van-ban-hop-nhat-so-11-vbhn-vpqh-44425.htm) hợp nhất BLHS + Luật 12/2017 + 59/2024 | bản đồng thuận |
| `100-2015-QH13/congbao` | [Luật 100/2015/QH13 đăng Công báo](https://congbao.chinhphu.vn/van-ban/luat-so-100-2015-qh13-18442.htm) | nguyên văn như ban hành (bản đồng thuận) |

Khi một VBHN khác bản hệ thống, thường là một trong ba trường hợp: (a) VBHN sửa lỗi gõ của bản đăng Công báo; (b) file Word luật sửa đổi của chúng ta có lỗi chép; (c) cách trình bày khác (viết hoa "Hình sự", "oá/óa", "sỹ/sĩ"). Hệ thống **không tự sửa**: trường hợp (a), (b) được lập thành *đề xuất hiệu đính* kèm bằng chứng, chỉ áp sau khi NGƯỜI duyệt; trường hợp (c) được coi là tương đương (vẫn liệt kê, không tính là sai).

```powershell
pip install -r requirements.txt                                   # có pdfplumber
python scripts/doi_chieu_vbhn.py trich 135-VBHN-VPQH 01-VBHN-VPQH 11-VBHN-VPQH       # PDF -> raw/<thư mục>/vbhn.json (chậm, ~1 phút/bộ)
python scripts/doi_chieu_vbhn.py trich 100-2015-QH13/congbao --mau "*_cb_phan*.pdf" --ra cb.json

python scripts/doi_chieu_vbhn.py so-sanh --bao-cao raw/135-VBHN-VPQH/so_sanh.md      # số liệu khớp + từng chỗ khác (không đổi CSDL)
python scripts/doi_chieu_vbhn.py de-xuat                           # lập đề xuất hiệu đính (CHỜ DUYỆT) vào CSDL và raw/100-2015-QH13/hieu_dinh.json
                                                                   # (từ chối nếu còn lệnh sửa đổi chưa duyệt; thêm --xem-truoc để lập trên bản chạy thử)
python scripts/doi_chieu_vbhn.py danh-sach                         # đọc từng đề xuất: từ cũ -> từ mới, bản nào đồng thuận
python scripts/doi_chieu_vbhn.py duyet --nguoi "Tên bạn" --ap-dung  # duyệt (hoặc --id 3 5 / --loai loi_go / --tu-choi) rồi dựng lại phiên bản
python scripts/doi_chieu_vbhn.py so-sanh                           # khớp lại sau hiệu đính
```

Quy tắc hiệu đính: mỗi quy tắc thay đúng **một** chỗ xuất hiện của "từ cũ" trong nút (Điều/khoản/điểm) bằng "từ mới"; một đề xuất chỉ được lập khi có bằng chứng ngoài chính VBHN đang so (ít nhất một văn bản khác viết giống VBHN, hoặc người đối chiếu ghi đã kiểm nguồn trong `raw/100-2015-QH13/xac_minh_nguon.json`). Loại `sai_so_lieu` (có chữ số) và `nhieu_chu` nên đọc kỹ trước khi duyệt. Văn bản như luật ban hành vẫn được giữ nguyên trong CSDL (`lookup.py ... --nguyen-van`), và quyết định duyệt được lưu ở `raw/<slug>/hieu_dinh.json`: sau `init_db.py --reset` chạy `python scripts/doi_chieu_vbhn.py nap` rồi `python scripts/apply_commands.py ap-dung 100/2015/QH13`.

Xuất bộ luật hiện hành (Markdown và Word) kèm nguồn sửa đổi từng Điều, phụ lục hiệu đính và kết quả đối chiếu:

```powershell
python scripts/xuat_bo_luat.py                                     # BLHS 2015 tại hôm nay -> xuat/BLHS-100-2015-QH13_<ngày>.md và .docx
python scripts/xuat_bo_luat.py --ngay 2018-01-01 --dinh-dang md    # một mốc trong quá khứ
python scripts/xuat_bo_luat.py --xem-truoc                         # BẢN XEM TRƯỚC: gồm cả lệnh/hiệu đính CHƯA duyệt, ghi rõ ở đầu file và từng chỗ
```

Lưu ý: bản xuất là dữ liệu dẫn xuất để tra cứu, không phải văn bản chính thức. Lệnh sửa đổi và đề xuất hiệu đính chưa duyệt không nằm trong bản xuất (đầu file có ghi số lượng còn chờ). Nghị quyết hoãn hiệu lực BLHS 2015 chưa nạp (xem "Giới hạn đã biết" ở Bước 2); đó là việc của bước sau.

## Bước 4 — lập chỉ mục tìm kiếm (FTS5 + vector bge-m3, chạy offline)

Chỉ mục nằm ở file riêng `db/chi_muc.sqlite` (đọc CSDL chính ở chế độ chỉ-đọc, xoá đi build lại được, không ảnh hưởng dữ liệu luật).
Mỗi phiên bản của Điều/Khoản/Điểm là một "đoạn"; điểm/khoản được ghép kèm tên Điều (và câu dẫn của khoản) để vector hiểu ngữ cảnh.

```powershell
pip install -r requirements.txt          # có thêm numpy
ollama pull bge-m3                       # ~1,2 GB, chạy CPU được

python scripts/build_index.py --xem 9    # xem thống kê + 9 đoạn mẫu, KHÔNG ghi gì, KHÔNG gọi Ollama
python scripts/build_index.py --thu 100  # nhúng thử 100 đoạn để đo tốc độ thật rồi tự ước lượng tổng thời gian
python scripts/build_index.py            # chạy đầy đủ; Ctrl+C an toàn, chạy lại sẽ làm tiếp từ chỗ dừng

python scripts/tim_kiem.py "lén lấy xe máy của hàng xóm bị phạt sao"
python scripts/tim_kiem.py "trộm cắp tài sản" --ngay 2017-12-31     # tra theo luật có hiệu lực ngày đó
python scripts/tim_kiem.py "trộm cắp" --che-do fts                  # chỉ từ khoá (hybrid | vector | fts; mặc định vector)
```

- Vector được cache theo mã băm (nội dung + mô hình): sau khi duyệt hiệu đính / áp thêm luật sửa đổi chỉ cần chạy lại `build_index.py`, chỉ đoạn nào đổi chữ mới phải tính lại.
- `--gia` dùng vector giả (băm từ) để thử đường ống khi chưa có Ollama; kết quả loại này không phản ánh chất lượng thật.
- Lọc theo ngày được áp dụng TRƯỚC khi xếp hạng, nên không bao giờ trả về phiên bản đã hết hiệu lực / chưa có hiệu lực.
- Nếu CSDL luật đã đổi mà chỉ mục chưa build lại, `tim_kiem.py` sẽ cảnh báo (tắt bằng `--khong-kiem-tra-cu`).
- Đo chất lượng: `python scripts/danh_gia.py --chi-tiet` (bộ câu hỏi `eval/bo_cau_hoi.json`, mặc định tập dev, chọn tập bằng `--tap`; Hit@k / MRR theo từng chế độ); `--quet` thử trọng số từ khoá cho hybrid.
  Lần đo đầu (58 câu nháp, chưa duyệt): vector Hit@1 64% / Hit@3 84% / MRR 0,753; hybrid 57% / 84% / 0,706; chỉ từ khoá 52% / 67% / 0,619 → mặc định dùng vector.
  Điểm yếu còn lại: lệch từ vựng giữa lời đời thường và tên Điều (vd "không đóng tiền nuôi con" ↔ "nghĩa vụ cấp dưỡng").

### Bước 4b — câu hỏi đời thường sinh sẵn cho từng Điều (thu hẹp khoảng cách từ vựng)

Lời người dân ("không chịu đóng tiền nuôi con") khác thuật ngữ luật ("nghĩa vụ cấp dưỡng"). Cách xử lý: LLM local viết sẵn khoảng 5 câu hỏi đời thường cho mỗi Điều, bge-m3 nhúng các câu đó; khi tìm, điểm của Điều được nâng nếu câu hỏi người dùng gần một câu hỏi sinh sẵn.
Máy chỉ đọc chữ của luật; tập `kiem_tra` của `eval/bo_cau_hoi.json` KHÔNG được đưa vào bước này.

```powershell
ollama pull qwen3:8b                                          # model viết chữ (Qwen3-8B, theo kế hoạch); chế độ nghĩ được TẮT tự động (cần Ollama >= 0.9)
python scripts/sinh_cau_hoi.py --dieu 173 186 123 --llm qwen3:8b   # xem thử chất lượng và tốc độ, KHÔNG ghi
python scripts/sinh_cau_hoi.py --llm qwen3:8b --theo-bo eval/bo_cau_hoi.json   # sinh và lưu đúng ~70 Điều đáp án của bộ dev (chỉ đọc SỐ Điều); đo tốc độ thật
python scripts/sinh_cau_hoi.py --llm qwen3:8b --mau 30      # hoặc 30 Điều trải đều (đừng dùng --thu N: N Điều đầu toàn là Phần chung)
python scripts/sinh_cau_hoi.py --llm qwen3:8b               # sinh nốt (Ctrl+C an toàn, chạy lại làm tiếp), rồi nhúng bằng bge-m3
python scripts/chan_doan_cau_hoi.py                           # CỬA KIỂM: câu sinh có đáng dùng không? (offline; chỉ cần Ollama để nhúng ~70 câu dev)
python scripts/danh_gia.py --quet-cau-hoi --tap dev   # CHỈ khi cửa kiểm ĐẠT: quét hệ số trên bộ dev
python scripts/tim_kiem.py "…" --dung-cau-hoi 0.9             # dùng khi đã chọn được hệ số ổn định
```

Mặc định chỉ sinh cho Điều về tội phạm (tiêu đề "Tội …", 315/409 Điều); Điều Phần chung (nguyên tắc, tuổi, hiệu lực…) bị bỏ vì LLM chỉ bịa tình huống phạm tội chung chung cho chúng (đo được: khứ hồi hạng 1 chỉ 15% trên Điều 1–41, câu "Tôi đánh nhau…" lặp ở nhiều Điều); thêm `--ca-dieu` nếu vẫn muốn. Điều đổi chữ (sau duyệt hiệu đính / áp luật mới) sẽ được sinh lại; Điều không đổi giữ nguyên. Câu hỏi sinh ra bị lọc: bỏ câu chứa từ cấm (Điều, khoản, tội…), câu chép nguyên tên Điều, câu trùng.
Sau khi sinh, các câu còn qua thêm hai vòng lọc: vòng khứ hồi (giữ câu chỉ khi tìm bằng chính câu đó thì Điều nguồn đứng top 3) và lọc trùng giữa các Điều (bỏ câu trùng/gần trùng câu của Điều khác, vì câu chép ví dụ hoặc câu chung chung không phân biệt được Điều nào).

**Cửa kiểm bắt buộc trước khi dùng** (`scripts/chan_doan_cau_hoi.py`). Lần thử đầu (1708 câu do qwen2.5:3b viết, lời nhắc có ví dụ) làm kết quả TỆ HƠN không dùng và càng tăng hệ số càng tệ (Hit@1 64% → 53% → 26%, MRR 0,753 → 0,399). Đo lại offline trên 128 câu (58 kiểm tra + 70 câu dev) cho thấy lỗi nằm ở dữ liệu, không ở công thức:
- chỉ 38% câu sinh tìm ra Điều nguồn ở hạng 1, 53% ở top 3; 8,7% trùng/gần trùng câu của Điều khác (model chép nguyên ví dụ trong lời nhắc như "xe máy hàng xóm mất tích" vào hàng chục Điều không liên quan, có cả chữ Hán);
- xếp hạng CHỈ bằng câu sinh: Hit@1 21% (kiểm tra) / 30% (dev), trong khi chữ luật là 64% / 73%;
- khi chữ luật và câu sinh chọn khác Điều hạng 1 thì câu sinh chỉ cứu được 5 và phá 30 trên bộ kiểm tra (4 và 34 trên bộ dev); điểm câu sinh càng cao càng không đáng tin;
- không cách kết hợp nào cứu được dữ liệu đó (max-sàn, z-score, RRF, xếp lại trong top-N, hiệu chỉnh hub): đã thử, không cách nào hơn không dùng vượt mức nhiễu (cao nhất là +1 câu ở hệ số 0,7), phần lớn kém hơn.
Cửa kiểm có bốn kết quả: ĐẠT, ĐẠT SƠ BỘ (qua ngưỡng nhưng câu sinh mới phủ một phần Điều về tội phạm), CHƯA ĐẠT, hoặc CHƯA ĐỦ DỮ LIỆU (ít hơn 20 câu dev có đáp án thuộc Điều đã sinh; khi đó chưa kết luận gì). Vì vậy mặc định KHÔNG dùng câu sinh (`he_so_cau_hoi = 0`); tìm kiếm tự bỏ qua câu sinh bằng lời nhắc cũ và báo; chỉ quét hệ số khi cửa kiểm ĐẠT: ≥ 70% câu sinh đưa Điều nguồn vào top 3 khi tìm bằng chính câu đó, ≤ 3% trùng giữa các Điều, không chữ nước ngoài, cứu/phá ≥ 0,5 trên bộ dev, và câu sinh phủ ≥ 90% Điều về tội phạm.

Hai điều chỉnh sau lần chạy qwen3:8b trên 70 Điều đáp án của bộ dev (câu sinh tốt hơn hẳn: 76% top 3, 0 trùng, 0 chữ nước ngoài), ghi lại để người đọc biết ngưỡng đã được sửa SAU khi thấy số: (1) ngưỡng ban đầu "≥ 60% đúng hạng 1" là heuristic của mình, không có cơ sở khác; đổi sang "≥ 70% trong top 3" vì đó đúng là tiêu chí vòng lọc `giu` và vì hạng 1 của câu sinh (54%) vẫn cho xếp hạng ngang chữ luật (xem (2)). Đây là cửa kiểm sơ bộ để khỏi lãng phí thời gian sinh, KHÔNG phải bằng chứng; bằng chứng là bảng quét hệ số khi đã phủ gần hết luật. (2) So phiếu trước đó cho chữ luật chọn giữa mọi Điều (315+) còn câu sinh chỉ chọn giữa 65 Điều đã sinh, nên câu sinh được ưu ái ("đúng 89% so với 75%, cứu 13/phá 4"). Giờ so phiếu làm trong THẾ GIỚI ĐÓNG (cả hai bên chỉ chọn trong Điều đã có câu sinh): chữ luật 87,7% / câu sinh 89,2% Hit@1, MRR 0,919 / 0,920, cứu 5 / phá 4. Nghĩa là câu sinh NGANG chữ luật chứ chưa hơn; hai bên bổ sung cho nhau (5 câu chỉ câu sinh đúng, 4 câu chỉ chữ luật đúng), và còn phải kiểm khi có đủ Điều gây nhiễu.
**Bộ câu hỏi đánh giá: MỘT file nguồn `eval/bo_cau_hoi.json`** (gom từ ba file cũ, đã chuyển vào `eval/_cu/`, giữ nguyên chữ và id). Mỗi câu có `id`, `cau_hoi`, `dieu` (danh sách số Điều), `loai`, `tap`, `nguon`, `trang_thai`; quy ước đầy đủ ở docstring `src/index/bo_cau_hoi.py`.

| `tap` | số câu | dùng để |
|---|---|---|
| `dev` | 70 | chẩn đoán và chọn tham số (được xem kết quả, được chỉnh) |
| `xac_nhan` | 70 | xác nhận độc lập cấu hình đã chọn trên dev; chạy với tham số ĐÃ CHỐT, không quét |
| `kiem_tra` | 58 | đóng băng, xác nhận cuối, không quét, không chỉnh theo kết quả |
| `phu` | 112 | phủ nốt: mỗi Điều về tội phạm chưa có câu ở ba tập trên có một câu; đo độ phủ toàn bộ luật, chạy với tham số ĐÃ CHỐT, không quét |

- `loai = don`: `dieu` là các Điều chấp nhận (trúng một trong số đó là đúng). `loai = nhieu_dieu`: tình huống gồm nhiều hành vi, `dieu` là các Điều cần tìm đủ; các script chấm Hit@k hiện bỏ qua loại này để khỏi chấm sai.
- `nguon` (`claude` | `nguoi_dung` | `ban_an`): ai soạn câu. Hiện cả 310 câu do Claude soạn nên điểm có thể cao hơn thực tế; câu bạn tự viết hoặc lấy từ bản án thật nên ghi nguồn riêng để báo cáo riêng.
- Chọn tập: `--tap dev|xac_nhan|kiem_tra|phu` (`danh_gia.py` còn có `tat_ca`). `thu_xep_lai.py` bắt buộc `--chi-w` với `xac_nhan` / `kiem_tra` / `phu`; `danh_gia.py --quet` / `--quet-cau-hoi` chỉ chạy trên `dev`; `sinh_cau_hoi.py --theo-bo` chỉ đọc số Điều của tập `dev`. Không tập nào được đưa chữ câu hỏi cho LLM sinh câu (test chặn cụm 4 từ trùng với lời nhắc).
- Sửa nhãn / thêm câu: chỉ sửa `eval/bo_cau_hoi.json`, rồi `python scripts/kiem_tra_bo_cau_hoi.py` (định dạng, id / câu trùng, Điều trùng giữa các tập, số Điều có thật trong chỉ mục) và `python scripts/xuat_xem_duyet.py` (bảng câu hỏi – Điều – tiêu đề Điều ra `eval/xem_duyet.md` để duyệt nhãn).
- Đổi chữ một câu làm mất cache điểm đã chấm của câu đó (khóa cache gồm chữ câu hỏi); sửa nhãn `dieu` thì không.

### Bước 4c — xếp lại top-N Điều bằng mô hình đọc cả câu hỏi và chữ Điều (thí nghiệm)

Tìm bằng vector so câu hỏi với từng đoạn luật độc lập nên hay nhầm giữa các Điều anh em, dù đáp án thường đã nằm trong top 5 (bộ dev: Hit@1 72,9%, Hit@3 88,6%, Hit@5 92,9%). Thí nghiệm: lấy top 5 Điều theo vector, chấm lại từng cặp (câu hỏi, chữ Điều) bằng một mô hình đọc cả hai, rồi trộn với điểm vector: `z(điểm xếp lại) + w * z(điểm vector)`.

```
python scripts/tai_xep_lai.py                                  # một lần: tải bge-reranker-v2-m3 (ONNX, ~2,3 GB) vào models/
pip install onnxruntime tokenizers
python scripts/thu_xep_lai.py                                  # bộ dev, quét w
python scripts/thu_xep_lai.py --xep-lai llm --llm qwen3:8b     # cách khác: Qwen3-8B qua Ollama chấm điểm 0-10 (không cần tải thêm)
python scripts/thu_xep_lai.py --tap kiem_tra --chi-w 0.25   # xác nhận cuối, CHỈ một w đã chốt trên dev
```

Kết quả đo (bge-reranker-v2-m3, xếp lại top 5, 70 câu dev nháp, chữ Điều đầy đủ cắt ở 512 token): Hit@1 72,9% → 78,6% (w = 0 và 0,25) và 80,0% (w = 0,5), MRR 0,813 → 0,858–0,865, Hit@3 88,6% → 92,9% (chạm trần top 5). Các giá trị w từ 1 trở lên giảm về 74–76%. Số câu cứu/phá ở w = 0: 8/4 (kiểm định dấu p = 0,39), ở w = 0,5: 6/1 (p = 0,12). Tức hướng tích cực và khá ổn định ở w ≤ 0,5 nhưng CHƯA có ý nghĩa thống kê trên 70 câu; chọn w trong dải 0-0,5, không chọn ô cao nhất. Xếp lại top 3 cho 77,1% (kém top 5). Dùng chữ ngắn (tiêu đề + khoản 1) không tốt hơn chữ đầy đủ (75,7-78,6%).

Mô hình cứu được các câu khác hẳn từ vựng ("đưa tiền cho công an để khỏi bị phạt" → Điều 364, "mạo danh cán bộ" → 339) nhưng vẫn nhầm giữa các Điều sát nhau (364/365, 308/414) và có nhãn dev còn tranh cãi (ví dụ "làm mất súng của đơn vị" có thể hợp lý với cả 308 lẫn 414), nên cần người duyệt nhãn trước khi coi con số là bằng chứng. Cái giá: ~1,1 giây mỗi cặp trên CPU 2 nhân (5 Điều ≈ 5 giây mỗi câu hỏi). Cách dùng Qwen3-8B qua Ollama đã có mã và test với LLM giả nhưng CHƯA chạy với Ollama thật.
