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
- Ngày bắt đầu hiệu lực của BLHS 2015: chính văn bản ghi 01/07/2016 nhưng Nghị quyết 41/2017/QH14 (Điều 1 khoản 1 điểm a) đã lùi sang **01/01/2018**. Kho đã ghi điều này bằng một lệnh `hoan_hieu_luc` đã duyệt, kèm văn bản nguồn (xem «Hiệu lực của cả bộ luật» ngay dưới). Lookup chỉ còn in cảnh báo khi kho CHƯA ghi nghị quyết lùi hiệu lực.
- Lệnh "đánh số lại" chưa hỗ trợ (báo là chưa hiểu). Các heuristic sửa từ ngữ (khoảng trắng, chữ hoa đầu câu) chỉ kiểm chứng đầy đủ khi đối chiếu với văn bản hợp nhất (Bước 3).
- Mục bộ trích lệnh không hiểu chỉ nằm trong `raw/<slug>/commands.json` và `log_nap.ghi_chu`, chưa có giao diện duyệt riêng.

### Hiệu lực của cả bộ luật và nhiều bộ luật nối tiếp (BLHS 1999 → BLHS 2015)

Mỗi bộ luật chính (có tên viết tắt, vd `BLHS`) có một khoảng hiệu lực nửa mở `[ngày bắt đầu, ngày hết hiệu lực)`. Khi tra theo một ngày, hệ thống chọn bộ luật có khoảng chứa ngày đó:

| Thời kỳ | Bộ luật | Trong kho |
|---|---|---|
| từ 01/01/2018 | Bộ luật hình sự 2015 (100/2015/QH13) | đã nạp |
| 01/07/2000 – 31/12/2017 | Bộ luật hình sự 1999 (15/1999/QH10), sửa đổi bởi 15/2008/QH12 (từ 01/01/2009, chỉ Điều 270 khoản 1) và 37/2009/QH12 (từ 01/01/2010) | đã nạp (xem «Nạp một bộ luật cũ» ngay dưới) |
| 01/01/1986 – 30/06/2000 | Bộ luật hình sự 1985 | chưa nạp (chỉ biết tên và mốc) |

Ngày thuộc thời kỳ chưa nạp thì giao diện/agent nói rõ «ngày đó thuộc bộ luật nào, kho chưa có» chứ không trả nhầm Điều của BLHS 2015. Danh sách thời kỳ đã biết nhưng chưa nạp nằm ở `agent.luat_chua_nap` trong `config.yaml` (không bắt buộc; có giá trị mặc định); bộ luật nào đã nạp (cùng số hiệu) thì tự bị loại khỏi danh sách này.

```powershell
python scripts/hoan_hieu_luc.py xem                                  # các bộ luật chính trong kho và khoảng hiệu lực của từng bộ
python scripts/hoan_hieu_luc.py hoan --dich 100/2015/QH13 --ngay-moi 2018-01-01 --nguon 41/2017/QH14 `
    --ten-nguon "Nghị quyết số 41/2017/QH14 ..." --ngay-ban-hanh 2017-06-20 --hieu-luc-tu 2017-07-05 `
    --vi-tri "Điều 1 khoản 1 điểm a" --can-cu "..." --nguoi "Tên bạn"      # CHẠY THỬ trên bản sao; thêm --ap-dung để ghi thật
python scripts/hoan_hieu_luc.py het --so-hieu 15/1999/QH10 --ngay-het 2018-01-01 --thay-boi 100/2015/QH13   # BLHS 1999 hết hiệu lực khi BLHS 2015 có hiệu lực
python scripts/build_index.py --tat-ca                               # dựng chỉ mục cho MỌI bộ luật chính đã nạp (hoặc --van-ban SỐ_HIỆU để thêm từng bộ)
```

- `hoan` ghi một lệnh `hoan_hieu_luc` ĐÃ DUYỆT (kèm văn bản nguồn + nhật ký nạp, ghi rõ ai nhập và căn cứ) rồi dựng lại phiên bản; chạy lại lệnh y hệt thì không làm gì. `--ap-dung` tự sao lưu `db/luat.sqlite.bak-THỜI-GIAN` trước khi ghi.
- `het` đặt `van_ban.ngay_het_hieu_luc` (ngày ĐẦU TIÊN không còn hiệu lực) rồi dựng lại để mọi phiên bản của bộ luật cũ bị cắt đúng ngày đó; cảnh báo nếu bộ luật thay thế bắt đầu hiệu lực khác ngày này (hở hoặc chồng nhau).
- Sau khi đổi khoảng hiệu lực phải chạy lại `build_index.py` (đoạn nào đổi ngày hoặc ngữ cảnh thì nhúng lại; phần còn lại dùng cache).
- Bản văn «như khi Quốc hội thông qua» (`bản gốc`) luôn lấy nguyên văn lúc ban hành, không phụ thuộc ngày bắt đầu hiệu lực.
- BLHS 1999 đã nạp cùng 2 luật sửa đổi (xem mục ngay dưới). Luật sửa đổi của bộ luật cũ nạp bằng `parse_amending_law.py --pham-vi 15/1999/QH10` và `extract_commands.py --dich 15/1999/QH10`: không đụng vào `pham_vi_sua_doi` trong `config.yaml` (mặc định vẫn là BLHS 2015).

### Nạp một bộ luật cũ và các luật sửa đổi của nó (ví dụ BLHS 1999 → bản ngày 05/05/2010)

Đã làm cho BLHS 1999; làm lại y hệt cho bộ luật cũ khác khi có tệp văn bản. Mỗi bước đều dừng chờ người xem rồi mới đi tiếp.

```powershell
# 1. Bộ luật gốc. Văn bản BLHS 1999 KHÔNG tự ghi ngày có hiệu lực nên phải nêu ngày và căn cứ (căn cứ hiện ra thành cảnh báo bắt buộc người duyệt đọc)
python scripts/parse_base_law.py "inbox/15_1999_QH10_46056.docx" --ten-viet-tat BLHS --ngay-hieu-luc 2000-07-01 `
    --can-cu-hieu-luc "mục 1 Nghị quyết 32/1999/QH10 ngày 21/12/1999: Bộ luật hình sự có hiệu lực từ 01/7/2000"
#    -> xem raw/15-1999-QH10/parsed.json, điền review.json (lỗi phải miễn kèm ghi chú, cảnh báo phải liệt kê vào da_xem_canh_bao), rồi:
python scripts/ingest_base_law.py 15-1999-QH10
python scripts/hoan_hieu_luc.py het --so-hieu 15/1999/QH10 --ngay-het 2018-01-01 --thay-boi 100/2015/QH13 --ap-dung
# 2. Luật sửa đổi của nó: --pham-vi nói «Bộ luật hình sự» trong luật này là văn bản nào
python scripts/parse_amending_law.py "inbox/37_2009_QH12_90648.docx" --pham-vi 15/1999/QH10
python scripts/parse_amending_law.py "inbox/15_2008_QH12_66950.docx" --pham-vi 15/1999/QH10
python scripts/extract_commands.py 37-2009-QH12 --dich 15/1999/QH10 --nap
python scripts/apply_commands.py bao-cao 15/1999/QH10 37/2009/QH12 --xuat bao_cao_37_2009.md   # ĐỌC rồi mới duyệt
python scripts/apply_commands.py duyet 15/1999/QH10 37/2009/QH12 --nguoi "Tên bạn"
python scripts/apply_commands.py ap-dung 15/1999/QH10
python scripts/build_index.py --tat-ca                                                          # cần Ollama đang chạy
```

Điều cần biết về lần nạp BLHS 1999 hiện có trong kho:
- **Ngày 01/07/2000** lấy từ mục 1 Nghị quyết 32/1999/QH10 (đã đối chiếu trên trang văn bản; chính BLHS 1999 không ghi ngày). Lệnh `hoan_hieu_luc` ghi nguồn này mang tên «Kintakashi (Claude nhập theo yêu cầu)», còn văn bản Nghị quyết chỉ là dòng ghi tay (số hiệu, ngày thông qua, căn cứ; ngày hiệu lực của chính nghị quyết lấy bằng ngày thông qua và chưa đối chiếu).
- **Luật 15/2008/QH12** có một câu lệnh («Bỏ cụm từ “trưng mua” tại đoạn 2 khoản 1 Điều 270 … và sửa đổi đoạn này như sau») mà bộ trích không hiểu; lệnh được ghi tay thành một lệnh thay cụm từ cho ra đúng câu mới của khối trích dẫn (`log_nap.phuong_phap = 'thu_cong'`, `raw/15-2008-QH12/commands.json`). Sáu mục còn lại của luật này sửa luật khác nên chỉ được ghi nhận, không áp.
- **Duyệt tạm.** Việc duyệt bộ luật gốc (`raw/15-1999-QH10/review.json`) và 42 lệnh sửa đổi do Claude làm theo yêu cầu của người dùng, ghi rõ «chờ người xác nhận»: đã đối chiếu số Điều (344 → 353 từ 01/01/2010), Điều 84, 138, 230a, 270, 313 và các Điều bị bãi bỏ (131, 183, 184, 199), nhưng chưa ai đọc lại toàn bộ. Người dùng nên mở `streamlit run src/review/app_base_law.py` (bộ luật gốc) và `apply_commands.py bao-cao` (lệnh sửa đổi) để đọc lại, rồi duyệt lại dưới tên mình.
- **Lỗi gõ có sẵn trong tệp Word nguồn được giữ nguyên** (hệ thống không tự sửa văn bản luật). Đã biết: «trẻ e m» ở 9 nút (Điều 228, 252, 254, 255, 256, 313, 314), «ôô tô» ở Điều 206 và 207 khoản 1, «dâm ôô» ở Điều 313 khoản 1; «a) Có tổ chức» thiếu dấu «;» trong khối trích dẫn của Luật 37/2009 (Điều 120 khoản 2 điểm a); và ở Điều 313 khoản 1 câu «Điều 230 (…quân sự) Điều 230a (tội khủng bố);» thiếu dấu «;» vì Luật 37/2009 chỉ nói «bổ sung cụm từ … vào sau cụm từ …». Danh sách này chưa phải là tất cả (chưa có văn bản hợp nhất của BLHS 1999 để đối chiếu như đã làm với BLHS 2015). Muốn sửa, dùng cơ chế hiệu đính có bằng chứng (`src/apply/hieu_dinh.py`), do người duyệt từng chỗ.

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

Lưu ý: bản xuất là dữ liệu dẫn xuất để tra cứu, không phải văn bản chính thức. Lệnh sửa đổi và đề xuất hiệu đính chưa duyệt không nằm trong bản xuất (đầu file có ghi số lượng còn chờ). Hiệu lực của BLHS 2015 tính từ 01/01/2018 (Nghị quyết 41/2017/QH14, xem Bước 2): xuất ở ngày trước đó báo «không có nội dung nào có hiệu lực» vì kho chưa nạp BLHS 1999.

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
| `dev` | 70 + 14 | chẩn đoán và chọn tham số (được xem kết quả, được chỉnh); 14 câu `nhieu_dieu` (`dn01`–`dn14`) để chỉnh lời nhắc tách hành vi |
| `xac_nhan` | 70 | xác nhận độc lập cấu hình đã chọn trên dev; chạy với tham số ĐÃ CHỐT, không quét |
| `kiem_tra` | 58 + 26 | đóng băng, xác nhận cuối, không quét, không chỉnh theo kết quả; 26 câu `nhieu_dieu` (`qn01`–`qn26`) |
| `phu` | 112 | phủ nốt: mỗi Điều về tội phạm chưa có câu ở ba tập trên có một câu; đo độ phủ toàn bộ luật, chạy với tham số ĐÃ CHỐT, không quét. Nhãn đã được người dùng duyệt 2026-10-14 (`da_duyet`) |

- `loai = don`: `dieu` là các Điều chấp nhận (trúng một trong số đó là đúng). `loai = nhieu_dieu`: tình huống gồm nhiều hành vi, `dieu` là các Điều cần tìm đủ; các script chấm Hit@k bỏ qua loại này để khỏi chấm sai (trúng một Điều rồi bỏ sót Điều kia là kết quả SAI ở đây); chúng được chấm riêng bằng `scripts/danh_gia_nhieu.py` (xem dưới). 40 câu hiện có: 2–3 Điều mỗi câu, mỗi Điều ứng với một hành vi bị xử riêng, mọi ngưỡng (số tiền, tỷ lệ thương tích, số hóa đơn…) đã được đối chiếu với văn bản Điều trong chỉ mục; chưa có người duyệt (`nhap`).
- `nguon` (`claude` | `nguoi_dung` | `ban_an`): ai soạn câu. Hiện cả 350 câu do Claude soạn nên điểm có thể cao hơn thực tế (với 40 câu nhiều Điều thì càng như vậy: cùng một người viết câu và viết nhãn); câu bạn tự viết hoặc lấy từ bản án thật nên ghi nguồn riêng để báo cáo riêng.
- Chọn tập: `--tap dev|xac_nhan|kiem_tra|phu` (`danh_gia.py` còn có `tat_ca`). `thu_xep_lai.py` bắt buộc `--chi-w` với `xac_nhan` / `kiem_tra` / `phu`; `danh_gia.py --quet` / `--quet-cau-hoi` chỉ chạy trên `dev`; `sinh_cau_hoi.py --theo-bo` chỉ đọc số Điều của tập `dev`. Không tập nào được đưa chữ câu hỏi cho LLM sinh câu (test chặn cụm 4 từ trùng với lời nhắc).
- Sửa nhãn / thêm câu: chỉ sửa `eval/bo_cau_hoi.json`, rồi `python scripts/kiem_tra_bo_cau_hoi.py` (định dạng, id / câu trùng, Điều trùng giữa các tập, số Điều có thật trong chỉ mục) và `python scripts/xuat_xem_duyet.py` (bảng câu hỏi – Điều – tiêu đề Điều ra `eval/xem_duyet.md` để duyệt nhãn).
- Đổi chữ một câu làm mất cache điểm đã chấm của câu đó (khóa cache gồm chữ câu hỏi); sửa nhãn `dieu` thì không.

#### Đo «tìm đủ» cho tình huống nhiều Điều

```
python scripts/danh_gia_nhieu.py                         # mốc «không tách» (cả tình huống là MỘT truy vấn), tập dev
python scripts/danh_gia_nhieu.py --du-doan tach_dev.json # so với bản đã tách hành vi: {"dn01": ["hành vi 1", "hành vi 2"], ...}
python scripts/danh_gia_nhieu.py --tap kiem_tra          # tập đóng băng: chỉ chạy với lời nhắc đã chốt, đúng một lần cho số báo cáo cuối
```

Số đo chính là **tìm đủ** (mọi Điều đáp án đều nằm trong tập Điều được hiển thị; mỗi hành vi hiển thị `--m` Điều đầu, mặc định 3), kèm bao phủ (recall mức Điều), chính xác (precision mức Điều), tỷ lệ hành vi có Điều đáp án (đo tách thừa) và tỷ lệ tách đúng số hành vi (`src/index/tim_du.py`). Bản tách luôn được so với mốc «không tách» ở **cùng số Điều hiển thị** để không thắng chỉ vì hiển thị nhiều hơn.

Số tham chiếu trên 14 câu dev (bge-m3 ONNX trên máy đám mây, chưa phải Ollama của bạn, nên chỉ để lấy cỡ; 1 câu = 7 điểm %): không tách, hiển thị 3 / 6 / 9 Điều → tìm đủ 7% / 29% / 43%. Tách **lý tưởng** (hành vi do người soạn câu tự viết lại bằng lời đời thường, không nêu tên tội, lưu ở `eval/tach_ly_tuong_dev.json` để chạy lại bằng `--du-doan`; đây là **trần**, không phải kết quả của mô hình nào) → tìm đủ 29% / 50% / 57% / 64% khi mỗi hành vi hiển thị 2 / 3 / 4 / 5 Điều, bao phủ 52% / 63% / 67% / 70%. Tách đúng giúp nhiều (cùng ~6 Điều hiển thị: 21% → 50%) nhưng chưa đủ: mô tả hành vi đời thường không có tên tội vẫn tìm sai Điều ở nhiều hành vi (làm giả con dấu, tham ô, lừa đảo chiếm đoạt, giam người…). Đó là lý do bước 5 cần mô tả hành vi mang từ gọi tên tội; số này sẽ đo lại với mô hình tách thật trên máy bàn.

##### Thử tách hành vi bằng qwen3:4b, chỉ bằng lời nhắc (chạy trên máy bàn)

`scripts/tach_hanh_vi.py` cho qwen3:4b (Ollama) tách từng tình huống nhiều Điều của một tập thành các hành vi, rồi `scripts/danh_gia_nhieu.py --du-doan` chấm kết quả. Lời nhắc hệ thống là đúng `HE_THONG` của tập train (để sau này so công bằng với bản tinh chỉnh); ví dụ mẫu lấy từ phần train của `train/tinh_huong.json`, loại mọi mẫu có Điều trùng đáp án của bộ đo.

```powershell
python scripts/tach_hanh_vi.py --tap dev --kieu ten_toi --vi-du 3      # ghi eval/tach_dev_qwen3-4b_ten_toi_3vd.json (+ .log.jsonl)
python scripts/tach_hanh_vi.py --tap dev --kieu thuan   --vi-du 0      # không tiền tố tên tội, không ví dụ mẫu
python scripts/tach_hanh_vi.py --tap dev --xem-loi-nhac                # chỉ in lời nhắc, không gọi mô hình
python scripts/danh_gia_nhieu.py --tap dev --du-doan eval/tach_dev_qwen3-4b_ten_toi_3vd.json
```

`--kieu ten_toi|thuan` đo tiền tố tên tội, `--vi-du N` số ví dụ mẫu, `--quy-tac` thêm đoạn quy tắc tách. Chọn bằng tập `dev`; tập `kiem_tra` chỉ chạy MỘT lần với lời nhắc đã chốt (cần `--da-chot`, không ghi đè kết quả cũ). Đầu ra được ép theo schema JSON; câu trả lời hỏng được thử lại hai lần (đổi seed), vẫn hỏng thì giữ nguyên cả tình huống làm một hành vi và ghi lỗi vào `.log.jsonl` thay vì bỏ qua.

##### Đo «gần chuẩn Claude» của khâu tách hành vi

Mọi đáp án hiện có do Claude soạn nên «tìm đủ» đo khoảng cách tới Claude, còn khâu TÁCH chưa có chuẩn riêng (hàng «tách lý tưởng» viết tay sau khi biết đáp án nên không khách quan). Cách đo: một phiên Claude MỚI, không thấy đáp án, tách các câu dev (lặp 3 phiên); so cách tách của mô hình với 3 bản đó, và lấy độ lệch giữa các bản Claude làm TRẦN.

```powershell
python scripts/xuat_chuan_mu.py                        # eval/chuan_mu/cau_hoi_mu_dev.json + LOI_NHAC_CHUAN_MU.md (không có đáp án Điều)
# dán lời nhắc vào 3 phiên Claude mới, lưu eval/chuan_mu/claude_1.json, claude_2.json, claude_3.json
python scripts/so_voi_chuan.py --chuan eval/chuan_mu/claude_*.json --du-doan eval/tach_dev_<mô hình>_thuan_0vd.json --sim bge --tim-du
```

Số đo chính: đồng số hành vi và `ghép` (ghép 1-1 tối ưu, không ngưỡng); F1 theo ngưỡng chỉ tham khảo (ngưỡng chưa hiệu chỉnh; `--sim chu` chạy offline nhưng thô). Có khoảng tin cậy bootstrap theo cặp cho hiệu «mô hình − trần». Chuẩn là Claude chứ không phải luật: số này đo độ giống Claude, không đo đúng-sai pháp lý. Mã: `src/index/so_voi_chuan.py`, test `tests/test_so_voi_chuan.py`.

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

## Bước 5 — tập train cho bước tách hành vi (một sự việc → nhiều hành vi → nhiều Điều)

Một tình huống đời thường thường dẫn đến nhiều Điều (vừa trộm vừa đập phá, vừa nhận hối lộ vừa làm giả hồ sơ…). Đường ống dự kiến: **tách** tình huống thành từng hành vi bị xử riêng → **tìm** Điều cho từng hành vi (bước 4) → **gộp** thành gợi ý "hành vi → 2–3 Điều" để người dùng tự đối chiếu. Bước tách là việc của một mô hình nhỏ chạy cục bộ (qwen3:4b, có thể tinh chỉnh LoRA); thư mục `train/` là dữ liệu cho nó.

**MỘT file nguồn: `train/tinh_huong.json`** (tách hẳn bộ đo `eval/bo_cau_hoi.json`, không câu nào của bộ đo đi vào đây). Mỗi mẫu: `id`, `tinh_huong` (đoạn văn đời thường), `hanh_vi` (danh sách `{mo_ta, dieu}`), `loai` (`don` = đúng 1 hành vi, `nhieu` = từ 2 hành vi), `nguon`, `trang_thai` (`nhap` | `da_duyet`). Quy ước đầy đủ nằm ở đầu `src/index/tap_train.py`.

- `mo_ta`: một câu ngắn, tự đủ nghĩa, KHÔNG nêu số Điều; vừa là đích mà mô hình tách phải học viết ra, vừa là câu truy vấn đem đi tìm Điều.
- `dieu`: các Điều chấp nhận cho hành vi đó. Mô hình tách KHÔNG nhìn thấy trường này khi huấn luyện; nó dùng để chấm cả đường ống và kiểm độ phủ. Quy ước nhãn: mỗi việc có thể bị xử riêng là một phần tử `hanh_vi`; tình tiết tăng nặng nằm trong cùng một Điều thì không tách thêm.
- Hiện có 450 mẫu: 106 một hành vi + 344 nhiều hành vi (267 mẫu 2 hành vi, 55 mẫu 3, 21 mẫu 4, 1 mẫu 5; tổng 894 hành vi), phủ 315/315 Điều về tội phạm (mỗi Điều làm đáp án 1–32 lần, trung vị 2).

```
python scripts/kiem_tra_train.py                        # định dạng, id/tình huống trùng, rò rỉ sang bộ đo, thống kê; có chỉ mục thì kiểm thêm số Điều có thật và độ phủ
python scripts/kiem_tra_train.py --bat-buoc-phu         # coi Điều tội phạm chưa có mẫu nào là lỗi
python scripts/xuat_sft.py                              # train/sft_train.jsonl + train/sft_val.jsonl (val 10%, chia cố định theo băm id)
python scripts/xuat_sft.py --chi-da-duyet               # chỉ mẫu đã được người duyệt
```

Dòng SFT theo định dạng `messages` (system / user / assistant); đích chỉ là `{"hanh_vi": ["mô tả 1", "mô tả 2"]}`. Tập `val` để theo dõi loss khi huấn luyện, KHÔNG phải bộ đo.

**Chống rò rỉ.** Bộ kiểm từ chối mẫu có cụm ≥ 9 âm tiết liền nhau trùng một câu của bộ đo (`K_TRUNG` trong `tap_train.py`; ngắn hơn là cụm pháp lý chung, từng gây báo nhầm), nhắc số Điều / khoản, hoặc trùng văn bản. Khi soạn, mức giống nhau về nghĩa với bộ đo cũng được dò bằng bge-m3 (cos ≥ 0,90 bị coi là gần trùng; lần soạn hiện tại: lớn nhất 0,89).

**Cổng truy hồi cho `mo_ta`.** Mô tả hành vi ngắn, thuần đời thường tìm Điều kém hơn câu hỏi đầy đủ; thêm từ gọi tên tội đời thường ("hiếp dâm", "vu khống", "lừa đảo chiếm đoạt", "đưa hối lộ"…) làm Hit@5 trên lô đầu tăng từ 84% lên 98%. Do đó mọi `mo_ta` đã được đo: tìm bằng vector (bge-m3, chỉ mục hiện hành) phải đưa Điều đáp án vào top 5 (894 hành vi: Hit@1 73,2%, Hit@3 94,9%, Hit@5 100%). Hệ quả cần biết: khoảng 47% `mo_ta` (420/894) có tiền tố dạng "Hiếp dâm: …" — mô hình tách sẽ học viết cả tên tội, có thể sai tên khi gặp tình huống lạ; nên so thêm bản bỏ tiền tố khi đo.

**Hạn chế (đọc trước khi dùng).** Toàn bộ 450 mẫu do Claude soạn (`nguon = claude`); ngày 2026-10-14 người dùng đã duyệt nhãn nên cả 450 mẫu là `da_duyet`, nhưng chưa có luật sư xem; các cặp Điều gần nhau (263/264, 270/271, 275/276, 138/139, 404/406, 411/412, 114/115…) và một số nhãn về tội ít gặp cần luật sư xem. Bốn hành vi cho phép 2 Điều (`t003`: 123/134, `t269`: 140/185, `t244`: 174/290, `t305`: 140/185). Tình huống từ cùng một người soạn nên giọng văn đồng nhất hơn người dùng thật; chưa có mẫu "không có hành vi phạm tội". Không dùng tập này để chỉnh tham số truy hồi hay xếp lại: đó là việc của `eval/`.

**Đợt vá nhãn đầu tiên (2026-10-14).** 53 mục từ `train/sua_nhan_train.md` (rà từ `xem_duyet_train.md`) đã áp vào `tinh_huong.json`; phần khác với bản vá và lý do nằm ở `train/nhat_ky_sua_nhan.md`. Các mục có điều kiện «đã bị xử phạt/xử lý kỷ luật mà còn vi phạm» được đối chiếu với văn bản Điều trong chỉ mục. Nhãn vẫn là nháp: bản vá do người/AI soạn, chưa luật sư duyệt. 

**Đợt 2 (2026-10-14).** Người dùng duyệt các mục ✎ trong `xem_duyet_train.md` nên mọi mẫu chuyển `da_duyet`; làm rõ `t408` và `t279`. Quy tắc «giả nhãn hiệu» đã chốt: hàng bị làm giả rồi bán như hàng thật (kể cả gắn thương hiệu nổi tiếng) → Điều 192–195 theo loại hàng; chỉ nhái nhãn hiệu / bao bì và bán công khai như hàng nhái → Điều 226.

## Bước 6 — agent và giao diện cho người dùng thường

Một câu hỏi vào, một câu trả lời có cấu trúc ra: **chữ luật lấy nguyên văn từ kho**, kèm nguồn sửa đổi, khoảng hiệu lực và lời nhắc «chỉ tham khảo, không phải tư vấn pháp lý». Không bước nào gọi API; không bước nào để mô hình ngôn ngữ viết lại chữ luật. Đây là chức năng 1 (tra cứu) đã gói thành thứ người không biết lập trình dùng được. Kho hiện có Bộ luật hình sự 2015; agent đã sẵn cho nhiều bộ luật nối tiếp nhau (chọn bộ luật theo ngày, xem «Hiệu lực của cả bộ luật» ở Bước 2); chưa mở rộng sang luật khác lĩnh vực.

```
chay_tra_cuu.bat                                              # giao diện web cục bộ (Streamlit), mở http://localhost:8501
python -m streamlit run src/ui/app_tra_cuu.py                 # cách chạy không qua .bat
python scripts/hoi.py "Điều 173"                              # dòng lệnh: một câu
python scripts/hoi.py                                         # dòng lệnh: hỏi nhiều câu liên tiếp (dòng trống để thoát)
python scripts/hoi.py "khoản 2 Điều 173 tại ngày 01/01/2018"
python scripts/hoi.py "so sánh Điều 173 bản gốc và hiện hành"
python scripts/hoi.py "lén lấy xe máy của hàng xóm" --json    # in JSON đầy đủ (TraLoi.to_dict), tiện cho thực nghiệm
```

Tuỳ chọn của `hoi.py`: `--ngay YYYY-MM-DD` (xem luật tại ngày đó), `--khong-tach`, `--xep-lai`, `-m` (số Điều mỗi hành vi), `-k`, `--db`, `--index`. Biến môi trường `LEXO_DB`, `LEXO_INDEX` đổi đường dẫn kho/chỉ mục cho cả giao diện lẫn dòng lệnh; `LEXO_GIA=1` dùng vector giả và bộ tách giả (CHỈ để thử giao diện và test, kết quả không có nghĩa).

**Các loại câu hỏi hiểu được** (mã: `src/agent/y_dinh.py`):

| Kiểu | Ví dụ | Việc làm |
|---|---|---|
| Tra Điều | `Điều 173`, `khoản 2 Điều 173`, `điểm đ khoản 1 Điều 168`, `173`, `dieu 173` | nguyên văn tại ngày chọn (mặc định hôm nay), chỉ khoản/điểm nếu hỏi; nhiều Điều một lúc (tối đa 5) |
| Xem theo ngày | `Điều 173 ngày 01/01/2018`, `tháng 7/2025`, `năm 2017` | bản có hiệu lực tại ngày đó; chỉ nêu năm thì lấy cuối năm và liệt kê sửa đổi rơi trong năm |
| Lịch sử | `lịch sử sửa đổi Điều 173` | các lần sửa/bổ sung/bãi bỏ, luật nào, khoản nào, hiệu lực từ ngày nào |
| So sánh | `so sánh Điều 173 năm 2017 và hiện nay`, `khác gì bản gốc` | hai bản cạnh nhau, chỗ khác tô màu từng từ |
| Quan hệ / chuyển tiếp | `những luật nào đã sửa đổi BLHS`, `điều khoản chuyển tiếp` | từ bảng quan hệ văn bản và điều khoản chuyển tiếp đã nạp |
| Tìm theo mô tả | `lén lấy xe máy của hàng xóm` | vài Điều gần nhất (bge-m3 + FTS), kèm khoản/điểm khớp nhất |
| Tình huống dài | đoạn kể ≥ 12 từ không nêu số Điều | tách thành từng hành vi (mô hình tách local), mỗi hành vi gợi ý m = 3 Điều + «Đọc nguyên văn» |
| Ngoài phạm vi | `Điều 5 BLDS`, `luật đất đai…` | nói rõ kho chỉ có luật nào; không đoán |

**Chọn bộ luật theo ngày.** Ngày xem (hôm nay, ngày chọn ở thanh bên «Xem luật theo một ngày khác hôm nay», hoặc ngày nêu trong câu) quyết định bộ luật: từ 01/01/2018 là BLHS 2015, trước đó là bộ luật cũ (BLHS 1999 sửa đổi 2009 cho 2010–2017). Nêu năm trong câu («BLHS 2015», «BLHS 1999») thì lấy đúng bộ đó; nếu ngày xem nằm ngoài khoảng hiệu lực của nó, hệ thống nói rõ bộ luật nào đang áp dụng vào ngày đó. Chỉ gõ «Điều 173 BLHS» (không năm) thì vẫn theo ngày (dòng lệnh cũng vậy: `python scripts/lookup.py "Điều 138 BLHS" --ngay 2010-05-05` tự lấy BLHS 1999 và nói rõ đã chọn bộ nào). Ngày thuộc thời kỳ chưa nạp: báo rõ, không trả nhầm. «Bản gốc» là bản lúc Quốc hội thông qua. Lịch sử / quan hệ / chuyển tiếp không nêu năm thì dùng bộ luật đang áp dụng hôm nay. So sánh hai mốc thuộc hai bộ luật khác nhau thì hiện hai Điều riêng (số Điều đổi giữa các bộ luật nên không tô khác biệt từng từ).

**Khác kế hoạch §14 (và vì sao).** (1) Phân loại ý định bằng **luật** (bỏ dấu + regex), không dùng LLM nhỏ: tra «Điều 173» mà sai số Điều vì mô hình «đoán» là lỗi không chấp nhận được; luật thì kiểm thử được từng ca, chạy được khi chưa bật Ollama. Cái giá: câu lạ rơi vào nhánh «tìm theo mô tả» (vô hại, vì chỉ trả Điều gần nghĩa). (2) **Không có bước 4b** (LLM diễn giải): mọi chữ luật trên màn hình lấy từ kho, đúng nguyên tắc chức năng 1 là tham khảo, không kết luận. Câu xin kết luận («có tội không», «bị phạt bao nhiêu năm») vẫn được trả Điều liên quan, kèm lời nhắc rằng hệ thống không đưa kết luận pháp lý. (3) Quy tắc năm: `BLHS 2015` / `năm 2015` là năm của văn bản, không phải ngày xem luật; chỉ nêu năm khác thì là mốc cuối năm.

**Hạ cấp khi thiếu thành phần** (giao diện hiện 🟢/🟠 ở thanh bên và nút «Kiểm tra lại kết nối»; mọi chuyển đổi đều có thông báo bằng lời, không tự lặng lẽ):

| Thiếu | Hệ quả |
|---|---|
| Ollama / bge-m3, hoặc chưa có chỉ mục vector | tìm theo mô tả chuyển sang FTS (từ khoá). Đo trên bộ dev: câu một Điều Hit@1 48,6%, Hit@3 71,4%, Hit@5 80,0% (có vector: 72,9 / 88,6 / 92,9); câu đời thường rất xa từ vựng luật có thể lệch hẳn |
| Mô hình tách (`agent.tach_model`) | tình huống dài tìm như một câu duy nhất, hiện 5 Điều; «tìm đủ» tập Điều chỉ khoảng 15% (có tách bằng n368: 17/34 = 50%). Thiếu cả hai: hiện cảnh báo vàng «kết quả sẽ rất kém» |
| Bộ xếp lại (onnxruntime / model) | bỏ qua, giữ thứ tự cũ (mặc định đã tắt) |

Tra Điều, lịch sử, so sánh, quan hệ **không cần Ollama** — chỉ cần `db/luat.sqlite`.

Chuẩn bị Ollama cho đủ chức năng: `ollama pull bge-m3`; tên mô hình tách phải có trong `ollama list` và nằm trong `agent.tach_model` ở `config.yaml` (mặc định thử `qwen3-8b-lexo-sach-n368`, rồi `lexo-tach`). Chưa có thì giao diện vẫn chạy ở chế độ hạ cấp.

**Kiểm thử.** `tests/test_agent_y_dinh.py` (định tuyến + ngày/khoản/điểm), `tests/test_agent.py` (agent trên kho thử + vector giả + hạ cấp), `tests/test_agent_trinh_bay.py` (Markdown, diff), `tests/test_ui_tra_cuu.py` (giao diện bằng `streamlit.testing`, không mở trình duyệt): 80 test; `tests/test_agent_nhieu_luat.py` (chọn bộ luật theo ngày, thời kỳ chưa nạp, so sánh qua hai bộ luật, chỉ mục cũ: 21 test); `tests/test_hieu_luc_vb.py` (ghi hiệu lực cả bộ luật: 11 test); `tests/test_amending_luat_cu.py` (luật sửa đổi viết theo lối cũ: dấu ngoặc gõ sai, khối trích dẫn thiếu dấu đóng, câu lệnh bị động, tên Điều, đích suy từ tên luật: 13 test); `tests/test_cli_nhieu_luat.py` (lookup.py khi có nhiều bộ luật cùng tên: 4 test); toàn bộ dự án 504 test xanh. Đã chạy thử trên kho thật ở chế độ FTS (chưa chạy với Ollama thật).

**Giới hạn đã biết (đọc trước khi dùng).**
- BLHS 2015 trong kho có hiệu lực từ 01/01/2018 (Nghị quyết 41/2017/QH14, Điều 1 khoản 1 điểm a; lệnh do người dùng yêu cầu ghi và nên tự đối chiếu lại với văn bản gốc, xem `scripts/hoan_hieu_luc.py xem`). Ngày từ 01/07/2000 đến 31/12/2017 thuộc BLHS 1999 (đã nạp, kèm sửa đổi 2009); ngày trước 01/07/2000 thuộc BLHS 1985 mà kho CHƯA nạp: hệ thống nói rõ điều đó thay vì trả Điều của bộ luật khác.
- 29 đề xuất hiệu đính kỹ thuật còn chờ duyệt (không đổi nội dung điều luật) được ghi ở chân thanh bên và ở từng Điều liên quan.
- «Tình huống dài» phụ thuộc chất lượng mô hình tách; mỗi hành vi chỉ gợi ý Điều gần nghĩa nhất, **không** phải kết luận về tội danh.
- Chỉ có Bộ luật Hình sự 2015 (3 luật sửa đổi) và Bộ luật Hình sự 1999 (2 luật sửa đổi), cùng văn bản nguồn ghi tay của hai nghị quyết 41/2017/QH14 và 32/1999/QH10 (chỉ có số hiệu, ngày và căn cứ chứ không có nội dung); hỏi luật khác sẽ được từ chối lịch sự.

## Chức năng 2 — phân tích vụ án (nhập nội dung vụ án → bản tóm tắt kiểu cáo trạng)

Bấm đúp `chay_phan_tich_vu_an.bat` (hoặc `streamlit run src/ui/app_vu_an.py`). Dán diễn biến vụ án; kết quả gồm: ai có dấu hiệu phạm tội gì (Điều/khoản), vì sao, đoạn trích nguyên văn từ sự việc làm căn cứ (✅ có trong sự việc, ⚠️ không tìm thấy nên cần kiểm tra) và nguyên văn Điều luật lấy từ kho. Bản văn kiểu cáo trạng tải về được (.txt, .json).

Đường ống (`src/agent/vu_an.py`): tìm Điều ứng viên (bge-m3 + FTS5, cả sự việc và từng hành vi) → chọn Điều (mô hình LoRA của kế hoạch Kaggle V3, nếu đã nạp vào Ollama; chưa có thì dùng thứ hạng tìm kiếm) → Qwen3 soạn JSON theo từng người từ nguyên văn các Điều → kiểm: Điều phải nằm trong danh sách đã đưa, khoản phải có thật, trích dẫn phải có nguyên văn trong sự việc.

- Cần Ollama với `qwen3:8b` để soạn. Thiếu thì giao diện **chỉ gợi ý Điều** và nói rõ (thanh bên có đèn trạng thái từng bước).
- Sau khi học xong trên Kaggle: gộp GGUF, `ollama create <tên>`, rồi ghi tên đó vào `config.yaml` mục `vu_an.chon_model` (mặc định tìm `qwen3-8b-lexo-chon-dieu-cbba-v1`).
- Chỉ để tham khảo: không phải cáo trạng, không phải kết luận pháp lý; chưa xét chứng cứ, tuổi, năng lực chịu trách nhiệm hình sự, tình tiết tăng nặng/giảm nhẹ, mức hình phạt.
- Thử giao diện không cần Ollama: `LEXO_GIA=1` (vector và mô hình giả, kết quả KHÔNG có nghĩa). Test: `pytest tests/test_vu_an.py tests/test_ui_vu_an.py`.
- Xem bảng Recall@K của gói đo mà không giải nén: `python scripts/xem_recall_zip.py lexo_do_ban_an_cbba.zip` (thoát với mã 2 nếu dưới sàn 80%).
