"""Luật sửa đổi viết theo lối cũ (vd Luật 37/2009/QH12 sửa BLHS 1999): lỗi gõ dấu ngoặc, khối trích dẫn thiếu dấu đóng, Điều hiệu lực
không có tiêu đề, câu lệnh dạng bị động / «tên Điều», mục đầu chỉ nêu mục đích, đích suy từ tên luật."""
import json

from src.extract.regex_extractor import extract_commands
from src.parse.amending import fix_stray_open_quotes, parse_amending_law, scan_structure
from src.validate.amending import has_errors, validate_amending_law

ALI = {"bộ luật hình sự": "100/2015/QH13"}
SCOPE = {"100/2015/QH13"}
HEADER = "QUỐC HỘI Số: 37/2009/QH12"
CAU_CHOT = "Luật này đã được Quốc hội nước Cộng hòa xã hội chủ nghĩa Việt Nam khóa XII, kỳ họp thứ 5 thông qua ngày 19 tháng 6 năm 2009."

LUAT_CU = [
    "LUẬT", "SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU CỦA BỘ LUẬT HÌNH SỰ", "Quốc hội ban hành Luật này.",
    "Điều 1. Sửa đổi, bổ sung, bãi bỏ một số điều của Bộ luật hình sự",
    "1. Bỏ hình phạt tử hình ở các điều 111 và 139.",
    "Sửa đổi cụm từ “hai mươi năm, tù chung thân hoặc tử hình” thành cụm từ “hai mươi năm hoặc tù chung thân” tại khoản 3 Điều 111, khoản 4 Điều 139.",
    "2. Sửa đổi mức định lượng như sau:",
    "a) Sửa đổi cụm từ “năm trăm nghìn đồng” thành cụm từ “hai triệu đồng” tại khoản 1 các điều 137, 138 và 139;",
    "b) Sửa đổi cụm từ “một triệu đồng” thành cụm từ “bốn triệu đồng” tại khoản 1 và bỏ từ “trên” tại điểm d khoản 2 Điều 140.",
    "3. Khoản 5 Điều 69 được sửa đổi, bổ sung như sau:",
    "“5. Nội dung khoản năm mới.”",
    "4. Tên Điều 84 được sửa đổi như sau:",
    "“Điều 84. Tội khủng bố nhằm chống chính quyền nhân dân”",
    "5. Bãi bỏ các điều 131, 183 và 199.",
    "Điều 2. Sửa đổi, bổ sung một số cụm từ tại khoản 1 Điều 313 như sau:",
    "1. Sửa đổi cụm từ “Điều 119, khoản 2 (tội mua bán phụ nữ)” thành cụm từ “Điều 119, khoản 2 (tội mua bán người)”;",
    "2. Bổ sung cụm từ “Điều 230a (tội khủng bố)” vào sau cụm từ “Điều 230 (tội chế tạo)”.",
    "Điều 3.", "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2010.", "________________", CAU_CHOT,
]


def parse(lines=LUAT_CU):
    return parse_amending_law(lines, HEADER, aliases=ALI, pham_vi_so_hieu=SCOPE)


# ---------- parser ----------

def test_dau_dong_go_nham_o_cho_mo_ngoac_duoc_doc_la_mo_ngoac_va_co_canh_bao():
    dong = "a) Sửa đổi cụm từ ”năm trăm nghìn đồng” thành cụm từ “hai triệu đồng” tại khoản 1 Điều 138;"
    out, warnings = fix_stray_open_quotes([dong, "Thay “a” bằng “b”."])
    assert out[0].startswith("a) Sửa đổi cụm từ “năm trăm nghìn đồng” thành") and out[1] == "Thay “a” bằng “b”."
    assert len(warnings) == 1 and "dòng 0" in warnings[0]


def test_khoi_trich_dan_thieu_dau_dong_duoc_dong_truoc_lenh_ke_tiep():
    lines = ["Điều 1. Sửa đổi một số điều của Bộ luật hình sự", "1. Sửa đổi Điều 3 như sau:", "“Điều 3. Nguyên tắc", "Nội dung ba.",
             "2. Bổ sung Điều 5a vào sau Điều 5 như sau:", "“Điều 5a. Mới", "Nội dung.”", "Điều 2. Hiệu lực thi hành"]
    dieus, blocks, warnings = scan_structure(lines)
    assert [d[1] for d in dieus] == ["1", "2"] and blocks == [(2, 3), (5, 6)]
    assert len(warnings) == 1 and "thiếu dấu ” đóng" in warnings[0] and "lệnh 2" in warnings[0]


def test_dong_nhac_lai_so_lenh_trong_khoi_khong_bi_cat_nham():
    lines = ["Điều 1. Sửa đổi", "1. Sửa đổi Điều 3 như sau:", "“Điều 3. Nguyên tắc", "2. Người phạm tội thì bị phạt tù.", "3. Mức phạt cao hơn.”"]
    _, blocks, warnings = scan_structure(lines)
    assert blocks == [(2, 4)] and not warnings          # «2.» trong khối không mở đầu bằng từ chỉ lệnh sửa đổi


def test_dieu_hieu_luc_khong_tieu_de_van_duoc_nhan_ra():
    law = parse()
    assert law.dieu_hieu_luc is not None and law.dieu_hieu_luc.ky_hieu == "3"
    assert (law.meta.so_hieu, law.meta.ngay_ban_hanh, law.meta.ngay_hieu_luc) == ("37/2009/QH12", "2009-06-19", "2010-01-01")
    assert not has_errors(validate_amending_law(law))


def test_tieu_de_chi_noi_dieu_cu_the_thi_van_ban_dich_la_luat_ma_ca_luat_sua():
    law = parse()
    assert [(d.ky_hieu, d.van_ban_dich_so_hieu, d.pham_vi) for d in law.dieu_sua_doi] == [("1", "100/2015/QH13", "trong"), ("2", "100/2015/QH13", "trong")]


def test_tieu_de_noi_ve_cac_luat_khac_khong_bi_gan_cho_luat_chinh():
    lines = list(LUAT_CU)
    i = lines.index("Điều 2. Sửa đổi, bổ sung một số cụm từ tại khoản 1 Điều 313 như sau:")
    lines[i] = "Điều 2. Sửa đổi, bổ sung một số điều của các luật có liên quan"
    d2 = parse(lines).dieu_sua_doi[1]
    assert (d2.van_ban_dich_so_hieu, d2.pham_vi) == (None, "khong_ro")


# ---------- bộ trích lệnh ----------

def test_trich_lenh_luat_cu_day_du_khong_bo_sot():
    r = extract_commands(parse())
    assert r.n_leaf == 8 and r.n_parsed_leaf == 8 and r.coverage() == 1.0 and not r.unparsed
    got = [(c.vi_tri_nguon, c.loai_thao_tac) for c in r.commands]
    assert got == [("Điều 1 khoản 1", "thay_cum_tu"), ("Điều 1 khoản 2 điểm a", "thay_cum_tu"), ("Điều 1 khoản 2 điểm b", "thay_cum_tu"),
                   ("Điều 1 khoản 2 điểm b", "thay_cum_tu"), ("Điều 1 khoản 3", "sua_doi"), ("Điều 1 khoản 4", "sua_doi"),
                   ("Điều 1 khoản 5", "bai_bo"), ("Điều 2 khoản 1", "thay_cum_tu"), ("Điều 2 khoản 2", "thay_cum_tu")]


def test_muc_dau_chi_neu_muc_dich_thi_lenh_lay_tu_cac_dong_sau():
    r = extract_commands(parse())
    c = r.commands[0]
    assert (c.cum_tu_cu, c.cum_tu_moi) == ("hai mươi năm, tù chung thân hoặc tử hình", "hai mươi năm hoặc tù chung thân")
    assert [t["duong_dan"] for t in c.dich["muc_tieu"]] == [[{"loai": "dieu", "ky_hieu": "111"}, {"loai": "khoan", "ky_hieu": "3"}],
                                                          [{"loai": "dieu", "ky_hieu": "139"}, {"loai": "khoan", "ky_hieu": "4"}]]
    assert any("câu nêu mục đích" in n for n in r.notes)          # bộ trích tự quyết điều này nên báo cho người duyệt


def test_khoan_dieu_duoc_sua_doi_dang_bi_dong_va_thanh_cum_tu():
    r = extract_commands(parse())
    a = r.commands[1]                                               # «thành cụm từ … tại khoản 1 các điều 137, 138 và 139»
    assert (a.cum_tu_cu, a.cum_tu_moi, a.dich["kieu"]) == ("năm trăm nghìn đồng", "hai triệu đồng", "thay")
    assert [t["duong_dan"][0]["ky_hieu"] for t in a.dich["muc_tieu"]] == ["137", "138", "139"]
    bi_dong = r.commands[4]                                         # «Khoản 5 Điều 69 được sửa đổi, bổ sung như sau:»
    assert bi_dong.dich["muc_tieu"][0]["duong_dan"] == [{"loai": "dieu", "ky_hieu": "69"}, {"loai": "khoan", "ky_hieu": "5"}]
    assert bi_dong.noi_dung_moi == "5. Nội dung khoản năm mới."


def test_mot_muc_hai_viec_cho_ra_hai_lenh_va_bo_tu_la_kieu_bo():
    thay, bo = extract_commands(parse()).commands[2:4]
    assert (thay.cum_tu_cu, thay.cum_tu_moi, thay.dich["kieu"]) == ("một triệu đồng", "bốn triệu đồng", "thay")
    assert (bo.cum_tu_cu, bo.cum_tu_moi, bo.dich["kieu"]) == ("trên", None, "bo")
    assert bo.dich["muc_tieu"][0]["duong_dan"] == [{"loai": "dieu", "ky_hieu": "140"}, {"loai": "khoan", "ky_hieu": "2"}, {"loai": "diem", "ky_hieu": "d"}]


def test_ten_dieu_chi_sua_tieu_de():
    c = extract_commands(parse()).commands[5]
    assert c.dich == {"muc_tieu": [{"duong_dan": [{"loai": "dieu", "ky_hieu": "84"}], "phan": "tieu_de"}]}
    assert c.noi_dung_moi.startswith("Điều 84. Tội khủng bố")


def test_muc_trong_dieu_tieu_de_nhac_dieu_cu_the_suy_ra_dich_tu_tieu_de():
    a, b = extract_commands(parse()).commands[-2:]
    for c in (a, b):
        assert c.dich["muc_tieu"] == [{"duong_dan": [{"loai": "dieu", "ky_hieu": "313"}, {"loai": "khoan", "ky_hieu": "1"}], "phan": "toan_bo"}]
    assert (a.dich["kieu"], b.dich["kieu"]) == ("thay", "chen_sau")
    assert (b.cum_tu_cu, b.cum_tu_moi) == ("Điều 230 (tội chế tạo)", "Điều 230a (tội khủng bố)")


def test_ket_qua_trich_lenh_ghi_duoc_ra_json():
    json.dumps(extract_commands(parse()).to_dict(), ensure_ascii=False)
