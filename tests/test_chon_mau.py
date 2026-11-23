"""Chọn tập học sạch và tập con lồng nhau (src/index/chon_mau.py)."""
from src.index.chon_mau import mau_trung, to_hop_dieu, xep_hang


def mau(id_, dieu_theo_hanh_vi):
    """dieu_theo_hanh_vi: danh sách các danh sách Điều chấp nhận, mỗi phần tử là một hành vi."""
    return {"id": id_, "tinh_huong": f"tình huống {id_}", "loai": "nhieu",
            "hanh_vi": [{"mo_ta": f"hành vi {i} của {id_}", "dieu": list(d)} for i, d in enumerate(dieu_theo_hanh_vi)]}


def cau(id_, dieu, loai="nhieu_dieu", tap="dev"):
    return {"id": id_, "cau_hoi": "nội dung không được dùng", "dieu": dieu, "loai": loai, "tap": tap}


def test_to_hop_dieu_hai_cach():
    x = mau("a", [["10", "11"], ["20"]])
    assert to_hop_dieu(x) == {frozenset({"10", "11", "20"}), frozenset({"10", "20"})}


def test_mau_trung_chi_theo_cau_nhieu_dieu_va_bat_ke_thu_tu():
    ds = [mau("t1", [["168"], ["141"]]), mau("t2", [["141"], ["168"]]), mau("t3", [["168"]]), mau("t4", [["168"], ["141"], ["5"]])]
    bo = [cau("dn01", ["168", "141"]), cau("d01", ["5"], loai="don")]
    assert mau_trung(ds, bo) == ["t1", "t2"]                    # t3 chỉ một Điều, t4 dư Điều; câu loai don không tính


def test_mau_trung_tinh_theo_dieu_dau_khi_hanh_vi_co_nhieu_dieu_chap_nhan():
    x = mau("t1", [["10", "11"], ["20"]])
    assert mau_trung([x], [cau("q", ["10", "20"])]) == ["t1"]    # chỉ khớp theo Điều đầu của mỗi hành vi
    assert mau_trung([x], [cau("q", ["10", "11", "20"])]) == ["t1"]
    assert mau_trung([x], [cau("q", ["11", "20"])]) == []


def _tap(n=120):
    return [mau(f"t{i:03d}", [[str(i)]] * (1 + i % 5)) for i in range(n)]


def test_xep_hang_xac_dinh_va_khong_phu_thuoc_thu_tu_dau_vao():
    ds = _tap()
    a = xep_hang(ds, 42)
    assert a == xep_hang(list(reversed(ds)), 42)
    assert a != xep_hang(ds, 43)
    assert sorted(a) == sorted(x["id"] for x in ds) and len(set(a)) == len(ds)


def test_xep_hang_k_dau_giu_ti_le_cac_tang():
    ds = _tap(200)
    so_hv = {x["id"]: min(len(x["hanh_vi"]), 4) for x in ds}
    tong = {t: sum(1 for v in so_hv.values() if v == t) for t in (1, 2, 3, 4)}
    thu_tu = xep_hang(ds, 7)
    for k in (20, 50, 100):
        co = {t: sum(1 for i in thu_tu[:k] if so_hv[i] == t) for t in tong}
        for t in tong:
            assert abs(co[t] - k * tong[t] / len(ds)) <= 1.5, (k, t, co)

