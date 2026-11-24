"""So cách tách với chuẩn Claude mù (src/index/so_voi_chuan, scripts/so_voi_chuan.py, scripts/xuat_chuan_mu.py)."""
import importlib.util
import json
from pathlib import Path

import pytest

from src.index.bo_cau_hoi import MAC_DINH, doc_bo
from src.index.so_voi_chuan import (boot_hieu, doc_tach, ghep_toi_uu, so_sanh, so_voi_cac_chuan, tong_hop, tran_chuan, tuong_dong_chu,
                                    tuong_dong_vec)
from src.index.tap_train import HE_THONG

ROOT = Path(__file__).resolve().parents[1]


def nap(ten):
    spec = importlib.util.spec_from_file_location(ten + "_s", ROOT / "scripts" / f"{ten}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tuong_dong_chu_bo_tien_to_va_tu_noi():
    a = "Hiếp dâm: dùng vũ lực ép nạn nhân quan hệ tình dục"
    b = "Dùng vũ lực ép nạn nhân quan hệ tình dục"
    assert tuong_dong_chu(a, b) == pytest.approx(1.0)                       # tiền tố tên tội không ảnh hưởng
    assert tuong_dong_chu("Trộm xe máy của hàng xóm", "Lái xe gây tai nạn chết người") < 0.2
    assert tuong_dong_chu("", "abc") == 0.0 and tuong_dong_chu("và của", "và của") == 0.0     # chỉ toàn từ nối -> không có nội dung


def test_ghep_toi_uu_chon_phep_ghep_khong_tham_lam():
    s = [[0.9, 0.8], [0.85, 0.0]]                            # tham lam ghép (0,0) rồi (1,1)=0 -> 0.9; tối ưu là (0,1)+(1,0)=1.65
    tong, cap = ghep_toi_uu(s)
    assert tong == pytest.approx(1.65) and sorted(cap) == [(0, 1), (1, 0)]
    tong, cap = ghep_toi_uu([[0.1, 0.9, 0.2]])               # chữ nhật: 1 hàng, 3 cột
    assert tong == pytest.approx(0.9) and cap == [(0, 1)]
    tong, cap = ghep_toi_uu([[0.1], [0.9], [0.2]])           # 3 hàng, 1 cột -> trả theo (hàng, cột)
    assert tong == pytest.approx(0.9) and cap == [(1, 0)]
    assert ghep_toi_uu([]) == (0.0, [])
    lon = [[1.0 if i == j else 0.0 for j in range(14)] for i in range(14)]        # quá 12 -> ghép tham lam, vẫn đúng với ma trận đơn vị
    assert ghep_toi_uu(lon)[0] == pytest.approx(14.0)


def test_so_sanh_dung_thua_thieu():
    chuan = ["Trộm xe máy của hàng xóm", "Lái xe gây tai nạn làm chết người"]
    r = so_sanh(list(reversed(chuan)), chuan, tuong_dong_chu, 0.4)           # đúng nhưng đảo thứ tự: vẫn khớp
    assert r["bang_so"] == 1.0 and r["f1"] == 1.0 and r["ghep"] == pytest.approx(1.0) and r["lech"] == 0
    r = so_sanh(chuan + ["Đánh người gây thương tích"], chuan, tuong_dong_chu, 0.4)        # thừa một hành vi
    assert r["bang_so"] == 0.0 and r["lech"] == 1.0 and r["r"] == 1.0 and r["p"] == pytest.approx(2 / 3)
    assert r["ghep"] == pytest.approx(2 / 3)                                  # phạt tách thừa dù không cần ngưỡng
    r = so_sanh(chuan[:1], chuan, tuong_dong_chu, 0.4)                       # thiếu một hành vi
    assert r["lech"] == -1.0 and r["p"] == 1.0 and r["r"] == 0.5
    with pytest.raises(ValueError):
        so_sanh([], chuan, tuong_dong_chu, 0.4)


def test_tran_va_so_voi_cac_chuan():
    a = {"x": ["Trộm xe máy của hàng xóm", "Lái xe gây tai nạn làm chết người"]}
    b = {"x": ["Lái xe gây tai nạn làm chết người", "Trộm xe máy của hàng xóm"]}
    c = {"x": ["Trộm xe máy của hàng xóm"]}                                  # một bản chuẩn khác gộp làm một
    tran = tong_hop(tran_chuan([a, b], ["x"], tuong_dong_chu, 0.4))
    assert tran["bang_so"] == 1.0 and tran["ghep"] == pytest.approx(1.0)
    tran3 = tong_hop(tran_chuan([a, b, c], ["x"], tuong_dong_chu, 0.4))
    assert tran3["bang_so"] < 1.0                                            # bất đồng giữa các bản chuẩn làm trần thấp đi
    with pytest.raises(ValueError, match="2 bản"):
        tran_chuan([a], ["x"], tuong_dong_chu, 0.4)
    kq = tong_hop(so_voi_cac_chuan(a, [a, b], ["x"], tuong_dong_chu, 0.4))
    assert kq["ghep"] == pytest.approx(1.0)


def test_tuong_dong_vec_cosine_va_nap_theo_lo():
    goi = []

    def embed(ts):
        goi.append(list(ts))
        return [[1.0, 0.0] if "xe" in t else [0.0, 1.0] for t in ts]

    td = tuong_dong_vec(embed, lo=2)
    td.nap(["Trộm xe", "Đốt nhà", "Lái xe", "Trộm xe"])
    assert td("Trộm xe", "Lái xe") == pytest.approx(1.0) and td("Trộm xe", "Đốt nhà") == pytest.approx(0.0)
    assert [len(g) for g in goi] == [2, 1]                                   # 3 chuỗi khác nhau, lô 2, không nhúng lại


def test_boot_hieu_xac_dinh_va_khong_lech():
    a, b = [1.0, 1.0, 0.0, 1.0, 1.0, 0.0] * 3, [1.0, 1.0, 0.0, 1.0, 1.0, 0.0] * 3
    h, lo, hi = boot_hieu(a, b)
    assert h == 0.0 and lo == 0.0 and hi == 0.0                              # hai dãy giống hệt
    a2 = [1.0] * 10 + [0.0] * 10
    b2 = [1.0] * 5 + [0.0] * 15
    h, lo, hi = boot_hieu(a2, b2)
    assert h == pytest.approx(0.25) and lo < h < hi and boot_hieu(a2, b2) == (h, lo, hi)
    with pytest.raises(ValueError):
        boot_hieu([1.0], [1.0, 0.0])


def test_doc_tach_hai_dinh_dang():
    assert doc_tach({"dn01": ["a", " b "], "dn02": {"hanh_vi": ["c"]}}) == {"dn01": ["a", "b"], "dn02": ["c"]}
    for hong in ({}, [], {"x": []}, {"x": [""]}, {"x": {"khac": ["a"]}}, {"x": "chuỗi"}):
        with pytest.raises(ValueError):
            doc_tach(hong)


def _co_bo():
    if not MAC_DINH.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json")
    return doc_bo(MAC_DINH, "dev", "nhieu_dieu")


def test_script_so_voi_chuan_chay_dau_cuoi(tmp_path, capsys):
    bo = _co_bo()
    mod = nap("so_voi_chuan")
    ds = {c["id"]: [f"Hành vi {k} của tình huống {c['id']} xe máy hàng xóm" for k in range(len(c["dieu"]))] for c in bo}

    def ghi(ten, d):
        p = tmp_path / ten
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return str(p)
    c1, c2 = ghi("c1.json", ds), ghi("c2.json", {i: {"hanh_vi": v} for i, v in ds.items()})            # hai bản chuẩn, hai định dạng
    dung = ghi("tach_dev_dung.json", ds)
    thua = ghi("tach_dev_thua.json", {i: v + ["Hành vi thừa hoàn toàn khác về chuyện đốt nhà"] for i, v in ds.items()})
    luu = tmp_path / "kq.md"
    assert mod.main(["--chuan", c1, c2, "--du-doan", dung, thua, "--luu", str(luu), "--chi-tiet"]) == 0
    out = luu.read_text(encoding="utf-8")
    assert "**TRẦN**" in out and "| dung | 100% | 100% |" in out and "| thua | 0% |" in out
    assert "KTC 95%" in out and "- [thua] " in out                                        # có khoảng tin cậy và liệt kê câu lệch
    with pytest.raises(SystemExit, match="thiếu"):
        mod.main(["--chuan", c1, "--du-doan", ghi("tach_dev_hong.json", {"dn01": ["x"]})])
    with pytest.raises(SystemExit, match="đóng băng"):
        mod.main(["--tap", "kiem_tra", "--chuan", c1, "--du-doan", dung])
    assert mod.main(["--chuan", c1, "--du-doan", dung]) == 0                              # chỉ 1 bản chuẩn: không có trần nhưng vẫn chạy
    assert "chưa có (cần ≥ 2 bản chuẩn)" in capsys.readouterr().out


def test_script_xuat_chuan_mu_khong_lo_dap_an(tmp_path):
    bo = _co_bo()
    mod = nap("xuat_chuan_mu")
    assert mod.main(["--ra", str(tmp_path)]) == 0
    cau = json.loads((tmp_path / "cau_hoi_mu_dev.json").read_text(encoding="utf-8"))
    assert cau == {c["id"]: c["cau_hoi"] for c in bo}
    md = (tmp_path / "LOI_NHAC_CHUAN_MU.md").read_text(encoding="utf-8")
    assert HE_THONG in md and f"Có {len(bo)} tình huống ĐỘC LẬP" in md and bo[0]["cau_hoi"] in md
    tho = json.dumps(cau, ensure_ascii=False) + md
    assert '"dieu"' not in tho and "đáp án" not in cau and "tap" not in cau                  # không có trường đáp án
    with pytest.raises(SystemExit, match="đóng băng"):
        mod.main(["--tap", "kiem_tra", "--ra", str(tmp_path)])
