"""Tra cứu theo ngày, nguồn sửa đổi từng nút, lịch sử, so sánh (src/query/lookup.py) trên bộ luật thử nghiệm đã áp lệnh."""
import pytest

from src.apply.rebuild import rebuild
from src.query.lookup import (
    dieu_khoan_lien_quan, dieu_status, get_dieu, lich_su_dieu, luu_y_hieu_luc, render, so_sanh, tom_tat_nguon,
)

from test_apply_rebuild import BASE_DATE, D1, D2, D3, P, env  # noqa: F401  (env là fixture)

L12 = dict(nguon="12/2017/QH14", ban_hanh="2017-06-20")
L86 = dict(nguon="86/2025/QH15", ban_hanh="2025-06-25")


@pytest.fixture
def daapdung(env):  # noqa: F811
    """Điều 2 khoản 2: sửa nguyên khoản (L12, D1). Điều 3 khoản 1: hai lệnh cùng ngày D1 (L12). Điều 3a mới (L86, D2). Điều 4 bãi bỏ (L86, D3)."""
    env.l_khoan = env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1,
                          noi_dung="2. Người phạm tội tự thú được miễn trách nhiệm hình sự.", vi_tri="Điều 1 khoản 3", **L12)
    env.l_a = env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1,
                      noi_dung="1. Bản trung gian.", vi_tri="Điều 1 khoản 4", **L12)
    env.l_b = env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "3", "khoan", "1")], "kieu": "thay"}, tu=D1,
                      cu="trung gian", moi="cuối cùng", vi_tri="Điều 1 khoản 5", **L12)
    env.l_new = env.cmd("bo_sung", {"cha": P("chuong", "II"), "sau": P("dieu", "3"), "loai": "dieu", "ky_hieu": "3a"}, tu=D2,
                        noi_dung="Điều 3a. Tội mới\n1. Người nào phạm tội mới:\na) bị phạt tiền;\nb) bị phạt tù.", vi_tri="Điều 1", **L86)
    env.l_del = env.cmd("bai_bo", {"muc_tieu": [P("dieu", "4")]}, tu=D3, vi_tri="Điều 2 khoản 1", **L86)
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 5 and not rep.problems()
    return env


def test_ban_goc_khong_co_nguon_va_ngay_mac_dinh_la_hom_nay(env):  # noqa: F811
    u = get_dieu(env.c, env.vb, "2", BASE_DATE)
    assert u is not None and all(not n.da_sua for n in u.walk()) and tom_tat_nguon(u) == []
    assert "[" not in render(u, ghi_chu=True)
    assert get_dieu(env.c, env.vb, "2") is not None                      # ngay=None -> hôm nay


def test_hien_hanh_theo_luat_sua_doi_kem_nguon(daapdung):
    env = daapdung
    u = get_dieu(env.c, env.vb, "2")                                       # mặc định: hiện hành
    k2 = next(c for c in u.children if c.ky_hieu == "2")
    assert k2.noi_dung == "Người phạm tội tự thú được miễn trách nhiệm hình sự." and k2.da_sua
    n = k2.nguon[0]
    assert (n.so_hieu, n.vi_tri_nguon, n.hieu_luc_tu, n.loai_thao_tac, n.tao_moi) == ("12/2017/QH14", "Điều 1 khoản 3", D1, "sua_doi", False)
    assert "Luật số 12/2017/QH14 (Điều 1 khoản 3), hiệu lực từ 01/01/2018" in n.mo_ta()
    assert not next(c for c in u.children if c.ky_hieu == "1").da_sua        # khoản không đổi thì không có nguồn
    text = render(u, ghi_chu=True)
    assert text.count("[") == 1 and "sửa đổi, bổ sung bởi Luật số 12/2017/QH14" in text
    assert "[" not in render(u)                                             # mặc định không kèm ghi chú (tương thích cũ)


def test_xem_ban_cu_theo_ngay(daapdung):
    env = daapdung
    old = get_dieu(env.c, env.vb, "2", "2017-12-31")
    assert next(c for c in old.children if c.ky_hieu == "2").noi_dung == "Người phạm tội tự thú được giảm nhẹ."
    assert tom_tat_nguon(old) == []                                         # bản cũ là bản gốc, không có nguồn sửa
    assert next(c for c in get_dieu(env.c, env.vb, "2", D1).children if c.ky_hieu == "2").noi_dung.endswith("hình sự.")
    assert get_dieu(env.c, env.vb, "4", "2025-12-31") is not None and get_dieu(env.c, env.vb, "4", D3) is None


def test_hai_lenh_cung_ngay_hien_thanh_chuoi_nguon(daapdung):
    env = daapdung
    k1 = next(c for c in get_dieu(env.c, env.vb, "3", D1).children if c.ky_hieu == "1")
    assert k1.noi_dung == "Bản cuối cùng."
    assert [n.lenh_id for n in k1.nguon] == [env.l_a, env.l_b]                # lệnh trung gian (khoảng rỗng) rồi lệnh cuối
    assert [n.loai_thao_tac for n in k1.nguon] == ["sua_doi", "thay_cum_tu"]
    assert "; rồi " in render(get_dieu(env.c, env.vb, "3", D1), ghi_chu=True)


def test_dieu_bo_sung_moi_ghi_nguon_o_dieu_khong_lap_o_con(daapdung):
    env = daapdung
    u = get_dieu(env.c, env.vb, "3a", D2)
    assert u.nguon[0].tao_moi and u.nguon[0].mo_ta().startswith("bổ sung bởi Luật số 86/2025/QH15 (Điều 1)")
    assert all(c.nguon and c.nguon[0].lenh_id == env.l_new for c in u.walk())    # mọi nút con cũng thuộc lệnh này
    assert render(u, ghi_chu=True).count("[") == 1                              # ...nhưng chỉ ghi chú một lần, ở Điều
    assert get_dieu(env.c, env.vb, "3a", "2025-06-30") is None


def test_dieu_status_giai_thich_vi_sao_khong_co(daapdung):
    env = daapdung
    assert "chưa từng có" in dieu_status(env.c, env.vb, "99")
    assert "được thêm vào từ 01/07/2025" in dieu_status(env.c, env.vb, "3a", "2025-06-30") and "86/2025/QH15" in dieu_status(env.c, env.vb, "3a", "2025-06-30")
    s = dieu_status(env.c, env.vb, "4", D3)
    assert "hết hiệu lực từ 01/01/2026" in s and "86/2025/QH15" in s and "Điều 2 khoản 1" in s
    assert "chưa có hiệu lực" in dieu_status(env.c, env.vb, "2", "2016-06-30")


def test_lich_su_dieu(daapdung):
    env = daapdung
    ev = lich_su_dieu(env.c, env.vb, "2")
    assert [(e.ngay, e.so_hieu, e.vi_tri_nguon, e.nut) for e in ev] == [(D1, "12/2017/QH14", "Điều 1 khoản 3", ["khoản 2 (sửa đổi)"])]
    ev3 = lich_su_dieu(env.c, env.vb, "3")
    assert [e.vi_tri_nguon for e in ev3] == ["Điều 1 khoản 4", "Điều 1 khoản 5"] and all(e.ngay == D1 for e in ev3)
    ev3a = lich_su_dieu(env.c, env.vb, "3a")
    assert len(ev3a) == 1 and ev3a[0].ngay == D2 and ev3a[0].nut[0].startswith("Điều 3a") and "(bổ sung)" in ev3a[0].nut[0]
    ev4 = lich_su_dieu(env.c, env.vb, "4")
    assert len(ev4) == 1 and ev4[0].ngay == D3 and ev4[0].nut == ["Điều 4 (bãi bỏ)"] and ev4[0].so_hieu == "86/2025/QH15"
    assert lich_su_dieu(env.c, env.vb, "5") == [] and lich_su_dieu(env.c, env.vb, "99") == []


def test_so_sanh_hai_thoi_diem(daapdung):
    env = daapdung
    d = so_sanh(env.c, env.vb, "2", "2017-12-31", D1)
    assert "-2. Người phạm tội tự thú được giảm nhẹ." in d.replace("  ", "") and "+2. Người phạm tội tự thú được miễn trách nhiệm hình sự." in d.replace("  ", "")
    assert so_sanh(env.c, env.vb, "2", D1, D3) == ""                          # không đổi giữa hai ngày
    d4 = so_sanh(env.c, env.vb, "4", D2, D3)                                  # Điều bị bãi bỏ: toàn bộ dòng bị xoá
    assert d4.count("\n-") >= 2 and "+Điều" not in d4


def test_dieu_khoan_hieu_luc_chuyen_tiep_gan_vao_van_ban_dich(daapdung):
    env = daapdung
    assert dieu_khoan_lien_quan(env.c, env.vb) == []                          # chưa nạp quan hệ / điều khoản trong fixture này
    for so_hieu, vt, loai, nd in [("12/2017/QH14", "Điều 3", "hieu_luc", "Luật này có hiệu lực từ 01/01/2018."),
                                  ("86/2025/QH15", "Điều 4", "chuyen_tiep", "Quy định chuyển tiếp.")]:
        a = env.c.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (so_hieu,)).fetchone()[0]
        env.c.execute("INSERT INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id) VALUES (?, 'sua_doi', ?)", (a, env.vb))
        env.c.execute("INSERT INTO dieu_khoan_van_ban (van_ban_id, loai, vi_tri, noi_dung) VALUES (?, ?, ?, ?)", (a, loai, vt, nd))
    rows = dieu_khoan_lien_quan(env.c, env.vb)
    assert [(r["so_hieu"], r["vi_tri"], r["loai"]) for r in rows] == [("12/2017/QH14", "Điều 3", "hieu_luc"), ("86/2025/QH15", "Điều 4", "chuyen_tiep")]


def test_luu_y_hieu_luc_chi_khi_chua_co_lenh_hoan(env):  # noqa: F811
    assert "01/07/2016" in luu_y_hieu_luc(env.c, env.vb)
    env.cmd("hoan_hieu_luc", None, tu="2016-06-01", nguon="41/2017/QH14", ban_hanh="2016-06-01", ngay_moi=D1, vi_tri="Điều 1")
    rebuild(env.c, env.vb)
    assert luu_y_hieu_luc(env.c, env.vb) is None
    assert get_dieu(env.c, env.vb, "2", "2017-06-01") is None and get_dieu(env.c, env.vb, "2", D1) is not None
