"""Trình bày (src/agent/trinh_bay.py): Markdown của Điều, lọc khoản/điểm, khung hiệu lực, HTML so sánh. Hàm thuần, không cần kho."""
from src.agent.trinh_bay import cua_so_hieu_luc, diff_html, ghi_chu_nguon, loc_khoan, markdown_dieu, md_thoat
from src.query.lookup import Nguon, UnitView


def nguon(i=1, tu="2018-01-01"):
    return Nguon(i, "12/2017/QH14", "Luật sửa đổi", "luat", "2017-06-20", "Điều 1 khoản 3", "sua_doi", tu)


def dieu():
    d1 = UnitView("diem", "a", None, "phạt cảnh cáo;", [], "2016-07-01", None)
    d2 = UnitView("diem", "b", None, "phạt tiền;", [], "2018-01-01", None, [nguon()])
    k1 = UnitView("khoan", "1", None, "Mọi hành vi bị xử lý như sau:", [d1, d2], "2016-07-01", None)
    k2 = UnitView("khoan", "2", None, "Tự thú được miễn trách nhiệm.", [], "2018-01-01", "2026-01-01", [nguon()])
    return UnitView("dieu", "2", "Nguyên tắc", "", [k1, k2], "2016-07-01", None)


def test_md_thoat_ky_tu_dac_biet():
    assert md_thoat("giá $5 *rẻ* _x_ [a] <b> a|b") == "giá \\$5 \\*rẻ\\* \\_x\\_ \\[a\\] \\<b\\> a\\|b"
    assert md_thoat("# tiêu đề").startswith("\\#") and md_thoat("- gạch").startswith("\\-")
    assert md_thoat("đồng\\nữa") == "đồng\\\\nữa"


def test_markdown_dieu_khoan_la_doan_diem_la_gach_dau_dong_ghi_chu_dung_cho():
    md = markdown_dieu(dieu())
    assert md.startswith("**Điều 2. Nguyên tắc**")
    assert "**1.** Mọi hành vi bị xử lý như sau:\n\n- a) phạt cảnh cáo;\n- b) phạt tiền; :gray[*(" in md
    assert md.count(":gray[") == 2                                          # điểm b và khoản 2 bị sửa; điểm a và khoản 1 thì không
    assert ":gray[" not in markdown_dieu(dieu(), ghi_chu=False)


def test_ghi_chu_bo_qua_khi_cung_nguon_voi_nut_cha():
    con = UnitView("diem", "a", None, "x", [], "2018-01-01", None, [nguon()])
    assert ghi_chu_nguon(con, (1,)) == "" and "Luật số 12/2017/QH14" in ghi_chu_nguon(con, ())


def test_loc_khoan_diem_va_loi():
    d = dieu()
    u, pv, loi = loc_khoan(d, "2", None)
    assert (pv, loi) == ("khoản 2", None) and [c.ky_hieu for c in u.children] == ["2"] and u.noi_dung == ""
    u, pv, loi = loc_khoan(d, "1", "b")
    assert pv == "điểm b khoản 1" and [c.ky_hieu for c in u.children[0].children] == ["b"]
    assert loc_khoan(d, "9", None)[2] == "Điều 2 không có khoản 9 tại ngày này."
    assert "không có điểm z" in loc_khoan(d, "1", "z")[2]
    assert loc_khoan(d, None, None) == (d, "", None) and len(d.children) == 2          # không sửa đối tượng gốc


def test_cua_so_hieu_luc_lay_moc_gan_nhat_va_ket_thuc_som_nhat():
    assert cua_so_hieu_luc(dieu()) == ("2018-01-01", "2026-01-01")


def test_diff_html_to_tung_tu_trong_dong_va_dong_thay_the():
    html, doi = diff_html("Phạt tù từ 01 năm đến 03 năm.\nGiữ nguyên.", "Phạt tù từ 02 năm đến 03 năm.\nGiữ nguyên.")
    assert doi == 1 and html.count("<p ") == 2 and ">01<" in html and ">02<" in html and "line-through" in html
    assert "Giữ nguyên." in html and html.count("<span") == 2                          # chỉ hai chỗ tô màu: «01» bị bỏ, «02» được thêm
    html, doi = diff_html("A\nB", "A")
    assert doi == 1 and "line-through" in html
    html, doi = diff_html("", "Dòng mới")
    assert doi == 1 and "rgba(46,160,67" in html and "line-through" not in html
    assert diff_html("x", "x") == ('<p style="margin:0 0 .45rem 0;line-height:1.55">x</p>', 0)


def test_diff_html_hai_dong_qua_khac_nhau_thi_khong_xen_ke_tung_tu():
    html, doi = diff_html("Hoàn toàn khác biệt một câu dài như vậy", "Nội dung mới tinh chẳng liên quan gì")
    assert doi == 1 and html.count("<p ") == 2 and "line-through" in html


def test_diff_html_thoat_html():
    html, _ = diff_html("a <script>x</script>", "a")
    assert "<script>" not in html and "&lt;script&gt;" in html
