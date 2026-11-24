"""Phân loại ý định bằng luật (src/agent/y_dinh.py): chạy thuần chữ, không cần kho, không cần Ollama."""
import pytest

from src.agent import y_dinh as yd
from src.agent.y_dinh import bo_dau, chuan_hoa, phan_loai, tim_moc

NARRATIVE = ("Chủ quán karaoke biết nhiều nhóm khách thuê phòng để hút ma túy đá nhưng vẫn cho thuê, còn tính thêm tiền dọn dẹp. "
             "Ngoài ra anh còn bán từng gói ma túy tổng hợp cho khách ngay tại quán để kiếm thêm.")


@pytest.mark.parametrize("cau, loai, dieu", [
    ("Điều 173", yd.TRA_DIEU, ["173"]),
    ("điều 173 blhs 2015", yd.TRA_DIEU, ["173"]),
    ("dieu 173", yd.TRA_DIEU, ["173"]),                                  # gõ không dấu
    ("173", yd.TRA_DIEU, ["173"]),                                       # gõ trơn số
    ("Điều 173a", yd.TRA_DIEU, ["173a"]),
    ("Điều 173, Điều 174 và Điều 175", yd.TRA_DIEU, ["173", "174", "175"]),
    ("Điều 100/2015/QH13 điều 173", yd.TRA_DIEU, ["173"]),              # số hiệu văn bản không phải số Điều
    ("lịch sử sửa đổi Điều 173", yd.LICH_SU, ["173"]),
    ("Điều 173 đã được sửa đổi những lần nào", yd.LICH_SU, ["173"]),
    ("so sánh Điều 173 năm 2017 và hiện nay", yd.SO_SANH, ["173"]),
    ("Điều 173 khác gì bản gốc", yd.SO_SANH, ["173"]),
    ("Điều 173 thay đổi gì so với trước", yd.SO_SANH, ["173"]),
    ("điều khoản chuyển tiếp của luật sửa đổi", yd.CHUYEN_TIEP, []),
    ("Những luật nào đã sửa đổi Bộ luật Hình sự?", yd.QUAN_HE, []),
    ("quan hệ văn bản của BLHS", yd.QUAN_HE, []),
    ("lén lấy xe máy của hàng xóm", yd.TIM_MO_TA, []),
    ("trộm xe máy thì bị phạt bao nhiêu năm tù", yd.TIM_MO_TA, []),
    (NARRATIVE, yd.TINH_HUONG, []),
    ("xin chào", yd.TRO_GIUP, []),
    ("bạn làm được gì", yd.TRO_GIUP, []),
    ("Điều 5 BLDS", yd.NGOAI_PHAM_VI, ["5"]),
    ("luật đất đai quy định gì", yd.NGOAI_PHAM_VI, []),
    ("", yd.TRONG, []),
    ("   ", yd.TRONG, []),
])
def test_y_dinh_va_so_dieu(cau, loai, dieu):
    y = phan_loai(cau)
    assert (y.loai, y.dieu) == (loai, dieu)


def test_khoan_diem_chi_khi_mot_dieu():
    y = phan_loai("khoản 2 Điều 173")
    assert (y.khoan, y.diem) == ("2", None)
    y = phan_loai("điểm đ khoản 1 Điều 168")
    assert (y.dieu, y.khoan, y.diem) == (["168"], "1", "đ")             # «đ» giữ nguyên, không bị nhầm với «d»
    y = phan_loai("điểm d khoản 1 Điều 168")
    assert y.diem == "d"
    y = phan_loai("khoản 2 Điều 173 và Điều 174")
    assert y.khoan is None                                                # nhiều Điều: không áp khoản cho Điều nào


def test_ngay_thang():
    assert [(m.iso, m.kieu) for m in phan_loai("Điều 173 tại ngày 01/01/2018").moc] == [("2018-01-01", "ngay")]
    assert [(m.iso, m.kieu) for m in phan_loai("Điều 173 ngày 5 tháng 3 năm 2019").moc] == [("2019-03-05", "ngay")]
    assert [(m.iso, m.kieu) for m in phan_loai("Điều 173 ngày 2019-03-05").moc] == [("2019-03-05", "ngay")]
    y = phan_loai("Điều 173 tháng 7/2025")
    assert [(m.iso, m.tu, m.kieu) for m in y.moc] == [("2025-07-31", "2025-07-01", "thang")]
    y = phan_loai("Điều 173 năm 2017")
    assert [(m.iso, m.tu, m.kieu, m.goc) for m in y.moc] == [("2017-12-31", "2017-01-01", "nam", "năm 2017")]   # trạng thái cuối năm
    y = phan_loai("so sánh Điều 173 từ 1/1/2017 đến 31/12/2025")
    assert [m.iso for m in y.moc] == ["2017-01-01", "2025-12-31"]
    y = phan_loai("Điều 173 khác gì bản gốc")
    assert [m.iso for m in y.moc] == [yd.MOC_GOC]
    y = phan_loai("so sánh Điều 173 năm 2017 và hiện nay")
    assert [m.iso for m in y.moc] == ["2017-12-31", yd.MOC_HOM_NAY]


def test_nam_cua_van_ban_khong_phai_ngay():
    y = phan_loai("Điều 173 BLHS 2015")
    assert (y.nam_van_ban, y.moc, y.viet_tat) == (2015, [], "BLHS")
    y = phan_loai("Điều 173 Bộ luật Hình sự 2015 năm 2017")
    assert y.nam_van_ban == 2015 and [m.iso for m in y.moc] == ["2017-12-31"]
    y = phan_loai("Điều 173 năm 2015")                                   # đúng một «năm 2015» và 2015 là năm của văn bản trong kho
    assert (y.nam_van_ban, y.moc) == (2015, [])
    y = phan_loai("Điều 173 năm 2015", nam_van_ban=())                    # kho không có văn bản năm 2015: đó là ngày
    assert [m.iso for m in y.moc] == ["2015-12-31"]
    y = phan_loai("Điều 173 theo 100/2015/QH13")                          # số hiệu không bị đọc thành năm
    assert y.moc == []


def test_ngay_khong_hop_le_bi_bo_va_co_luu_y():
    y = phan_loai("Điều 40 ngày 31/02/2020")
    assert y.moc == [] and any("không hợp lệ" in x for x in y.luu_y)
    moc, _, luu_y, _ = tim_moc(bo_dau("tháng 13/2020"))
    assert moc == [] and luu_y


def test_cau_ke_chuyen_khong_doc_ngay():
    y = phan_loai("Năm 2017, " + NARRATIVE)
    assert y.loai == yd.TINH_HUONG and y.moc == []                         # ngày xảy ra việc không phải ngày cần xem luật


def test_so_dieu_trong_cau_ke_chuyen_dai():
    y = phan_loai("Điều 173 áp dụng thế nào cho trường hợp " + NARRATIVE)
    assert y.loai == yd.TINH_HUONG and y.dieu == [] and any("Điều 173" in x for x in y.luu_y)


def test_luat_khac_chan_hoac_chi_nhac():
    y = phan_loai("Điều 5 BLDS")
    assert (y.loai, y.van_ban_khac) == (yd.NGOAI_PHAM_VI, "Bộ luật Dân sự")
    y = phan_loai("theo Luật Giao thông, " + NARRATIVE)                    # kể chuyện dài: không chặn, chỉ nhắc
    assert y.loai == yd.TINH_HUONG and y.van_ban_khac == "Luật Giao thông" and y.luu_y


def test_linh_vuc_ngoai_chi_nhac():
    y = phan_loai("tôi đang ly hôn, chồng tôi đánh tôi")
    assert y.loai == yd.TIM_MO_TA and any("ngoài Bộ luật Hình sự" in x for x in y.luu_y)


def test_xin_ket_luan():
    assert phan_loai("trộm xe máy có tội không").xin_ket_luan
    assert phan_loai("trộm xe máy thì bị xử thế nào").xin_ket_luan is False           # «bị xử thế nào» kiểu bộ đo không phải xin kết luận
    assert phan_loai("trộm xe máy thì bị phạt bao nhiêu năm").xin_ket_luan
    assert phan_loai("tôi ăn trộm xe thì ngồi tù bao nhiêu năm").xin_ket_luan


def test_toi_da_dieu():
    y = phan_loai("Điều 1, Điều 2, Điều 3, Điều 4, Điều 5, Điều 6, Điều 7")
    assert len(y.dieu) == yd.TOI_DA_DIEU and y.luu_y


def test_chuan_hoa_nfd_thanh_nfc():
    import unicodedata
    nfd = unicodedata.normalize("NFD", "Điều 173")                         # bàn phím/clipboard có thể cho dạng tổ hợp
    assert chuan_hoa(nfd) == "điều 173" and phan_loai(nfd).dieu == ["173"]
    assert bo_dau("Điều Đặng") == "Dieu Dang"
