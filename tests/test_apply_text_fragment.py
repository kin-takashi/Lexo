"""Hàm thuần: thao tác cụm từ và parse khối trích dẫn."""
import pytest

from src.apply.text_ops import apply_phrase
from src.parse.fragment import locate, parse_fragment


def test_thay_ca_cum_khong_thay_giua_tu():
    assert apply_phrase("tù trưởng và tù", "thay", "tù", "giam") == ("giam trưởng và giam", 2)
    assert apply_phrase("tùy nghi", "thay", "tù", "giam") == ("tùy nghi", 0)


def test_bo_cum_gon_khoang_trang():
    assert apply_phrase("hoạt động tư pháp của người", "bo", "tư pháp", None) == ("hoạt động của người", 1)
    assert apply_phrase("hoạt động tư pháp, của", "bo", "tư pháp", None) == ("hoạt động, của", 1)
    assert apply_phrase("tư pháp của người", "bo", "tư pháp", None) == ("của người", 1)
    assert apply_phrase("Cơ quan điều tra, thanh tra và tòa", "bo", ", thanh tra", None) == ("Cơ quan điều tra và tòa", 1)


def test_chen_cum():
    assert apply_phrase("kiểm sát viên", "chen_sau", "kiểm sát", "hoặc điều tra") == ("kiểm sát hoặc điều tra viên", 1)
    assert apply_phrase("kiểm sát viên", "chen_sau", "kiểm sát", ", thanh tra") == ("kiểm sát, thanh tra viên", 1)
    assert apply_phrase("Viện kiểm sát", "chen_truoc", "kiểm sát", "điều tra,") == ("Viện điều tra, kiểm sát", 1)
    assert apply_phrase("Người phạm tội", "chen_cuoi", None, "và đồng phạm") == ("Người phạm tội và đồng phạm", 1)
    assert apply_phrase("Người phạm tội", "chen_dau", None, "Mọi") == ("Mọi Người phạm tội", 1)


def test_khong_thay_thi_dem_bang_0_va_kieu_sai():
    assert apply_phrase("abc", "thay", "xyz", "q") == ("abc", 0)
    with pytest.raises(ValueError):
        apply_phrase("abc", "doi", "a", "b")
    with pytest.raises(ValueError):
        apply_phrase("abc", "thay", None, "b")


# ---------- khối trích dẫn ----------

def test_fragment_ca_dieu():
    f = parse_fragment("Điều 3. Nguyên tắc\nMở đầu.\n1. Khoản một:\na) điểm a;\nb) điểm b.\n2. Khoản hai.")
    (d,) = f.nodes
    assert (d.loai, d.ky_hieu, d.tieu_de, d.noi_dung) == ("dieu", "3", "Nguyên tắc", "Mở đầu.")
    assert [(c.ky_hieu, c.noi_dung) for c in d.children] == [("1", "Khoản một:"), ("2", "Khoản hai.")]
    assert [c.ky_hieu for c in d.children[0].children] == ["a", "b"]


def test_fragment_chi_khoan_va_chi_diem_khong_can_dieu_bao_quanh():
    f = parse_fragment("2. Khoản hai:\na) x;\nb) y.")
    assert [n.loai for n in f.nodes] == ["khoan"] and [c.ky_hieu for c in f.nodes[0].children] == ["a", "b"]
    g = parse_fragment("b) Nội dung điểm b;")
    assert [(n.loai, n.ky_hieu, n.noi_dung) for n in g.nodes] == [("diem", "b", "Nội dung điểm b;")]
    h = parse_fragment("3. Nhiều khoản\n3a. Khoản 3a\n4. Khoản 4")
    assert [n.ky_hieu for n in h.nodes] == ["3", "3a", "4"]


def test_fragment_tach_diem_gop_cung_dong():
    f = parse_fragment("1. Khoản:\na) một; b) hai; c) ba.")
    assert [c.ky_hieu for c in f.nodes[0].children] == ["a", "b", "c"]


def test_fragment_so_tien_khong_bi_nhan_la_khoan():
    f = parse_fragment("1. Phạt tiền\n2.000.000 đồng trở lên.")
    assert [n.ky_hieu for n in f.nodes] == ["1"] and "2.000.000" in f.nodes[0].noi_dung


def test_fragment_doan_khong_ky_hieu_vao_preamble():
    f = parse_fragment("Chỉ là một đoạn văn.")
    assert f.nodes == [] and f.preamble == ["Chỉ là một đoạn văn."]


def test_locate_theo_hau_to_duong_dan():
    f = parse_fragment("Điều 5. T\n1. A\n2. B:\na) x")
    assert locate(f.nodes, [("dieu", "5"), ("khoan", "2"), ("diem", "a")]).ky_hieu == "a"
    assert locate(f.nodes, [("dieu", "5")]).loai == "dieu"
    g = parse_fragment("2. B:\na) x")                                 # khối chỉ chứa khoản
    assert locate(g.nodes, [("dieu", "5"), ("khoan", "2")]).ky_hieu == "2"
    assert locate(g.nodes, [("dieu", "5"), ("khoan", "3")]) is None


def test_cum_o_dau_van_ban_viet_hoa_chu_dau_van_ap_duoc():
    # luật dẫn "gây thiệt hại về tài sản" giữa câu, nhưng điểm d bắt đầu bằng "Gây ..."
    assert apply_phrase("Gây thiệt hại về tài sản từ 300 đồng.", "thay", "gây thiệt hại về tài sản", "gây thất thoát, lãng phí") == \
        ("Gây thất thoát, lãng phí từ 300 đồng.", 1)
    assert apply_phrase("Người phạm tội", "chen_sau", "người", "nào") == ("Người nào phạm tội", 1)
    assert apply_phrase("Người phạm tội", "chen_truoc", "người", "mọi") == ("Mọi người phạm tội", 1)
    assert apply_phrase("Các cơ quan tiến hành", "bo", "các", None) == ("Cơ quan tiến hành", 1)
    # có chỗ khớp nguyên dạng thì không dùng phương án viết hoa
    assert apply_phrase("Gây hại; gây hại", "thay", "gây hại", "làm hại") == ("Gây hại; làm hại", 1)
    assert apply_phrase("Gây hại", "thay", "gây hạ", "x") == ("Gây hại", 0)
