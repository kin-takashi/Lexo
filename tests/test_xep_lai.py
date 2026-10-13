"""Xếp lại top-N Điều (src/index/xep_lai): trộn điểm, đo, kiểm định dấu, kết luận dải ổn định, LLM chấm điểm (giả), tải mô hình thiếu."""
import json

import pytest

from src.index.xep_lai import (BgeReranker, LLMXepLai, XepLaiError, chi_so, hang_dap_an, ket_luan_xep_lai, kiem_dinh_dau, quet_w, rut_gon,
                               xep_lai_top, z)

CAND = [{"dieu": "dieu 1", "vec": 0.70}, {"dieu": "dieu 2", "vec": 0.65}, {"dieu": "dieu 3", "vec": 0.60}, {"dieu": "dieu 4", "vec": 0.50}]


def test_z_chuan_hoa_va_khong_chia_cho_0():
    a = z([1.0, 2.0, 3.0])
    assert sum(a) == pytest.approx(0) and a[2] == pytest.approx(-a[0])
    assert z([5.0, 5.0, 5.0]) == [0.0, 0.0, 0.0] and z([]) == []


def test_xep_lai_top_w0_chi_tin_mo_hinh_xep_lai_va_giu_phan_ngoai_top():
    assert xep_lai_top(CAND, [0.0, 3.0, 1.0], 0, top=3) == ["dieu 2", "dieu 3", "dieu 1", "dieu 4"]       # dieu 4 ngoài top giữ nguyên vị trí
    assert xep_lai_top(CAND, [0.0, 3.0, 1.0, -1.0], 0) == ["dieu 2", "dieu 3", "dieu 1", "dieu 4"]


def test_xep_lai_top_w_lon_quay_ve_thu_tu_vector_va_hoa_giu_thu_tu_vector():
    assert xep_lai_top(CAND, [0.0, 3.0, 1.0], 1000, top=3)[:3] == ["dieu 1", "dieu 2", "dieu 3"]
    assert xep_lai_top(CAND, [1.0, 1.0, 1.0], 0, top=3)[:3] == ["dieu 1", "dieu 2", "dieu 3"]             # mô hình không phân biệt: giữ thứ tự cũ


def test_hang_va_chi_so():
    assert hang_dap_an(["a", "b", "c"], {"c", "x"}) == 3 and hang_dap_an(["a"], {"z"}) is None
    m = chi_so([1, 3, None, 2])
    assert m["hit1"] == 0.25 and m["hit3"] == 0.75 and m["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 2) / 4)


def test_kiem_dinh_dau():
    assert kiem_dinh_dau(0, 0) == 1.0
    assert kiem_dinh_dau(8, 4) == pytest.approx(0.388, abs=0.001)                  # đúng số lần chạy bge: cứu 8, phá 4 -> chưa loại trừ được ngẫu nhiên
    assert kiem_dinh_dau(6, 1) == pytest.approx(0.125)
    assert kiem_dinh_dau(4, 4) == 1.0 and kiem_dinh_dau(10, 0) < 0.01


def _items():
    # 3 câu: câu 1 và 2 vector sai (đáp án ở hạng 2), câu 3 vector đúng; mô hình xếp lại đúng cả ba
    mk = lambda dap, rr: {"dap_an": {dap}, "cand": CAND[:3], "diem_xl": rr}  # noqa: E731
    return [mk("dieu 2", [0.0, 2.0, 0.0]), mk("dieu 2", [0.0, 2.0, 0.0]), mk("dieu 1", [2.0, 0.0, 0.0])]


def test_quet_w_cuu_pha_va_baseline():
    base, dong = quet_w(_items(), (0, 1000), 3)
    assert base["hit1"] == pytest.approx(1 / 3)
    d0, dmax = dong
    assert d0["hit1"] == 1.0 and d0["cuu"] == 2 and d0["pha"] == 0
    assert dmax["hit1"] == pytest.approx(1 / 3) and dmax["cuu"] == 0                # w rất lớn = quay về vector


def test_ket_luan_xep_lai_dai_on_dinh():
    base = {"hit1": 0.729, "mrr": 0.813}
    tot = [{"w": 0, "hit1": 0.786, "mrr": 0.858}, {"w": 0.25, "hit1": 0.786, "mrr": 0.858}, {"w": 0.5, "hit1": 0.80, "mrr": 0.865}]
    assert ket_luan_xep_lai(base, tot)[0]
    le = [{"w": 0, "hit1": 0.786, "mrr": 0.858}, {"w": 0.25, "hit1": 0.729, "mrr": 0.813}, {"w": 0.5, "hit1": 0.80, "mrr": 0.865}]
    assert not ket_luan_xep_lai(base, le)[0]                                      # hai ô cao nhưng không liền kề: không phải dải ổn định
    te = [{"w": 0, "hit1": 0.80, "mrr": 0.86}, {"w": 0.25, "hit1": 0.80, "mrr": 0.86}, {"w": 0.5, "hit1": 0.60, "mrr": 0.70}]
    assert ket_luan_xep_lai(base, te[:2])[0] and not ket_luan_xep_lai(base, [te[1], te[2]])[0]


def test_rut_gon_giu_tieu_de_va_khoan_1():
    vb = "Điều 364. Tội đưa hối lộ\nKhoản 1: Người nào đưa hối lộ ...\nĐiểm a: abc\nKhoản 2: nặng hơn"
    assert rut_gon(vb) == "Điều 364. Tội đưa hối lộ\nKhoản 1: Người nào đưa hối lộ ...\nĐiểm a: abc"
    assert len(rut_gon("x" * 5000, 600)) == 600


class LLMThu:
    """LLM giả: ghi lại lời nhắc, trả điểm cố định theo thứ tự ứng viên (đã đảo ở lượt hai)."""
    model = "gia"

    def __init__(self, tra):
        self.tra, self.prompts = tra, []

    def hoi(self, prompt):
        self.prompts.append(prompt)
        return self.tra.pop(0) if isinstance(self.tra, list) else self.tra


def test_llm_cham_hai_luot_dao_thu_tu_va_trung_binh():
    llm = LLMThu([json.dumps({"diem": [9, 2, 1]}), json.dumps({"diem": [0, 3, 7]})])       # lượt 2 theo thứ tự đảo: ứng viên 1 được 7
    kq = LLMXepLai(llm).cham("hỏi gì đó", ["Điều A", "Điều B", "Điều C"])
    assert kq == [(9 + 7) / 2, (2 + 3) / 2, (1 + 0) / 2]
    p1, p2 = llm.prompts
    assert "«hỏi gì đó»" in p1 and p1.index("Điều A") < p1.index("Điều C") and p2.index("Điều C") < p2.index("Điều A")


def test_llm_tra_sai_dinh_dang_thi_bao_loi_ro():
    for tho in ("không phải json", json.dumps({"diem": [1, 2]}), json.dumps({"x": 1})):
        with pytest.raises(XepLaiError):
            LLMXepLai(LLMThu(tho)).cham("q", ["a", "b", "c"])


def test_bge_thieu_mo_hinh_bao_cach_tai(tmp_path):
    with pytest.raises(XepLaiError, match="tai_xep_lai"):
        BgeReranker(tmp_path / "khong_co")
