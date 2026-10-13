"""Bộ câu hỏi thống nhất eval/bo_cau_hoi.json: đọc theo tập, kiểm tra hợp lệ, bảng duyệt; file thật hợp lệ và các tập không dùng chung Điều."""
import json

import pytest

from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, bang_xem_duyet, doc_bo, kiem_tra_hop_le, thong_ke


def mot(id_, q="lén lấy xe máy hàng xóm", dieu=("173",), **kw):
    x = {"id": id_, "cau_hoi": q, "dieu": list(dieu), "loai": "don", "tap": "dev", "nguon": "claude", "trang_thai": "nhap"}
    x.update(kw)
    return x


def ghi(tmp_path, cau, ten="bo.json"):
    p = tmp_path / ten
    p.write_text(json.dumps({"cau_hoi": cau}, ensure_ascii=False), encoding="utf-8")
    return p


def test_doc_bo_loc_theo_tap_va_loai(tmp_path):
    p = ghi(tmp_path, [mot("a"), mot("b", q="hai việc", dieu=("243", "178"), loai="nhieu_dieu"), mot("c", q="khác", dieu=("174",), tap="xac_nhan")])
    assert [x["id"] for x in doc_bo(p, "dev")] == ["a"]                       # mặc định bỏ loại cần tìm đủ nhiều Điều
    assert [x["id"] for x in doc_bo(p, "dev", None)] == ["a", "b"]
    assert [x["id"] for x in doc_bo(p)] == ["a", "c"] == [x["id"] for x in doc_bo(p, "tat_ca")]
    with pytest.raises(BoCauHoiError, match="tập không hợp lệ"):
        doc_bo(p, "thu")
    with pytest.raises(BoCauHoiError, match="không có câu nào thuộc tập 'kiem_tra'"):
        doc_bo(p, "kiem_tra")


def test_loi_doc_file_goi_y_ten_file_cu(tmp_path):
    with pytest.raises(BoCauHoiError, match="--tap xac_nhan"):
        doc_bo(tmp_path / "cau_hoi_dev2.json")
    with pytest.raises(BoCauHoiError, match="không thấy"):
        doc_bo(tmp_path / "khong_co.json")
    hong = tmp_path / "hong.json"
    hong.write_text("{khong phai json", encoding="utf-8")
    with pytest.raises(BoCauHoiError, match="JSON"):
        doc_bo(hong)
    thieu = tmp_path / "thieu.json"
    thieu.write_text("{}", encoding="utf-8")
    with pytest.raises(BoCauHoiError, match="cau_hoi"):
        doc_bo(thieu)


def test_kiem_tra_hop_le_bat_cac_loi():
    assert kiem_tra_hop_le([mot("a"), mot("b", q="câu khác", dieu=("217a",), tap="kiem_tra")]) == []
    loi = "\n".join(kiem_tra_hop_le([
        mot("a"), mot("a", q="cùng id"), mot("c", q="  LÉN lấy xe máy   hàng xóm "), mot("d", q="theo Điều 173 thì sao", dieu=("174",)),
        mot("e", q="x", dieu=("abc",)), mot("f", q="y", dieu=("175",), tap="thu"), mot("g", q="z", dieu=("176",), loai="nhieu_dieu"),
        mot("h", q="w", dieu=("177",), nguon="ai_do"), mot("i", q="v", dieu=("173",), tap="kiem_tra")]))
    for mong_doi in ("a: id trùng", "c: câu hỏi trùng với a", "d: câu hỏi nhắc số Điều", "e: dieu phải là danh sách", "f: tap = 'thu'",
                     "g: loai nhieu_dieu cần ít nhất 2 Điều", "h: nguon = 'ai_do'", "Điều 173 là đáp án ở cả tập dev (a) và kiem_tra (i)"):
        assert mong_doi in loi, mong_doi


def test_nhieu_dieu_duoc_phep_trung_dieu_voi_tap_khac():
    cau = [mot("a", dieu=("243",)), mot("b", q="cháy rừng lan sang nhà dân làm chết người", dieu=("243", "178", "128"), loai="nhieu_dieu", tap="kiem_tra")]
    assert kiem_tra_hop_le(cau) == []


def test_bang_xem_duyet_chia_tap_va_thoat_dau_gach():
    md = bang_xem_duyet([mot("a", q="hỏi | có gạch"), mot("c", q="khác", dieu=("999",), tap="kiem_tra")], {"dieu 173": "Điều 173. Tội trộm cắp tài sản"})
    assert "## Tập dev (1 câu)" in md and "## Tập kiem_tra (1 câu)" in md and "## Tập xac_nhan" not in md
    assert "| a | hỏi \\| có gạch | 173 | Tội trộm cắp tài sản |" in md
    assert "| c | khác | 999 | ? |" in md                                   # Điều không có trong chỉ mục -> dấu hỏi, không lỗi


def test_thong_ke():
    tk = thong_ke([mot("a"), mot("b", q="q2", dieu=("174",), tap="kiem_tra", nguon="nguoi_dung")])
    assert tk["tap"] == {"dev": 1, "kiem_tra": 1} and tk["nguon"]["nguoi_dung"] == 1


def test_file_bo_cau_hoi_that_hop_le_va_cac_tap_khong_chung_dieu():
    if not MAC_DINH.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json")
    cau = doc_bo(MAC_DINH, None, None)
    assert kiem_tra_hop_le(cau) == []                     # gồm: id / câu không trùng, không nhắc số Điều, đáp án các tập không giao nhau
    for tap in TAP:
        assert len(doc_bo(MAC_DINH, tap)) >= 50, tap


def test_tap_dong_bang_la_tap_con_cua_tap_va_khong_gom_dev():
    assert TAP_DONG_BANG < set(TAP) and "dev" not in TAP_DONG_BANG
    assert {"xac_nhan", "kiem_tra", "phu"} == set(TAP_DONG_BANG)


def test_tap_phu_moi_dieu_mot_cau_don():
    if not MAC_DINH.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json")
    phu = doc_bo(MAC_DINH, "phu", None)
    assert all(x["loai"] == "don" and len(x["dieu"]) == 1 for x in phu)
    dieu = [x["dieu"][0] for x in phu]
    assert len(dieu) == len(set(dieu))                  # phủ nốt: mỗi Điều đúng một câu
