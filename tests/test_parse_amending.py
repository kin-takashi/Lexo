"""Parser + validator + stage cho luật sửa đổi: file tổng hợp, và 3 luật thật trong inbox/ nếu có."""
import json
from collections import Counter
from pathlib import Path

import pytest

from src.ingest.amending_law import load_amending, stage_amending_law
from src.ingest.base_law import IngestError
from src.ingest.docx_text import extract_docx
from src.parse.amending import AmendingLaw, parse_amending_law, resolve_target_law, scan_structure
from src.validate.amending import has_errors, validate_amending_law
from src.validate.base_law import CANH_BAO, LOI

from test_ingest_lookup import build_docx

ROOT = Path(__file__).resolve().parent.parent
ALI = {"bộ luật hình sự": "100/2015/QH13"}
SCOPE = {"100/2015/QH13"}

LINES = [
    "LUẬT", "SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU CỦA BỘ LUẬT HÌNH SỰ", "Căn cứ Hiến pháp;", "Quốc hội ban hành Luật này.",
    "Điều 1. Sửa đổi, bổ sung một số điều của Bộ luật Hình sự số 100/2015/QH13",
    "1. Sửa đổi, bổ sung Điều 3 như sau:",
    "“Điều 3. Nguyên tắc",
    "1. Mọi hành vi phải bị xử lý.",
    "2. Mức phạt tối thiểu như sau:",
    "a) mức một;",
    "b) mức hai.”",
    "2. Bổ sung Điều 5a vào sau Điều 5 như sau:",
    "“Điều 5a. Điều mới",
    "Nội dung điều mới.”",
    "3. Sửa đổi, bổ sung một số điểm của Điều 8 như sau:",
    "a) Sửa đổi điểm b khoản 1 như sau:",
    "“b) Nội dung điểm b;”",
    "b) Bãi bỏ khoản 3.",
    "4. Bãi bỏ Điều 10.",
    "5. Thay cụm từ “của Bộ luật Hình sự” bằng cụm từ “của Luật này” tại khoản 2 Điều 12.",
    "Điều 2. Sửa đổi, bổ sung một số điều của Luật Khác số 12/2010/QH12",
    "1. Sửa đổi Điều 1 như sau:",
    "“Điều 1. Điều của luật khác",
    "Nội dung.”",
    "Điều 3. Hiệu lực thi hành",
    "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2030.",
    "________________",
    "Luật này đã được Quốc hội nước Cộng hòa xã hội chủ nghĩa Việt Nam khóa XIV, kỳ họp thứ 3 thông qua ngày 20 tháng 6 năm 2017.",
]
HEADER = "QUỐC HỘI Số: 12/2017/QH14"


def parse(lines=LINES, **kw):
    return parse_amending_law(lines, HEADER, aliases=ALI, pham_vi_so_hieu=SCOPE, **kw)


def codes(flags, level=None):
    return [f.code for f in flags if level is None or f.level == level]


# ---------- tách cấu trúc ----------

def test_dieu_trong_khoi_trich_dan_khong_phai_dieu_cap_cao():
    dieus, blocks, warnings = scan_structure(LINES)
    assert [d[1] for d in dieus] == ["1", "2", "3"]          # Điều 3, 5a, 1 trong “ ” không được tính
    assert len(blocks) == 4 and not warnings


def test_meta():
    m = parse().meta
    assert (m.so_hieu, m.loai, m.ngay_ban_hanh, m.ngay_hieu_luc) == ("12/2017/QH14", "luat", "2017-06-20", "2030-01-01")
    assert m.ten_day_du == "Luật sửa đổi, bổ sung một số điều của bộ luật hình sự"
    assert m.hieu_luc_ngoai_le == []


def test_muc_va_khoi_trich_dan():
    law = parse()
    d1, d2 = law.dieu_sua_doi
    assert (d1.ky_hieu, d1.pham_vi, d2.pham_vi, d2.van_ban_dich_so_hieu) == ("1", "trong", "ngoai", "12/2010/QH12")
    assert [i.ky_hieu for i in d1.items] == ["1", "2", "3", "4", "5"]
    i1 = d1.items[0]
    assert i1.vi_tri_nguon == "Điều 1 khoản 1" and i1.quote_ids == ["Q1"]
    q = law.quote("Q1")
    assert q.text.startswith("Điều 3. Nguyên tắc\n1. Mọi hành vi") and q.text.endswith("b) mức hai.")
    assert "“" not in q.text and "”" not in q.text
    i3 = d1.items[2]
    assert [(c.id, c.vi_tri_nguon) for c in i3.children] == [("D1.3.a", "Điều 1 khoản 3 điểm a"), ("D1.3.b", "Điều 1 khoản 3 điểm b")]
    assert i3.children[0].quote_ids == ["Q3"] and law.quote("Q3").text == "b) Nội dung điểm b;"
    assert [q.id for q in law.quotes] == ["Q1", "Q2", "Q3", "Q4"]
    assert d2.items[0].quote_ids == ["Q4"] and d2.items[0].pham_vi == "ngoai"


def test_cum_tu_trong_ngoac_khong_lam_lech_van_ban_dich():
    ali = {"bộ luật hình sự": "100/2015/QH13"}
    t = "Thay cụm từ “của Bộ luật Hình sự” bằng cụm từ “của Luật này” tại khoản 2 Điều 12."
    assert resolve_target_law(t, ali) == (None, None)
    t2 = "Sửa đổi, bổ sung một số điều của Luật Phòng, chống mua bán người số 53/2024/QH15 như sau:"
    assert resolve_target_law(t2, ali) == ("53/2024/QH15", "Luật Phòng, chống mua bán người")
    t3 = "Sửa đổi khoản 1 Điều 5 của Bộ luật Hình sự số 100/2015/QH13 đã được sửa đổi theo Luật số 12/2017/QH14"
    assert resolve_target_law(t3, ali)[0] == "100/2015/QH13"                 # lần xuất hiện đầu


def test_muc_ke_thua_van_ban_dich_tu_dieu():
    item = parse().dieu_sua_doi[0].items[4]
    assert item.pham_vi == "trong"        # cụm từ trong “ ” chứa "Bộ luật Hình sự" nhưng đích vẫn là BLHS theo Điều 1


def test_dieu_hieu_luc_va_ngoai_le():
    lines = list(LINES)
    i = lines.index("Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2030.")
    lines[i:i + 1] = ["1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2030.",
                      "2. Điều 7 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2032."]
    law = parse(lines)
    assert law.meta.ngay_hieu_luc == "2030-01-01"
    assert law.meta.hieu_luc_ngoai_le == [{"cau": "2. Điều 7 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2032.", "ngay": "2032-01-01"}]
    assert "Hieu_luc_ngoai_le" in codes(validate_amending_law(law), CANH_BAO)


def test_dieu_sua_doi_chi_dinh_tay():
    law = parse(dieu_sua_doi=["2"])
    assert [d.ky_hieu for d in law.dieu_sua_doi] == ["2"]


def test_khong_co_loi_tren_van_ban_sach():
    flags = validate_amending_law(parse())
    assert not has_errors(flags), flags


# ---------- validator bắt lỗi ----------

def test_bat_thieu_khoi_trich_dan():
    lines = [l for l in LINES if l not in ("“Điều 5a. Điều mới", "Nội dung điều mới.”")]
    assert "Thieu_khoi_trich_dan" in codes(validate_amending_law(parse(lines)), LOI)


def test_bat_muc_nhay_so():
    lines = [l for l in LINES if not l.startswith("4. Bãi bỏ")]
    assert "Muc_nhay_so" in codes(validate_amending_law(parse(lines)), LOI)


def test_bat_dau_ngoac_khong_can_bang():
    lines = list(LINES)
    lines[lines.index("b) mức hai.”")] = "b) mức hai."          # quên đóng khối
    flags = validate_amending_law(parse(lines))
    assert any("không bao giờ đóng" in f.message or "không cân bằng" in f.message for f in flags)


def test_bat_thieu_ngay():
    lines = LINES[:-1]
    law = parse(lines)
    assert "Thieu_ngay_ban_hanh" in codes(validate_amending_law(law), LOI)


def test_khong_co_dieu_sua_doi():
    assert "Khong_co_dieu_sua_doi" in codes(validate_amending_law(parse(LINES, dieu_sua_doi=["99"])), LOI)


# ---------- tất định, ghi/đọc, stage ----------

def test_to_dict_from_dict_khu_hoi():
    law = parse()
    again = AmendingLaw.from_dict(json.loads(json.dumps(law.to_dict())))
    assert again.to_dict() == law.to_dict()
    with pytest.raises(ValueError):
        AmendingLaw.from_dict({"format_version": 99})


def test_stage_ghi_amending_json_tat_dinh(tmp_path):
    src = build_docx(tmp_path / "LSD.docx", LINES, so_hieu="12/2017/QH14")
    a = stage_amending_law(src, tmp_path / "raw", aliases=ALI, pham_vi_so_hieu=SCOPE)
    b = stage_amending_law(src, tmp_path / "raw", aliases=ALI, pham_vi_so_hieu=SCOPE)
    assert a.sha256 == b.sha256 and a.directory.name == "12-2017-QH14"
    assert not has_errors(a.flags)
    assert load_amending(a.amending_path).to_dict() == a.law.to_dict()
    assert (a.directory / "LSD.docx").exists()


def test_stage_khong_ghi_de_file_goc_khac(tmp_path):
    src = build_docx(tmp_path / "LSD.docx", LINES, so_hieu="12/2017/QH14")
    stage_amending_law(src, tmp_path / "raw", aliases=ALI, pham_vi_so_hieu=SCOPE)
    (tmp_path / "other").mkdir()
    other = build_docx(tmp_path / "other" / "LSD.docx", LINES + ["thêm"], so_hieu="12/2017/QH14")
    with pytest.raises(IngestError):
        stage_amending_law(other, tmp_path / "raw", aliases=ALI, pham_vi_so_hieu=SCOPE)


# ---------- ba luật thật (chỉ chạy khi có trong inbox/) ----------

REAL = {
    "12/2017/QH14": ROOT / "inbox" / "Luật-12-2017-QH14.docx",
    "86/2025/QH15": ROOT / "inbox" / "86_2025_QH15_662377.docx",
    "59/2024/QH15": ROOT / "inbox" / "59_2024_QH15_606865.docx",
}


@pytest.fixture(scope="module")
def real_laws(tmp_path_factory):
    if not all(p.exists() for p in REAL.values()):
        pytest.skip("thiếu file luật sửa đổi trong inbox/")
    tmp = tmp_path_factory.mktemp("amend")
    return {k: stage_amending_law(p, tmp / "raw", aliases=ALI, pham_vi_so_hieu=SCOPE) for k, p in REAL.items()}


def test_real_khong_co_loi_cau_truc(real_laws):
    for so, st in real_laws.items():
        assert not has_errors(st.flags), (so, [f for f in st.flags if f.level == LOI][:3])


def test_real_12_2017(real_laws):
    law = real_laws["12/2017/QH14"].law
    assert (law.meta.ngay_ban_hanh, law.meta.ngay_hieu_luc) == ("2017-06-20", "2018-01-01")
    assert [d.ky_hieu for d in law.dieu_sua_doi] == ["1", "2"]
    d1, d2 = law.dieu_sua_doi
    assert len(d1.items) == 141 and sum(len(i.children) for i in d1.items) == 53
    assert len(law.quotes) == 167
    assert all(i.pham_vi == "trong" for _, i in law.iter_items())
    # mọi khối trích dẫn đều có chủ, không khối nào bị dùng hai lần
    owned = Counter(q for _, i in law.iter_items() for q in i.quote_ids)
    assert set(owned) == {q.id for q in law.quotes} and set(owned.values()) == {1}
    # Điều 2 là các lệnh thay/bỏ cụm từ nhiều thao tác, không có khối trích dẫn
    assert len(d2.items) == 3 and sum(len(i.children) for i in d2.items) == 52 and not any(i.quote_ids for i in d2.walk_items())


def test_real_86_2025(real_laws):
    law = real_laws["86/2025/QH15"].law
    assert (law.meta.ngay_ban_hanh, law.meta.ngay_hieu_luc, law.meta.ngay_header) == ("2025-06-25", "2025-07-01", "2025-06-25")
    d1, d2 = law.dieu_sua_doi
    assert d1.pham_vi == "trong" and len(d1.items) == 29
    assert d2.pham_vi == "khong_ro" or all(i.pham_vi == "ngoai" for i in d2.walk_items() if i.cap == 1)
    assert not any(i.pham_vi in ("khong_ro",) for _, i in law.iter_items())
    assert law.dieu_chuyen_tiep is not None


def test_real_59_2024_chi_hai_lenh_vao_blhs(real_laws):
    law = real_laws["59/2024/QH15"].law
    (d177,) = law.dieu_sua_doi
    assert d177.ky_hieu == "177"
    trong = [i for i in d177.walk_items() if i.pham_vi == "trong"]
    assert [i.id for i in trong] == ["D177.1", "D177.1.a", "D177.1.b"]
    assert [i.text for i in trong[1:]] == ["Bãi bỏ chương XII;", "Bỏ từ “tư pháp” tại điểm g khoản 1 Điều 134."]
    assert law.meta.hieu_luc_ngoai_le and law.meta.hieu_luc_ngoai_le[0]["ngay"] == "2028-01-01"
    # cụm từ trong ngoặc ở khoản 2 điểm đ có chữ "Bộ luật Hình sự" nhưng lệnh đó nhắm BLTTHS
    assert next(i for i in d177.walk_items() if i.id == "D177.2.đ").pham_vi == "ngoai"
