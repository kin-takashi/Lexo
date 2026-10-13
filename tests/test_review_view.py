"""Hàm thuần của giao diện duyệt."""
from src.parse.base_law import parse_base_law
from src.review.base_law_view import dieu_at_line, dieu_matches_source, dieu_spans, node_to_text, path_to, sample_dieu

LINES = [
    "BỘ LUẬT", "THỬ NGHIỆM",
    "Chương I", "MỘT",
    "Điều 1. A", "1. Câu dẫn:", "a) x;", "b) y; c) z.",
    "Chương II", "HAI",
    "Điều 2. B", "Nội dung B.",
    "Điều 3. Hiệu lực", "Có hiệu lực từ ngày 01 tháng 7 năm 2099.",
    "________________",
    "Bộ luật này đã được Quốc hội thông qua ngày 27 tháng 11 năm 2098.",
]


def law():
    return parse_base_law(LINES, "Số: 1/2098/QH99")


def test_spans_stop_before_next_chuong_title():
    spans = dieu_spans(law())
    assert [(d.ky_hieu, a, b) for d, a, b in spans] == [("1", 4, 8), ("2", 10, 12), ("3", 12, 14)]


def test_node_to_text_matches_source_including_split_points():
    lw = law()
    for node, a, b in dieu_spans(lw):
        assert dieu_matches_source(lw, node, a, b), node.ky_hieu


def test_mismatch_is_detected():
    lw = law()
    node, a, b = dieu_spans(lw)[1]
    node.noi_dung += " bị sửa"
    assert not dieu_matches_source(lw, node, a, b)


def test_dieu_at_line_and_path():
    lw = law()
    node, _, _ = dieu_at_line(lw, 6)
    assert node.ky_hieu == "1"
    assert dieu_at_line(lw, 8) is None                # dòng "Chương II" không thuộc Điều nào
    assert [n.ky_hieu for n in path_to(lw, node)] == ["I"]
    assert "b) y;" in node_to_text(node) and "c) z." in node_to_text(node)


def test_sample_is_stable_ordered_and_capped():
    lw = law()
    assert sample_dieu(lw) == ["1", "2", "3"]         # ít hơn 30 Điều: lấy hết
    assert sample_dieu(lw, n=2) == sample_dieu(lw, n=2)
    assert len(sample_dieu(lw, n=2)) == 2
