"""Parser + validator văn bản gốc trên dữ liệu tổng hợp (luật 'BỘ LUẬT THỬ NGHIỆM'), không phụ thuộc file thật."""
import re

import pytest

from src.parse.base_law import parse_base_law
from src.parse.model import ParsedLaw
from src.parse.text import count_homoglyphs, normalize_text, parse_vn_date
from src.validate.base_law import CANH_BAO, LOI, roman_to_int, validate_base_law

HEAD = ["BỘ LUẬT", "THỬ NGHIỆM", "Căn cứ Hiến pháp;", "Quốc hội ban hành Bộ luật thử nghiệm."]
CLOSING = [
    "________________",
    "Bộ luật này đã được Quốc hội nước Cộng hòa xã hội chủ nghĩa Việt Nam khóa XIII, kỳ họp thứ 10 "
    "thông qua ngày 27 tháng 11 năm 2098.",
]
HIEU_LUC = ["Điều {n}. Hiệu lực thi hành", "Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2099."]


def make(body, *, header="Số: 99/2098/QH99", head=HEAD, tail=None, **kw):
    """Ghép đầu + thân + Điều hiệu lực (đánh số tiếp theo Điều cuối của thân, để không gây nhảy số) + chân văn bản."""
    body = list(body)
    if tail is None:
        last = max((int(m.group(1)) for line in body if (m := re.match(r"^Điều (\d+)", line))), default=0)
        tail = [HIEU_LUC[0].format(n=last + 1), HIEU_LUC[1]] + CLOSING
    return parse_base_law(head + body + list(tail), header, **kw)


def codes(law, level=None):
    return [f.code for f in validate_base_law(law) if level is None or f.level == level]


GOOD_BODY = [
    "Phần thứ nhất",
    "NHỮNG QUY ĐỊNH CHUNG",
    "Chương I",
    "ĐIỀU KHOẢN CHUNG",
    "Điều 1. Phạm vi điều chỉnh",
    "Bộ luật này quy định về tội phạm.",
    "Điều 2. Nguyên tắc",
    "1. Nguyên tắc như sau:",
    "a) tuân thủ pháp luật;",
    "b) bảo vệ quyền con người.",
    "2. Mức phạt tối thiểu:",
    "2.000.000 đồng đối với cá nhân.",
    "Điều 2a. Điều bổ sung theo kiểu có chữ",
    "Nội dung không chia khoản.",
    "Chương II",
    "TIÊU ĐỀ RẤT DÀI",
    "CHIA LÀM HAI DÒNG",
    "Mục 1",
    "MỤC MỘT",
    "Điều 3. Điều trong mục",
    "1. Khoản duy nhất.",
    "Phần thứ hai",
    "PHẦN HAI",
]


def test_structure_keys_titles_nesting():
    law = make(GOOD_BODY[:-2] + ["Điều 4. Điều tiếp", "1. Một."])
    assert [r.loai for r in law.roots] == ["phan"]
    phan = law.roots[0]
    assert (phan.ky_hieu, phan.tieu_de) == ("thứ nhất", "NHỮNG QUY ĐỊNH CHUNG")
    ch1, ch2 = phan.children
    assert (ch1.loai, ch1.ky_hieu, ch1.tieu_de) == ("chuong", "I", "ĐIỀU KHOẢN CHUNG")
    assert ch2.tieu_de == "TIÊU ĐỀ RẤT DÀI CHIA LÀM HAI DÒNG"
    assert [(d.loai, d.ky_hieu) for d in ch1.children] == [("dieu", "1"), ("dieu", "2"), ("dieu", "2a")]
    muc = ch2.children[0]
    assert (muc.loai, muc.ky_hieu, muc.tieu_de) == ("muc", "1", "MỤC MỘT")
    assert [d.ky_hieu for d in muc.children] == ["3", "4", "5"]    # 5 = Điều hiệu lực do make() thêm


def test_khoan_diem_and_continuation():
    law = make(GOOD_BODY[:-2])
    dieu2 = [n for n in law.iter_nodes() if n.loai == "dieu" and n.ky_hieu == "2"][0]
    k1, k2 = dieu2.children
    assert k1.noi_dung == "Nguyên tắc như sau:"
    assert [(d.ky_hieu, d.noi_dung) for d in k1.children] == [("a", "tuân thủ pháp luật;"), ("b", "bảo vệ quyền con người.")]
    # dòng "2.000.000 đồng ..." KHÔNG được coi là khoản, mà là đoạn nối tiếp của khoản 2
    assert k2.noi_dung == "Mức phạt tối thiểu:\n2.000.000 đồng đối với cá nhân."
    assert k2.children == []
    dieu1 = [n for n in law.iter_nodes() if n.loai == "dieu" and n.ky_hieu == "1"][0]
    assert dieu1.noi_dung == "Bộ luật này quy định về tội phạm."


def test_khoan_outside_dieu_is_not_khoan_and_warns():
    law = make(["Chương I", "TIÊU ĐỀ", "1. Dòng lạc khỏi Điều nào", "Điều 1. A", "Nội dung."])
    assert not any(n.loai == "khoan" for n in law.iter_nodes())
    assert any("ngoài Điều" in w for w in law.warnings)
    assert "canh_bao_parse" in codes(law, CANH_BAO)


def test_inline_merged_points_are_split_only_for_next_letter():
    law = make([
        "Điều 1. A",
        "1. Câu dẫn:",
        "a) một;",
        "b) hai; c) ba; d) bốn;",
        "đ) năm, xem điểm c) khoản 1 Điều này; điểm d) khoản 2.",
    ])
    khoan = [n for n in law.iter_nodes() if n.loai == "khoan"][0]
    assert [d.ky_hieu for d in khoan.children] == ["a", "b", "c", "d", "đ"]
    assert khoan.children[1].noi_dung == "hai;"
    assert khoan.children[3].noi_dung == "bốn;"
    # dẫn chiếu "điểm c)" / "điểm d)" trong câu không bị tách
    assert "xem điểm c) khoản 1 Điều này; điểm d) khoản 2." in khoan.children[4].noi_dung
    assert sum("tách điểm" in w for w in law.warnings) == 2
    assert LOI not in [f.level for f in validate_base_law(law)]


def test_meta_extraction():
    law = make(GOOD_BODY[:-2], ten_viet_tat="blts")
    m = law.meta
    assert (m.so_hieu, m.loai, m.ten_day_du) == ("99/2098/QH99", "bo_luat", "Bộ luật thử nghiệm")
    assert m.ten_viet_tat == "BLTS"
    assert m.ngay_ban_hanh == "2098-11-27"
    assert m.ngay_hieu_luc == "2099-07-01"
    assert law.footer[-1].startswith("Bộ luật này đã được Quốc hội")
    # dòng kẻ ngang ngay trước câu chốt thuộc chân văn bản, không lọt vào Điều cuối
    last = [n for n in law.iter_nodes() if n.loai == "dieu"][-1]
    assert "____" not in last.full_text()


def test_viet_tat_default_from_first_two_lines():
    assert make(GOOD_BODY[:-2]).meta.ten_viet_tat == "BLTN"


def test_missing_metadata_flags():
    law = parse_base_law(["Điều 1. A", "Nội dung."], "")
    got = codes(law, LOI)
    assert {"thieu_so_hieu", "thieu_ten", "thieu_ngay_ban_hanh", "thieu_ngay_hieu_luc"} <= set(got)


def test_impossible_effective_date_is_not_read():
    law = make(GOOD_BODY[:-2], tail=["Điều 4. Hiệu lực thi hành", "Có hiệu lực từ ngày 30 tháng 2 năm 2099."] + CLOSING)
    assert law.meta.ngay_hieu_luc is None
    assert "thieu_ngay_hieu_luc" in codes(law, LOI)


def test_clean_law_has_no_errors_or_warnings():
    law = make(GOOD_BODY[:-2])
    bad = [f for f in validate_base_law(law) if f.level in (LOI, CANH_BAO)]
    assert bad == []


# ---------- validator: phát hiện thiếu/nhảy/trùng ----------

def test_validator_dieu_gap_and_duplicate():
    law = make(["Điều 1. A", "Nội dung.", "Điều 3. C", "Nội dung.", "Điều 3. C lặp", "Nội dung."], tail=CLOSING)
    got = codes(law, LOI)
    assert "Điều_nhay_so" in got and "Điều_trung" in got


def test_validator_dieu_suffix_sequence_ok_and_bad():
    ok = make(["Điều 1. A", "x.", "Điều 1a. B", "x.", "Điều 1b. C", "x.", "Điều 2. D", "x."], tail=CLOSING)
    assert "Điều_nhay_so" not in codes(ok)
    bad = make(["Điều 1. A", "x.", "Điều 1c. B", "x."], tail=CLOSING)     # thiếu 1a, 1b
    assert "Điều_nhay_so" in codes(bad)
    skip_d = make(["Điều 1. A", "x.", "Điều 1d. B", "x."], tail=CLOSING)
    assert "Điều_nhay_so" in codes(skip_d)


def test_validator_khoan_start_and_gap():
    law = make(["Điều 1. A", "2. Bắt đầu từ hai.", "4. Nhảy."], tail=CLOSING)
    got = codes(law, LOI)
    assert "khoản_khong_bat_dau_tu_1" in got and "khoản_nhay_so" in got


def test_validator_points_use_vietnamese_alphabet():
    ok = make(["Điều 1. A", "1. Dẫn:", "a) 1;", "b) 2;", "c) 3;", "d) 4;", "đ) 5;", "e) 6."], tail=CLOSING)
    assert "diem_sai_thu_tu" not in codes(ok)
    bad = make(["Điều 1. A", "1. Dẫn:", "a) 1;", "b) 2;", "d) 4."], tail=CLOSING)
    assert "diem_sai_thu_tu" in codes(bad)
    src_typo = make(["Điều 1. A", "1. Dẫn:", "c) 3;", "d) 4;", "e) 6."], tail=CLOSING)   # thiếu đ) như file thật
    assert "diem_sai_thu_tu" in codes(src_typo)


def test_validator_chuong_muc_sequence():
    law = make(["Chương I", "A", "Chương III", "B", "Điều 1. X", "y."], tail=CLOSING)
    assert "Chương_nhay_so" in codes(law, LOI)
    law2 = make(["Chương I", "A", "Mục 2", "M", "Điều 1. X", "y."], tail=CLOSING)
    assert "Mục_khong_bat_dau_tu_1" in codes(law2, LOI)


def test_validator_empty_dieu_and_missing_title():
    law = make(["Điều 1.", "Điều 2. Có tiêu đề", "x."], tail=CLOSING)
    assert "dieu_rong" in codes(law, LOI)
    assert "dieu_thieu_tieu_de" in codes(law, CANH_BAO)


def test_validator_effective_before_promulgation():
    tail = ["Điều 99. Hiệu lực", "Bộ luật này có hiệu lực từ ngày 01 tháng 1 năm 2000."] + CLOSING
    assert "hieu_luc_truoc_ban_hanh" in codes(make(["Điều 1. A", "x."], tail=tail), LOI)


def test_roman_to_int():
    assert [roman_to_int(x) for x in ("I", "IV", "IX", "XIX", "XXVI", "XL", "Z")] == [1, 4, 9, 19, 26, 40, None]


# ---------- chuẩn hoá văn bản ----------

def test_homoglyph_normalization():
    raw = "\u00d0i\u1ec1u 317. \u00f0\u1ed1i v\u1edbi"      # "Ðiều 317. ðối với" với Ð/ð là Latin Eth
    assert count_homoglyphs(raw) == 2
    fixed = normalize_text(raw)
    assert fixed == "Điều 317. đối với" and count_homoglyphs(fixed) == 0


def test_normalize_whitespace_and_soft_breaks():
    assert normalize_text("  A \u00a0 B\tC\nD  \u200b") == "A B C D"


def test_parse_vn_date():
    assert parse_vn_date("thông qua ngày 27 tháng 11 năm 2015.") == "2015-11-27"
    assert parse_vn_date("ngày 30 tháng 2 năm 2015") is None
    assert parse_vn_date("không có ngày") is None


def test_roundtrip_dict():
    law = make(GOOD_BODY[:-2], source={"name": "x.docx"})
    again = ParsedLaw.from_dict(law.to_dict())
    assert again.to_dict() == law.to_dict()


def test_roundtrip_rejects_unknown_format():
    d = make(GOOD_BODY[:-2]).to_dict()
    d["format_version"] = 999
    with pytest.raises(ValueError):
        ParsedLaw.from_dict(d)
