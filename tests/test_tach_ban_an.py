"""Kiểm thử bộ tách bản án (src/ban_an/tach.py).

Hai nhóm:
  * văn bản GIẢ LẬP (tên hư cấu, tự viết) - luôn chạy, nằm trong repo được;
  * 10 bản án THẬT trong inbox/ho_so_vu_an_txt/ - chỉ chạy khi có thư mục đó (inbox/ bị git-ignore vì văn bản công bố vẫn còn
    thông tin cá nhân sót), nên KHÔNG chép nguyên văn bản án thật vào tests/.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.ban_an.tach import (chuan_hoa, khoa, ket_qua_cap_tren, nguon_nhan_de_xuat, rut_dieu, rut_nhan_quyet_dinh, tach, tim_dau_hieu_ro_ri,
                             tim_pii)

ROOT = Path(__file__).resolve().parents[1]
THU_MUC_THAT = ROOT / "inbox" / "ho_so_vu_an_txt"


# --------------------------------------------------------------------------------------------------------------------
# văn bản giả lập
# --------------------------------------------------------------------------------------------------------------------
def _phuc_tham(*, ngat_trang: bool = True, loi_ocr: bool = False, bo_nhan_dinh: bool = False) -> str:
    h_nd = "NỌI DUNG VỤ ÁN:" if loi_ocr else "NỘI DUNG VỤ ÁN:"
    h_nh = "NHẠN ĐỊNH CỦA TÒA ÁN:" if loi_ocr else "NHẬN ĐỊNH CỦA TÒA ÁN:"
    nd = ("\f" if ngat_trang else "") + h_nd
    nhan_dinh = "" if bo_nhan_dinh else f"""
{h_nh}
[1] Đơn kháng cáo của bị cáo Nguyễn Văn An làm trong thời hạn luật định nên hợp lệ.
[2] Xét kháng cáo xin giảm nhẹ hình phạt: bị cáo có nhân thân tốt, thành khẩn khai báo, đã khắc phục hậu quả; Tòa án cấp sơ thẩm đã
áp dụng các tình tiết giảm nhẹ và quyết định mức hình phạt tương xứng với tính chất, mức độ hành vi phạm tội của bị cáo.
[3] Do đó không có căn cứ chấp nhận kháng cáo của bị cáo.
"""
    return f"""TÒA ÁN NHÂN DÂN TỈNH XYZ
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM

Bản án số: 12/2025/HS-PT
Ngày: 03/02/2025

NHÂN DANH NƯỚC CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Bị cáo có kháng cáo: Nguyễn Văn An; bị tạm giam từ ngày 30/9/2024.
3
{nd}
Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An lẻn vào nhà anh Trần Văn Bình lấy trộm một chiếc xe máy trị giá 18.000.000 đồng
rồi đem bán. Cơ quan điều tra truy tố về tội “Trộm cắp tài sản” theo khoản 1 Điều 173 Bộ luật hình sự.
Tại Bản án hình sự sơ thẩm số 05/2024/HS-ST ngày 12/12/2024, Tòa án nhân dân huyện ABC quyết định:
Áp dụng khoản 1 Điều 173; điểm s khoản 1 Điều 51; Điều 38 Bộ luật hình sự. Xử phạt bị cáo Nguyễn Văn An 12 (mười hai) tháng tù
về tội “Trộm cắp tài sản”.
Ngoài ra, bản án sơ thẩm còn quyết định về xử lý vật chứng, án phí và quyền kháng cáo theo quy định.
Ngày 20/12/2024, bị cáo Nguyễn Văn An có đơn kháng cáo xin giảm nhẹ hình phạt.
Tại phiên tòa phúc thẩm, bị cáo giữ nguyên kháng cáo.
4
{nhan_dinh}
QUYẾT ĐỊNH:
Căn cứ điểm a khoản 1 Điều 355, Điều 356 Bộ luật Tố tụng hình sự;
Không chấp nhận kháng cáo của bị cáo Nguyễn Văn An. Giữ nguyên Bản án hình sự sơ thẩm số 05/2024/HS-ST ngày 12/12/2024.
Áp dụng khoản 1 Điều 173; điểm s khoản 1 Điều 51; Điều 38 của Bộ luật hình sự;
Xử phạt bị cáo Nguyễn Văn An 12 (mười hai) tháng tù về tội “Trộm cắp tài sản”.
Bản án phúc thẩm có hiệu lực pháp luật kể từ ngày tuyên án.
Nơi nhận: TM. HỘI ĐỒNG XÉT XỬ PHÚC THẨM
- Bị cáo; - Lưu hồ sơ. THẨM PHÁN - CHỦ TỌA PHIÊN TÒA
5
"""


QUYET_DINH_THU_TUC = """TÒA ÁN NHÂN DÂN CẤP CAO
TẠI THÀNH PHỐ ABC
Số: 08/2025/HSPT-QĐ
Thành phố ABC, ngày 17 tháng 6 năm 2025.
QUYẾT ĐỊNH
Về việc giải quyết kháng cáo quá hạn
NHẬN THẤY:
Ngày 21/4/2025, Tòa án nhân dân tỉnh XYZ nhận được đơn kháng cáo đề ngày 17/4/2025 của bị cáo Lê Thị Cúc đối với Bản án hình sự sơ thẩm
số 50/2025/HS-ST ngày 31 tháng 3 năm 2025 với nội dung xin giảm nhẹ hình phạt.
XÉT THẤY:
Việc kháng cáo của bị cáo Lê Thị Cúc là quá thời hạn quy định tại Điều 333 của Bộ luật Tố tụng hình sự; lý do bị cáo nêu là không chính đáng.
QUYẾT ĐỊNH:
1. Không chấp nhận kháng cáo quá hạn của bị cáo Lê Thị Cúc.
2. Bản án hình sự sơ thẩm số 50/2025/HS-ST có hiệu lực thi hành.
CÁC THẨM PHÁN
THẨM PHÁN – CHỦ TỌA PHIÊN HỌP
"""


# --------------------------------------------------------------------------------------------------------------------
# chuẩn hóa, tiêu đề
# --------------------------------------------------------------------------------------------------------------------
def test_chuan_hoa_ngat_trang_so_trang_nbsp():
    t = chuan_hoa("Dòng một\u00a0có  NBSP\n7\n\f\nNỘI DUNG VỤ ÁN:\n\n\n\nHết")
    assert "7" not in t.split("\n")                       # số trang đứng một mình bị bỏ
    assert "\f" not in t and "\u00a0" not in t
    assert "NỘI DUNG VỤ ÁN:" in t.split("\n")             # \f không còn dính đầu dòng tiêu đề
    assert "\n\n\n" not in t


def test_tach_phuc_tham_gia_lap_du_bon_phan():
    kq = tach(_phuc_tham())
    assert kq["kieu"] == "ban_an" and kq["dat"] is True and kq["canh_bao"] == []
    p = kq["phan"]
    assert khoa(p["noi_dung"].split("\n")[0]) == "NOI DUNG VU AN"
    assert khoa(p["nhan_dinh"].split("\n")[0]) == "NHAN DINH CUA TOA AN"
    assert khoa(p["quyet_dinh"].split("\n")[0]) == "QUYET DINH"
    assert "Bản án số: 12/2025/HS-PT" in p["dau"] and "Khoảng 20 giờ" not in p["dau"]
    assert p["cuoi"].startswith("Nơi nhận")
    assert "Xử phạt" not in p["nhan_dinh"] and "Đơn kháng cáo" not in p["quyet_dinh"]


def test_meta_gia_lap():
    m = tach(_phuc_tham())["meta"]
    assert (m["so"], m["nam"], m["hau_to"], m["cap"], m["ngay"]) == ("12", 2025, "HS-PT", "phuc_tham", "2025-02-03")
    assert m["toa_an"] == "TÒA ÁN NHÂN DÂN TỈNH XYZ"
    assert m["so_tham_tham_chieu"] == "05/2024/HS-ST"


def test_ngay_lay_ngay_som_nhat_va_chiu_gach_ocr():
    # OCR: "Ngày 28 — 10 — 2025"; ngày tạm giữ đứng sau không được chọn nhầm
    t = tach("TÒA ÁN X\nBản án số: 1/2025/HS-PT\nNgày 28 — 10 — 2025\ntạm giữ từ ngày 30/9/2023\n" + "NỘI DUNG VỤ ÁN:\nabc\nNHẬN ĐỊNH CỦA TÒA ÁN:\nabc\nQUYẾT ĐỊNH:\nabc")
    assert t["meta"]["ngay"] == "2025-10-28"
    t = tach("Quyết định số: 09/2025/HS-GĐT\nNgày 03 tháng 4 năm 2025\ntạm giữ từ ngày 30/9/2023\nNỘI DUNG VỤ ÁN:\nabc\nNHẬN ĐỊNH CỦA TÒA ÁN:\nabc\nQUYẾT ĐỊNH:\nabc")
    assert t["meta"]["ngay"] == "2025-04-03" and t["meta"]["cap"] == "giam_doc_tham"


def test_tieu_de_sai_dau_do_ocr_van_nhan_ra():
    kq = tach(_phuc_tham(loi_ocr=True, ngat_trang=False))
    assert kq["dat"] is True and set(kq["tieu_de"]) == {"noi_dung", "nhan_dinh", "quyet_dinh", "cuoi"}


def test_thieu_tieu_de_nhan_dinh_bao_canh_bao_khong_nem_loi():
    kq = tach(_phuc_tham(bo_nhan_dinh=True))
    assert kq["dat"] is False
    assert any("NHẬN ĐỊNH" in c for c in kq["canh_bao"])
    assert kq["phan"]["quyet_dinh"].startswith("QUYẾT ĐỊNH")        # các phần còn lại vẫn tách được


def test_van_ban_khong_phai_ban_an():
    kq = tach("Xin chào, đây là một đoạn văn bất kỳ.\nKhông có tiêu đề nào cả.")
    assert kq["kieu"] == "khong_ro" and kq["dat"] is False and kq["phan"]["noi_dung"] == ""


def test_quyet_dinh_thu_tuc_tach_duoc_nhung_khong_dung_lam_mau():
    kq = tach(QUYET_DINH_THU_TUC)
    assert kq["dat"] is True and kq["kieu"] == "quyet_dinh_thu_tuc"
    assert kq["nguon_nhan_de_xuat"] == "khong_dung_lam_mau"
    assert kq["meta"]["ngay"] == "2025-06-17" and kq["meta"]["hau_to"] == "HSPT-QĐ"
    assert kq["phan"]["nhan_dinh"].startswith("XÉT THẤY")                # bước "xét thấy" đóng vai nhận định
    assert kq["phan"]["quyet_dinh"].startswith("QUYẾT ĐỊNH") and "Không chấp nhận" in kq["phan"]["quyet_dinh"]


# --------------------------------------------------------------------------------------------------------------------
# cắt đoạn chép bản án sơ thẩm (chỗ lộ đáp án)
# --------------------------------------------------------------------------------------------------------------------
def test_cat_so_tham_khoi_su_viec():
    nd = tach(_phuc_tham())["noi_dung"]
    assert nd["su_viec"].startswith("Khoảng 20 giờ") and "Xử phạt" not in nd["su_viec"] and "Áp dụng" not in nd["su_viec"]
    assert nd["so_tham_trich"].startswith("Tại Bản án hình sự sơ thẩm số 05/2024/HS-ST")
    assert "Xử phạt bị cáo Nguyễn Văn An 12 (mười hai) tháng tù" in nd["so_tham_trich"]
    assert "kháng cáo" not in nd["so_tham_trich"].split("quyền kháng cáo")[0]          # chưa lẫn diễn biến kháng cáo
    assert nd["dien_bien"].startswith("Ngày 20/12/2024, bị cáo Nguyễn Văn An có đơn kháng cáo")
    assert "phiên tòa phúc thẩm" in nd["dien_bien"]


def test_dong_ngay_trong_trich_khong_bi_nhan_nham_la_moc_ket_thuc():
    # dòng gãy "ngày 15/6/2025." đứng đầu dòng và ngay sau là "quyền kháng cáo" không phải mốc diễn biến kháng cáo
    t = _phuc_tham().replace("Xử phạt bị cáo Nguyễn Văn An 12 (mười hai) tháng tù\nvề tội",
                             "Xử phạt bị cáo Nguyễn Văn An 12 (mười hai) tháng tù, khấu trừ tạm giam từ\nngày 15/6/2025.\nvề tội")
    nd = tach(t)["noi_dung"]
    assert "ngày 15/6/2025." in nd["so_tham_trich"] and nd["dien_bien"].startswith("Ngày 20/12/2024")


def test_dau_hieu_ro_ri_con_sot_trong_su_viec():
    r = tach(_phuc_tham())["ro_ri_trong_su_viec"]
    assert r.get("truy_to") == 1 and r.get("toi_danh_ngoac_kep") == 1 and r.get("dieu_luat", 0) >= 1
    assert tim_dau_hieu_ro_ri("Hai bên xô xát, bị cáo đánh anh B gây thương tích.") == {}


# --------------------------------------------------------------------------------------------------------------------
# nhãn thô từ phần Quyết định
# --------------------------------------------------------------------------------------------------------------------
def test_rut_dieu_khoan_diem():
    assert rut_dieu("điểm b khoản 2 Điều 318, Điều 38; điểm s khoản 1, khoản 2 Điều 51; Điều 58") == [
        {"dieu": 318, "chu": None, "khoan": 2, "diem": "b"}, {"dieu": 38, "chu": None, "khoan": None, "diem": None},
        {"dieu": 51, "chu": None, "khoan": 1, "diem": "s"}, {"dieu": 51, "chu": None, "khoan": 2, "diem": None},
        {"dieu": 58, "chu": None, "khoan": None, "diem": None}]
    # OCR: "q. s" thay cho "q, s"; nhóm điểm gắn với khoản đứng ngay sau nó
    r = rut_dieu("điểm c khoản 3 Điều 134: Các điểm b, e, q. s khoản 1; khoản 2 Điều 51; Điều 65")
    assert {(x["dieu"], x["khoan"], x["diem"]) for x in r} == {
        (134, 3, "c"), (51, 1, "b"), (51, 1, "e"), (51, 1, "q"), (51, 1, "s"), (51, 2, None), (65, None, None)}
    assert rut_dieu("Điều 355, 356") == [{"dieu": 355, "chu": None, "khoan": None, "diem": None},
                                         {"dieu": 356, "chu": None, "khoan": None, "diem": None}]


def test_rut_dieu_co_chu_cai():
    """«Điều 217a» là một Điều khác với «Điều 217»: không được cắt mất chữ cái."""
    assert rut_dieu("điểm a khoản 1 Điều 217a") == [{"dieu": 217, "chu": "a", "khoan": 1, "diem": "a"}]
    r = rut_dieu("Điều 256a, Điều 51; khoản 2 Điều 217a, 217")
    assert [(x["dieu"], x["chu"], x["khoan"]) for x in r] == [(256, "a", None), (51, None, None), (217, "a", 2), (217, None, None)]
    # chữ đứng riêng sau số (nhóm điểm của khoản kế tiếp) không bị coi là chữ của Điều
    assert [(x["dieu"], x["chu"]) for x in rut_dieu("Điều 51 và điểm b khoản 1 Điều 52")] == [(51, None), (52, None)]


def test_bo_luat_bi_vo_chu_van_phan_loai_dung():
    """PDF hay vỡ chữ ('T ố tụng', 'B ộ luật'): Điều 355, 357 của Bộ luật Tố tụng hình sự không được tính là Điều của BLHS."""
    n = rut_nhan_quyet_dinh("1. Căn cứ điểm b khoản 1 Điều 355, điểm c khoản 1 Điều 357 của B ộ luật T ố tụng hình sự, chấp nhận kháng cáo. "
                            "Áp dụng điểm b, d khoản 2 Điều 321; Điều 51 của Bộ luật Hình sự năm 2015, xử phạt 06 tháng tù về tội “Đánh bạc”.")
    assert [d["bo_luat"] for d in n["dan_chieu"]] == ["tttt_hinh_su", "hinh_su"]
    assert {x["dieu"] for x in n["dan_chieu"][0]["dieu"]} == {355, 357}
    assert {x["dieu"] for x in n["dan_chieu"][1]["dieu"]} == {321, 51}
    assert rut_nhan_quyet_dinh("Căn cứ Điều 584 B ộ luật D ân sự, buộc bồi thường.")["dan_chieu"][0]["bo_luat"] == "dan_su"


def test_rut_nhan_phan_biet_bo_luat_hinh_su_va_to_tung():
    n = rut_nhan_quyet_dinh(
        "Căn cứ điểm a khoản 1 Điều 355 Bộ luật Tố tụng hình sự; Áp dụng khoản 1 Điều 173; Điều 38 của Bộ luật hình sự; "
        "Xử phạt bị cáo A 12 tháng tù về tội “Trộm cắp tài sản”. Căn cứ Điều 584 Bộ luật Dân sự, buộc bồi thường.")
    loai = [d["bo_luat"] for d in n["dan_chieu"]]
    assert loai == ["tttt_hinh_su", "hinh_su", "dan_su"]
    assert [(x["dieu"], x["khoan"]) for x in n["dan_chieu"][1]["dieu"]] == [(173, 1), (38, None)]
    assert n["toi_danh"] == ["Trộm cắp tài sản"] and len(n["xu_phat"]) == 1


def test_toi_danh_co_dau_hai_cham_va_ba_gia_ban_an():
    n = rut_nhan_quyet_dinh("Tuyên bố bị cáo X phạm tội: “Lừa đảo chiếm đoạt tài sản”. Áp dụng điểm a khoản 4 Điều 174 BLHS.")
    assert n["toi_danh"] == ["Lừa đảo chiếm đoạt tài sản"]
    assert n["dan_chieu"][0]["bo_luat"] == "hinh_su" and n["dan_chieu"][0]["dieu"] == [{"dieu": 174, "chu": None, "khoan": 4, "diem": "a"}]


def test_ket_qua_cap_tren_va_nguon_nhan():
    assert ket_qua_cap_tren("Không chấp nhận kháng cáo. Giữ nguyên Bản án sơ thẩm.") == ["giu_nguyen", "khong_chap_nhan_khang_cao"]
    assert nguon_nhan_de_xuat("phuc_tham", ["giu_nguyen"]) == "so_tham_trich"
    assert nguon_nhan_de_xuat("phuc_tham", ["sua", "chap_nhan_khang_cao"]) == "quyet_dinh_cap_tren"
    assert nguon_nhan_de_xuat("phuc_tham", ["sua", "giu_nguyen"]) == "ket_hop"
    assert nguon_nhan_de_xuat("phuc_tham", ["huy"]) == "khong_co_nhan_cuoi"
    assert nguon_nhan_de_xuat("giam_doc_tham", ["huy", "giu_nguyen"]) == "so_tham_trich"      # hủy phúc thẩm, giữ nguyên sơ thẩm
    assert nguon_nhan_de_xuat("so_tham", []) == "quyet_dinh"
    kq = tach(_phuc_tham())
    assert kq["nguon_nhan_de_xuat"] == "so_tham_trich" and kq["nhan_so_tham_trich"]["toi_danh"] == ["Trộm cắp tài sản"]


def test_tim_pii_chi_dem():
    c = tim_pii("VneID 001096043xxx; sinh ngày 09/02/1996; sinh năm 1957; con ông Nguyễn Văn K; tài khoản 0059101230260xxx; ĐT 0912345678")
    assert c["so_bi_che_xxx"] == 2 and c["sinh_ngay_day_du"] == 1 and c["sinh_nam"] == 1 and c["dien_thoai"] == 1
    assert tim_pii("Số tiền 1.652.000 đồng, khoảng 20 giờ") == {}


# --------------------------------------------------------------------------------------------------------------------
# 10 bản án thật (bỏ qua nếu không có)
# --------------------------------------------------------------------------------------------------------------------
# (kiểu, cấp, số, ngày, nguồn nhãn đề xuất) - đã đối chiếu bằng mắt với từng PDF
THAT = {
    "vu_an_01": ("ban_an", "phuc_tham", "543", "2025-10-28", "khong_co_nhan_cuoi"),         # hủy bản án sơ thẩm, điều tra lại (bản quét, OCR)
    "vu_an_02": ("ban_an", "phuc_tham", "568", "2025-12-15", "quyet_dinh_cap_tren"),        # sửa hình phạt
    "vu_an_03": ("ban_an", "phuc_tham", "549", "2025-12-09", "so_tham_trich"),              # bác kháng cáo (bản quét, OCR)
    "vu_an_04": ("ban_an", "phuc_tham", "275", "2025-12-24", "so_tham_trich"),
    "vu_an_05": ("ban_an", "phuc_tham", "271", "2025-12-23", "khong_co_nhan_cuoi"),         # hủy, điều tra lại
    "vu_an_06": ("ban_an", "phuc_tham", "201", "2025-11-04", "so_tham_trich"),
    "vu_an_07": ("quyet_dinh_thu_tuc", "phuc_tham", "08", "2025-06-17", "khong_dung_lam_mau"),   # kháng cáo quá hạn
    "vu_an_08": ("quyet_dinh_thu_tuc", "phuc_tham", "429", "2025-06-11", "khong_dung_lam_mau"),  # đình chỉ phúc thẩm (bản quét, OCR)
    "vu_an_09": ("ban_an", "phuc_tham", "485", "2025-06-03", "quyet_dinh_cap_tren"),
    "vu_an_10": ("ban_an", "giam_doc_tham", "09", "2025-04-03", "so_tham_trich"),           # giám đốc thẩm
}
# (tên tệp, tội danh phải có trong nhãn trích được ở phần Quyết định hoặc đoạn chép bản án sơ thẩm)
TOI_DANH_THAT = {
    "vu_an_01": "Lừa đảo chiếm đoạt tài sản", "vu_an_03": "Có ý gây thương tích", "vu_an_04": "Gây rối trật tự công cộng",
    "vu_an_05": "Lừa đảo chiếm đoạt tài sản", "vu_an_06": "Buôn lậu", "vu_an_10": "Đánh bạc",
}
# (tên tệp, nguồn, (Điều, khoản, điểm)) phải có trong dẫn chiếu Bộ luật hình sự
DIEU_THAT = [("vu_an_02", "nhan_quyet_dinh", (324, 3, "a")), ("vu_an_04", "nhan_quyet_dinh", (318, 2, "b")),
             ("vu_an_05", "nhan_so_tham_trich", (174, 4, "a")), ("vu_an_10", "nhan_so_tham_trich", (321, 2, "b"))]


def _tach_that(ten: str) -> dict:
    f = THU_MUC_THAT / f"{ten}.txt"
    if not f.exists():
        pytest.skip(f"không có {f} (inbox/ không nằm trong git)")
    return tach(f.read_text(encoding="utf-8"))


@pytest.mark.parametrize("ten", sorted(THAT))
def test_that_bon_phan_va_thong_tin(ten):
    kieu, cap, so, ngay, nguon = THAT[ten]
    kq = _tach_that(ten)
    assert kq["dat"] is True, kq["canh_bao"]
    assert (kq["kieu"], kq["meta"]["cap"], kq["meta"]["so"], kq["meta"]["ngay"], kq["nguon_nhan_de_xuat"]) == (kieu, cap, so, ngay, nguon)
    p = kq["phan"]
    assert khoa(p["quyet_dinh"].split("\n")[0]).startswith("QUYET DINH")
    assert len(p["noi_dung"]) > 150 and len(p["nhan_dinh"]) > 100 and len(p["quyet_dinh"]) > 300


@pytest.mark.parametrize("ten", [t for t, v in THAT.items() if v[0] == "ban_an"])
def test_that_su_viec_khong_con_ket_qua_cua_ban_an_so_tham(ten):
    kq = _tach_that(ten)
    nd = kq["noi_dung"]
    assert len(nd["so_tham_trich"]) > 400                              # có đoạn chép bản án sơ thẩm và đã tách riêng
    assert khoa(nd["so_tham_trich"]).startswith(("TAI BAN AN", "VOI NOI DUNG NEU TREN TAI BAN AN"))
    assert "Xử phạt" not in nd["su_viec"] and "Tuyên bố" not in nd["su_viec"] and "Áp dụng" not in nd["su_viec"]
    assert len(nd["su_viec"]) > 1000 and len(nd["dien_bien"]) > 300


@pytest.mark.parametrize("ten,toi", sorted(TOI_DANH_THAT.items()))
def test_that_toi_danh(ten, toi):
    kq = _tach_that(ten)
    tat_ca = kq["nhan_quyet_dinh"]["toi_danh"] + kq["nhan_so_tham_trich"]["toi_danh"]
    assert toi in tat_ca, tat_ca


@pytest.mark.parametrize("ten,nguon,dkd", DIEU_THAT)
def test_that_dieu_khoan_diem(ten, nguon, dkd):
    kq = _tach_that(ten)
    co = {(x["dieu"], x["khoan"], x["diem"]) for d in kq[nguon]["dan_chieu"] if d["bo_luat"] == "hinh_su" for x in d["dieu"]}
    assert dkd in co, sorted(co, key=str)[:12]


def test_that_pii_con_sot():
    # số liệu đã đo: văn bản công bố KHÔNG ẩn danh hoàn toàn (ngày sinh, số định danh bị che một phần, tên cha mẹ...)
    f = THU_MUC_THAT / "vu_an_02.txt"
    if not f.exists():
        pytest.skip("không có inbox/")
    c = tach(f.read_text(encoding="utf-8"))["pii"]
    assert c.get("sinh_ngay_day_du", 0) >= 1 and c.get("so_bi_che_xxx", 0) >= 1
