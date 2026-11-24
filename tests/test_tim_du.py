"""Chấm «tìm đủ» cho tình huống nhiều Điều (src/index/tim_du, scripts/danh_gia_nhieu.py) và các câu nhieu_dieu trong file bộ đo thật."""
import importlib.util
import json
from pathlib import Path

import pytest

from src.index.bo_cau_hoi import MAC_DINH, TAP_DONG_BANG, doc_bo
from src.index.tim_du import cham, hien_thi, so_dieu, so_ngan_sach, tong_hop

ROOT = Path(__file__).resolve().parents[1]


def nap_script():
    spec = importlib.util.spec_from_file_location("danh_gia_nhieu", ROOT / "scripts" / "danh_gia_nhieu.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_so_dieu_chuan_hoa():
    assert so_dieu("dieu 173") == "173" and so_dieu("Điều 217A") == "217a" and so_dieu(" 173 ") == "173"


def test_hien_thi_hop_m_dieu_dau_cua_moi_hanh_vi_khong_lap():
    hv = [["173", "172", "171", "170"], ["178", "173", "134"]]
    assert hien_thi(hv, 3) == ["173", "172", "171", "178", "134"]          # 173 lặp ở hành vi thứ hai chỉ tính một lần
    assert hien_thi(hv, 1) == ["173", "178"]
    with pytest.raises(ValueError):
        hien_thi(hv, 0)


def test_cham_tim_du_va_thieu():
    ok = cham(["173", "178"], [["173", "172"], ["134", "178"]], m=2)
    assert ok["tim_du"] == 1.0 and ok["bao_phu"] == 1.0 and ok["thieu"] == []
    assert ok["chinh_xac"] == pytest.approx(2 / 4) and ok["hanh_vi_co_dap_an"] == 1.0 and ok["dung_so_hanh_vi"] == 1.0 and ok["so_hien_thi"] == 4
    thieu = cham(["173", "178"], [["173", "172", "171"], ["134", "318", "156"]], m=3)           # hành vi 2 không đưa 178 vào top 3
    assert thieu["tim_du"] == 0.0 and thieu["bao_phu"] == 0.5 and thieu["thieu"] == ["178"]
    assert thieu["hanh_vi_co_dap_an"] == 0.5


def test_cham_trung_mot_dieu_la_chua_du():
    # tìm trúng Điều 173 mà bỏ sót 178: Hit@k kiểu «một trong các Điều» tính là trúng, còn «tìm đủ» phải tính là sai
    r = cham(["173", "178"], [["173", "172"]], m=3)
    assert r["tim_du"] == 0.0 and r["bao_phu"] == 0.5 and r["dung_so_hanh_vi"] == 0.0


def test_cham_tach_thua_lam_giam_chinh_xac_khong_lam_giam_tim_du():
    r = cham(["173", "178"], [["173"], ["178"], ["999"]], m=1)             # hành vi thứ ba là thừa
    assert r["tim_du"] == 1.0 and r["chinh_xac"] == pytest.approx(2 / 3)
    assert r["hanh_vi_co_dap_an"] == pytest.approx(2 / 3) and r["dung_so_hanh_vi"] == 0.0


def test_cham_loi_dau_vao():
    with pytest.raises(ValueError, match="rỗng"):
        cham([], [["173"]])
    r = cham(["173", "173"], [[]])                                         # đáp án lặp được gộp; hành vi rỗng không có gì để hiển thị
    assert r["bao_phu"] == 0.0 and r["chinh_xac"] == 0.0 and r["so_hien_thi"] == 0


def test_so_ngan_sach_khong_tach_cung_k():
    xh = ["173", "172", "178", "134"]
    assert so_ngan_sach(["173", "178"], xh, 2)["tim_du"] == 0.0           # k = 2 chưa tới 178
    assert so_ngan_sach(["173", "178"], xh, 3)["tim_du"] == 1.0
    assert so_ngan_sach(["173", "178"], xh, 0)["so_hien_thi"] == 1         # k < 1 được nâng lên 1, không báo lỗi


def test_tong_hop_trung_binh():
    a = cham(["1", "2"], [["1"], ["2"]], m=1)
    b = cham(["1", "2"], [["1"]], m=1)
    tb = tong_hop([a, b])
    assert tb["tim_du"] == 0.5 and tb["bao_phu"] == pytest.approx(0.75)
    with pytest.raises(ValueError):
        tong_hop([])


def test_doc_du_doan_bao_loi_ro_rang(tmp_path):
    mod = nap_script()
    bo = [{"id": "a"}, {"id": "b"}]
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"a": ["hành vi 1", "hành vi 2"], "b": ["hành vi"]}, ensure_ascii=False), encoding="utf-8")
    assert mod.doc_du_doan(f, bo)["a"][1] == "hành vi 2"
    f.write_text(json.dumps({"a": ["x"]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="thiếu 1 id: b"):
        mod.doc_du_doan(f, bo)
    f.write_text(json.dumps({"a": [], "b": ["x"]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="ít nhất một hành vi"):
        mod.doc_du_doan(f, bo)
    f.write_text("{hong", encoding="utf-8")
    with pytest.raises(SystemExit, match="không đọc được"):
        mod.doc_du_doan(f, bo)


def test_dong_bang_mot_khong_tach_khong_co_so_lieu_hanh_vi():
    mod = nap_script()
    tb = tong_hop([cham(["1", "2"], [["1"], ["2"]], m=1)])
    assert mod.dong_bang("x", tb, co_hanh_vi=False).count("–") == 2
    assert "–" not in mod.dong_bang("x", tb, co_hanh_vi=True)


def test_cau_nhieu_dieu_trong_file_bo_cau_hoi_that():
    if not MAC_DINH.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json")
    try:
        nd = doc_bo(MAC_DINH, None, "nhieu_dieu")
    except Exception:
        pytest.skip("chưa có câu nhieu_dieu")
    assert len(nd) >= 20
    for x in nd:
        assert 2 <= len(x["dieu"]) <= 4 and len(set(x["dieu"])) == len(x["dieu"]), x["id"]
        assert x["tap"] in ("dev", "kiem_tra"), x["id"]                                  # xac_nhan / phu giữ mỗi câu một Điều
    # Điều nhiều hành vi không được trùng nguyên bộ Điều giữa dev và kiem_tra (tránh «dò đáp án» sang tập đóng băng)
    dev = {frozenset(x["dieu"]) for x in nd if x["tap"] == "dev"}
    dong = {frozenset(x["dieu"]) for x in nd if x["tap"] in TAP_DONG_BANG}
    assert not (dev & dong)
