"""Đối chiếu với văn bản hợp nhất (src/validate/vbhn.py): fold, đề xuất sửa chữ, so sánh nút. Văn bản trong test là giả lập."""
import json

import pytest

from src.parse.base_law import parse_body
from src.validate.vbhn import (
    Item, ap_dung_sua, compare, de_xuat_sua, fold, items_from_nodes, key_of, lap_de_xuat, nap_vbhn_json,
)

# ---------- fold ----------


def test_fold_bo_khac_biet_trinh_bay():
    assert fold("Hoà giải, Thuỷ lợi; Sỹ quan hàng tháng 07 người.") == fold("hòa giải thủy lợi sĩ quan hằng tháng 7 người")
    assert fold("Bộ luật  hình sự") == fold("bộ luật hình sự.") == fold("Bộ Luật Hình Sự")


@pytest.mark.parametrize("a,b", [
    ("phạt tiền dưới 100.000.000 đồng", "phạt tiền dưới 500.000.000 đồng"),    # chữ số không bao giờ bị bỏ qua
    ("0,05", "5"),                                                             # số 0 đầu số thập phân giữ nguyên
    ("phạt tù từ 01 năm", "phạt tù từ 10 năm"),
    ("người phạm tội", "người phạm tội bị"),                                   # từ thừa/thiếu
    ("quyền dụng đất", "quyền sử dụng đất"),
])
def test_fold_khong_bo_chu_so_hay_tu(a, b):
    assert fold(a) != fold(b)


def test_fold_none_va_rong():
    assert fold(None) == fold("") == ""


# ---------- de_xuat_sua ----------


def apply_all(text, edits):
    for e in edits:
        text = ap_dung_sua(text, e.tu_cu, e.thanh_moi)
        assert text is not None
    return text


@pytest.mark.parametrize("ours,theirs,loai,da_xoa,da_them", [
    ("chiếm đoạt quyền dụng đất của người khác.", "chiếm đoạt quyền sử dụng đất của người khác.", "loi_go", "", "sử"),
    ("bị phạt liền từ 10.000.000 đồng đến 20.000.000 đồng.", "bị phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng.", "loi_go", "liền", "tiền"),
    ("thì bị phạt tiền.", "thì bị bị phạt tiền.", "loi_go", "", "bị"),                    # chỗ thiếu một từ lặp
    ("phạm tội đối với d, d khoản này", "phạm tội đối với d, khoản này", "loi_go", "d", ""),   # bên ta thừa chữ
    ("phạt tiền dưới 100.000.000 đồng nhưng", "phạt tiền dưới 500.000.000 đồng nhưng", "sai_so_lieu", "100.000.000", "500.000.000"),
    ("người bị kết án đã chấp hành hình phạt.", "người bị kết án đã chấp hành xong hình phạt.", "loi_go", "", "xong"),
])
def test_de_xuat_sua_mot_cho(ours, theirs, loai, da_xoa, da_them):
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and len(edits) == 1
    e = edits[0]
    assert (e.loai, e.da_xoa, e.da_them) == (loai, da_xoa, da_them)
    assert ours.count(e.tu_cu) == 1
    assert apply_all(ours, edits) == theirs                                  # áp lên bản ta ra đúng từng chữ


def test_de_xuat_sua_chi_khac_trinh_bay_thi_khong_sua():
    edits, ok = de_xuat_sua("Người nào hoà giải, sỹ quan hàng tháng 07 người.", "người nào hòa giải sĩ quan hằng tháng 7 người")
    assert ok and edits == []


def test_de_xuat_sua_giu_trinh_bay_cua_ban_ta_o_cho_khong_sai():
    ours = "Sỹ quan thuỷ binh bị phạt liền từ 05 năm."
    theirs = "Sĩ quan thủy binh bị phạt tiền từ 5 năm."
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and len(edits) == 1 and edits[0].da_them == "tiền"
    out = apply_all(ours, edits)
    assert out.startswith("Sỹ quan thuỷ binh") and out.endswith("từ 05 năm.")      # phần không sai giữ nguyên như bản ta


def test_de_xuat_sua_chen_truoc_dau_cau():
    ours = "Điều này quy định tội phạm. Ngày hôm đó là ngày lễ."
    theirs = "Điều này quy định tội phạm bị. Ngày hôm đó là ngày lễ."
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and apply_all(ours, edits) == theirs                           # từ chèn nằm trước dấu chấm như văn bản hợp nhất


def test_de_xuat_sua_chen_sau_dau_cau_va_viet_hoa_tu_sau():
    ours, theirs = "A. Ngày hôm đó là ngày lễ.", "A. Quy định Ngày hôm đó là ngày lễ."
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and apply_all(ours, edits) == theirs
    ours, theirs = "Mức phạt. Ngày hôm", "Mức phạt. Mới ngày hôm"                # từ đứng sau chỗ chèn lấy cách viết của văn bản hợp nhất
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and apply_all(ours, edits) == theirs


def test_de_xuat_sua_chen_cuoi_van_truoc_dau_cau_ket_thuc():
    ours, theirs = "bị phạt tù;", "bị phạt tù chung thân;"
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and apply_all(ours, edits) == theirs


def test_de_xuat_sua_nhieu_cho_tach_rieng():
    ours = "Người nào quyền dụng đất của người khác, gây thiệt hại lớn, thì bị phạt liền từ năm."
    theirs = "Người nào quyền sử dụng đất của người khác, gây thiệt hại lớn, thì bị phạt tiền từ năm."
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and len(edits) == 2 and apply_all(ours, edits) == theirs
    assert all(ours.count(e.tu_cu) == 1 for e in edits)                      # mỗi sửa đủ ngữ cảnh để chỉ một chỗ khớp


def test_de_xuat_sua_nhieu_chu_khi_lech_nhieu_tu():
    ours = "bị phạt tù từ 01 năm đến 03 năm."
    theirs = "bị phạt tù từ 01 năm đến 03 năm hoặc cải tạo không giam giữ."
    edits, ok = de_xuat_sua(ours, theirs)
    assert ok and edits[0].loai == "nhieu_chu" and apply_all(ours, edits) == theirs


def test_de_xuat_sua_khong_co_diem_tua_thi_khong_doan():
    assert de_xuat_sua("", "một đoạn mới") == ([], False)                    # bên ta không có chữ nào
    assert de_xuat_sua("một đoạn cũ", "") == ([], False)
    # đoạn lặp: không ngữ cảnh nào đủ ngắn để chỉ một chỗ khớp -> không kiểm chứng được, không tự đoán
    assert de_xuat_sua("nhà nước nhà nước nhà nước", "nhà nước nhà nước nhà nước nhà nước", ngu_canh_toi_da=1) == ([], False)


def test_ap_dung_sua_mo_ho_hoac_khong_co():
    assert ap_dung_sua("a b a", "a", "c") is None            # hai chỗ -> mơ hồ
    assert ap_dung_sua("a b", "x", "c") is None              # không có
    assert ap_dung_sua("a b", "b", "c") == "a c"


# ---------- items_from_nodes / compare ----------

BODY = [
    "Chương I", "ĐIỀU KHOẢN CHUNG",
    "Điều 1. Phạm vi",
    "Bộ luật này quy định về tội phạm.",
    "Điều 2. Nguyên tắc",
    "1. Mọi hành vi vi phạm bị xử lý như sau:",
    "a) phạt cảnh cáo;",
    "b) phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng.",
    "2. Người phạm tội tự thú được giảm nhẹ.",
    "Chương II", "CÁC TỘI DANH",
    "Điều 3. Tội trộm cắp",
    "Người nào trộm cắp tài sản thì bị phạt tù.",
    "Điều 4. (được bãi bỏ)",
]


def nodes(lines):
    roots, _pre, _warn = parse_body(lines)
    return items_from_nodes(roots)


def test_items_from_nodes_khoa_va_bai_bo():
    items, repealed = nodes(BODY)
    assert {"chuong I", "chuong II", "dieu 1", "dieu 2", "dieu 2/khoan 1", "dieu 2/khoan 1/diem a", "dieu 2/khoan 2", "dieu 3"} <= set(items)
    assert "dieu 4" not in items and repealed == ["dieu 4"]                  # "(được bãi bỏ)" coi như không có nút
    assert items["dieu 2/khoan 1/diem b"].noi_dung == "phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng."
    assert items["dieu 3"].cha == "chuong II" and items["dieu 1"].cha == "chuong I"
    assert key_of("dieu", "2", "chuong I") == "dieu 2" and key_of("khoan", "1", "dieu 2") == "dieu 2/khoan 1"


def test_compare_giong_het():
    a, rep = nodes(BODY)
    b, _ = nodes(BODY)
    r = compare(a, b, rep)
    assert r.diffs == [] and r.n_match == r.n_match_fold == r.n_ours == r.n_theirs and r.n_match_pct == 1.0


def test_compare_khac_trinh_bay_khong_la_sai_khac_noi_dung():
    a, _ = nodes(BODY)
    b, _ = nodes([x.replace("Bộ luật này", "bộ luật này").replace("tội phạm.", "tội phạm") for x in BODY])
    r = compare(a, b)
    assert {d.kind for d in r.diffs} == {"khac_trinh_bay"}
    assert r.n_match == r.n_ours - 1 and r.n_match_fold == r.n_ours                   # nút Điều 1 không giống hệt nhưng khớp sau fold
    assert r.dieu_with_diffs() == [] and r.dieu_with_diffs(kem_trinh_bay=True) == ["dieu 1"]
    assert r.n_khop_chuan_hoa_pct == 1.0 and r.n_match_pct < 1.0


def test_compare_cac_loai_sai_khac():
    a, _ = nodes(BODY)
    sua = [x.replace("tự thú được giảm nhẹ", "tự thú được miễn").replace("Tội trộm cắp", "Tội trộm") for x in BODY if "Điều 4" not in x]
    sua += ["Điều 5. Mới", "Nội dung điều mới."]
    b, _ = nodes(sua)
    r = compare(a, b)
    kinds = {(d.kind, d.key) for d in r.diffs}
    assert ("khac_noi_dung", "dieu 2/khoan 2") in kinds
    assert ("khac_tieu_de", "dieu 3") in kinds
    assert ("thieu_o_ta", "dieu 5") in kinds
    assert r.dieu_with_diffs() == ["dieu 2", "dieu 3", "dieu 5"]
    assert r.n_match_fold < r.n_theirs and r.by_kind()["thieu_o_ta"] == 1


def test_compare_thua_o_ta_va_ghi_bai_bo():
    a, _ = nodes(BODY)
    a["dieu 4"] = Item("dieu 4", "dieu", "4", "Tội cũ", "Nội dung cũ.", "chuong II", 3)       # hệ thống còn Điều 4 mà văn bản hợp nhất ghi bãi bỏ
    b, rep_b = nodes(BODY)
    d = next(d for d in compare(a, b, rep_b).diffs if d.kind == "thua_o_ta")
    assert d.key == "dieu 4" and "bãi bỏ" in d.note


def test_compare_khac_vi_tri_dieu_duoi_chuong_khac():
    a, _ = nodes(BODY)
    b, _ = nodes([x for x in BODY if x not in ("Điều 3. Tội trộm cắp", "Người nào trộm cắp tài sản thì bị phạt tù.")]
                 [:BODY.index("Chương II")] + ["Điều 3. Tội trộm cắp", "Người nào trộm cắp tài sản thì bị phạt tù.",
                                              "Chương II", "CÁC TỘI DANH", "Điều 4. (được bãi bỏ)"])
    assert any(d.kind == "khac_vi_tri" and d.key == "dieu 3" for d in compare(a, b).diffs)


# ---------- lap_de_xuat ----------


def item(key, nd, td="", loai="khoan"):
    return Item(key, loai, key.rsplit(" ", 1)[1], td, nd, None, 0)


def test_lap_de_xuat_can_bang_chung():
    ours = {"dieu 9/khoan 1": item("dieu 9/khoan 1", "chiếm đoạt quyền dụng đất.")}
    theirs = {"dieu 9/khoan 1": item("dieu 9/khoan 1", "chiếm đoạt quyền sử dụng đất.")}
    # 1) không có bản tham chiếu nào đồng thuận và không có xác minh -> không đề xuất
    ds, khong = lap_de_xuat(ours, theirs, {"11/VBHN": {}}, nhan_nguon="135")
    assert ds == [] and [k["ly_do"] for k in khong] == ["thieu_bang_chung"]
    # 2) bản tham chiếu giống bản hệ thống -> không phải bằng chứng
    ds, khong = lap_de_xuat(ours, theirs, {"Công báo": {"dieu 9/khoan 1": item("dieu 9/khoan 1", "chiếm đoạt quyền dụng đất.")}}, nhan_nguon="135")
    assert ds == [] and khong[0]["tham_chieu"] == {"Công báo": "giong_ban_he_thong"}
    # 3) một bản tham chiếu viết như văn bản hợp nhất -> đề xuất
    ref = {"11/VBHN": {"dieu 9/khoan 1": item("dieu 9/khoan 1", "chiếm đoạt quyền sử dụng đất.")}}
    ds, khong = lap_de_xuat(ours, theirs, ref, nhan_nguon="135")
    assert khong == [] and len(ds) == 1
    d = ds[0]
    assert (d["khoa"], d["truong"], d["tu_cu"], d["thanh_moi"], d["loai"]) == ("dieu 9/khoan 1", "noi_dung", "quyền dụng", "quyền sử dụng", "loi_go")
    assert d["bang_chung"]["tham_chieu"] == {"11/VBHN": "cung_sua"} and d["bang_chung"]["nguon_so_sanh"] == "135"
    # 4) hoặc có xác minh nguồn do người ghi
    ds, khong = lap_de_xuat(ours, theirs, {}, {"dieu 9/khoan 1": [{"nguon": "Công báo 1263, tr. 5"}]}, nhan_nguon="135")
    assert len(ds) == 1 and ds[0]["bang_chung"]["xac_minh"] == [{"nguon": "Công báo 1263, tr. 5"}]


def test_lap_de_xuat_bo_qua_khac_trinh_bay_va_nut_chi_co_mot_ben():
    ours = {"dieu 1": item("dieu 1", "Bộ luật này hoà giải.", loai="dieu"), "dieu 2": item("dieu 2", "x", loai="dieu")}
    theirs = {"dieu 1": item("dieu 1", "bộ luật này hòa giải", loai="dieu"), "dieu 3": item("dieu 3", "y", loai="dieu")}
    assert lap_de_xuat(ours, theirs, {}, nhan_nguon="n") == ([], [])


def test_lap_de_xuat_chi_nut_xac_minh():
    ours = {"dieu 9": item("dieu 9", "a b c", loai="dieu"), "dieu 8": item("dieu 8", "a b c", loai="dieu")}
    theirs = {"dieu 9": item("dieu 9", "a b d", loai="dieu"), "dieu 8": item("dieu 8", "a b d", loai="dieu")}
    ds, _ = lap_de_xuat(ours, theirs, {}, {"dieu 9": [{"nguon": "x"}]}, nhan_nguon="n", chi_nut_xac_minh=True)
    assert {d["khoa"] for d in ds} == {"dieu 9"}


def test_lap_de_xuat_khong_sua_tu_dong_duoc_thi_khong_de_xuat():
    ours = {"dieu 9": item("dieu 9", "", loai="dieu")}
    theirs = {"dieu 9": item("dieu 9", "một đoạn hoàn toàn mới", loai="dieu")}
    ds, khong = lap_de_xuat(ours, theirs, {"X": theirs}, nhan_nguon="n")
    assert ds == [] and [k["ly_do"] for k in khong] == ["khong_tu_dong"]     # kể cả khi có bản tham chiếu đồng thuận


# ---------- nap_vbhn_json ----------


def test_nap_vbhn_json(tmp_path):
    p = tmp_path / "vbhn.json"
    p.write_text(json.dumps({"lines": BODY, "marks": {"2": [1]}, "footnotes": {"1": "Chú thích."}, "preamble": [], "pages": [[1, 1]] * len(BODY),
                             "sources": []}, ensure_ascii=False), encoding="utf-8")
    items, repealed = nap_vbhn_json(p)
    assert "dieu 2/khoan 1/diem a" in items and repealed == ["dieu 4"]
    again, _ = nodes(BODY)
    assert compare(again, items).diffs == []
