"""Kiểm thử scripts/phan_tich_cbba.py (phân tích mô tả kết quả đo mẫu con cbba). Dữ liệu giả lập, không cần mô hình."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.ban_an import chon_dieu as cd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "phan_tich_cbba.py"
_spec = importlib.util.spec_from_file_location("phan_tich_cbba", SCRIPT)
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)


def _mau(n: int = 60) -> list[dict]:
    """n vụ: Điều xoay vòng 173 / 174 / 251, mỗi 6 vụ có thêm Điều thứ hai; ứng viên đúng thứ tự giảm dần."""
    ra = []
    for i in range(n):
        dieu = [["173", "174", "251"][i % 3]] + (["321"] if i % 6 == 0 else [])
        ra.append({"id": f"cbba_{i:03d}", "tap": "test", "dieu": cd.sap_xep(dieu), "cap": "phuc_tham" if i % 5 == 0 else "so_tham", "nam": 2020 + i % 3,
                   "tan_suat_dieu_hoc": [0, 5, 20, 50][i % 4], "dieu_chua_gap": i % 20 == 0,
                   "so_tu_goc": [300, 700, 1500][i % 3] if i % 7 else None,
                   "xep_hang": {c: ["173", "174", "251", "321", "300"] for c in cd.CHE_DO_UV}})
    return ra


def _dong(x: dict, hien: list[str], loi: str | None = None) -> dict:
    return {"id": x["id"], "dieu": x["dieu"], "hien_thi": hien, "loi": loi, "cham": cd.cham_chon(x["dieu"], hien), "giay": 2.0,
            "co_the_bi_cat": False, "co_think": False}


def test_wilson_mcnemar_va_khoang_hieu():
    lo, hi = pt.wilson(50, 100)
    assert round(lo, 3) == 0.404 and round(hi, 3) == 0.596
    assert pt.wilson(0, 0) == (0.0, 0.0) and pt.wilson(10, 10)[1] == 1.0 and pt.wilson(0, 10)[0] == 0.0
    assert pt.mcnemar_p(0, 0) == 1.0 and pt.mcnemar_p(5, 5) == 1.0
    assert round(pt.mcnemar_p(10, 0), 6) == round(2 / 1024, 6)                    # 10 thắng, 0 thua: 2 × (1/2)^10
    hieu = [1] * 30 + [0] * 60 + [-1] * 10
    tb, lo, hi = pt.khoang_hieu(hieu)
    assert tb == pytest.approx(0.2) and lo < tb < hi and (tb, lo, hi) == pt.khoang_hieu(hieu)       # xác định
    assert pt.khoang_hieu([]) == (0.0, 0.0, 0.0)


def test_hang_truy_hoi_va_vi_mo_theo_dieu():
    mau = _mau(12)
    a3 = pt.hang_truy_hoi(mau, "hybrid", 3)
    assert all(r["hien_thi"] == ["173", "174", "251"] for r in a3) and a3[0]["cham"]["tim_du"] == 0.0        # vụ 0: đáp án 173 + 321, thiếu 321
    assert a3[1]["cham"]["tim_du"] == 1.0
    a5 = pt.hang_truy_hoi(mau, "hybrid", 5)
    assert all(r["cham"]["tim_du"] == 1.0 for r in a5)
    v, so = pt.vi_mo_theo_dieu(a3, 1)
    assert so == 4 and v == pytest.approx((1 + 1 + 1 + 0) / 4)                    # 321 không bao giờ được hiển thị ở top 3
    v4, so4 = pt.vi_mo_theo_dieu(a3, 4)
    assert so4 == 3 and v4 == 1.0                                                  # 321 chỉ có 2 vụ nên bị loại khỏi trung bình từ 4 vụ
    hon, kem, bang = pt.so_dieu_hon_kem(a5, a3, toi_thieu=1)
    assert (hon, kem, bang) == (1, 0, 3)


def test_bao_cao_day_du_va_danh_dau_chua_du():
    mau = _mau(60)
    c0 = [_dong(x, ["173"]) for x in mau]                                           # mô hình gốc: luôn chọn 173
    l = [_dong(x, x["dieu"]) for x in mau[:50]]                                     # L đúng hoàn toàn nhưng thiếu 10 vụ cuối
    l[3] = _dong(mau[3], [], loi="không đọc được")
    cau_hinh = {"A3": pt.hang_truy_hoi(mau, "hybrid", 3), "C0": c0, "L": l}
    txt = pt.bao_cao(mau, cau_hinh, "thử")
    assert "**CHƯA ĐỦ (50/60)**" in txt and "## 2. So sánh cặp" in txt and "L so với C0" in txt and "L so với A3" in txt
    assert "L so với A5" not in txt                                                  # không có A5 thì không so
    # L (vụ chung = 50, vụ 3 lỗi) so với C0: số thắng / thua đếm tay
    chung = [x for x in mau[:50]]
    thang = sum(1 for x, r in zip(chung, l) if r["cham"]["tim_du"] > cd.cham_chon(x["dieu"], ["173"])["tim_du"])
    thua = sum(1 for x, r in zip(chung, l) if r["cham"]["tim_du"] < cd.cham_chon(x["dieu"], ["173"])["tim_du"])
    assert f"| {thang + thua} | {thang} / {thua} |" in txt
    assert "| cấp xét xử |" in txt and "| tần suất Điều hiếm nhất trong tập học |" in txt and "0 (chưa gặp)" in txt and "| Điều chưa gặp ở tập học |" in txt
    assert "| độ dài sự việc gốc (từ) |" in txt and "≤500" in txt and "501–1000" in txt and ">1000" in txt and "| ? |" in txt
    assert pt.nhom_do_dai({"so_tu_goc": 500}) == "≤500" and pt.nhom_do_dai({"so_tu_goc": 1000}) == "501–1000" and pt.nhom_do_dai({}) == "?"
    assert "## 4. Trung bình vĩ mô theo Điều" in txt and "L so với C0 theo từng Điều" in txt


def test_chay_script_ghi_phan_tich(tmp_path):
    mau = _mau(30)
    goi, kq = tmp_path / "goi", tmp_path / "kq"
    goi.mkdir()
    kq.mkdir()
    (goi / "ban_an_do.json").write_text(json.dumps({"mau": mau + [dict(mau[0], id="dev_x", tap="dev")]}, ensure_ascii=False), encoding="utf-8")
    (goi / "cau_hinh.json").write_text(json.dumps({"ung_vien": {"che_do": "hybrid", "k": 3}}), encoding="utf-8")
    for ten, hien in (("C0", lambda x: ["173"]), ("L", lambda x: x["dieu"])):
        (kq / f"{ten}.jsonl").write_text("".join(json.dumps(_dong(x, hien(x)), ensure_ascii=False) + "\n" for x in mau), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--goi", str(goi), "--ket-qua", str(kq), "--cau-hinh", "A3,A5,C0,L,HOP"], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "BỎ QUA HOP" in r.stdout
    txt = (kq / "phan_tich.md").read_text(encoding="utf-8")
    assert "30 vụ trong gói đo" in txt and "| L | 30 |" in txt and "CHƯA ĐỦ" not in txt          # dev_x không lẫn vào tập test
    assert "| L so với C0 | tìm đủ |" in txt and "| L so với A5 | tìm đủ |" in txt
    assert subprocess.run([sys.executable, str(SCRIPT), "--goi", str(goi), "--ket-qua", str(kq), "--tap", "dev", "--cau-hinh", "HOP"],
                          capture_output=True, text=True, cwd=ROOT).returncode != 0         # tập dev có 1 vụ nhưng không cấu hình nào có kết quả
    assert subprocess.run([sys.executable, str(SCRIPT), "--goi", str(tmp_path / "khong"), "--ket-qua", str(kq)], capture_output=True, text=True,
                          cwd=ROOT).returncode != 0
