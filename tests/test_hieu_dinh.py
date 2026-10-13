"""Lớp hiệu đính kỹ thuật (src/apply/hieu_dinh.py): đề xuất -> người duyệt -> áp lên mọi phiên bản; tích hợp rebuild và tra cứu.
Dữ liệu là bộ luật thử nghiệm (không phải số liệu pháp lý thật)."""
import json
import sqlite3

import pytest

from src.apply import hieu_dinh as hd
from src.apply.rebuild import preview, rebuild
from src.query.lookup import get_dieu, hieu_dinh_cho_duyet_dieu, render, so_hieu_dinh_cho_duyet
from src.store import connect, init_db

from test_apply_rebuild import D1, P, env  # noqa: F401  (env là fixture)

K1 = "dieu 3/khoan 1"
GOC = "Người nào trộm cắp tài sản thì bị phạt tù từ 01 năm đến 03 năm."


def de_xuat(khoa=K1, tu_cu="trộm cắp tài sản thì bị", thanh_moi="trộm cắp tài sản thì sẽ bị", loai="loi_go", truong="noi_dung", **bc):
    return {"khoa": khoa, "truong": truong, "tu_cu": tu_cu, "thanh_moi": thanh_moi, "loai": loai,
            "bang_chung": {"nguon_so_sanh": "135/VBHN-VPQH (bản hệ thống ngày 2026-01-01)", "tham_chieu": {"11/VBHN-VPQH": "cung_sua"}, **bc}}


def them(env, *ds, nguoi=None, **kw):  # noqa: F811
    hd.luu_de_xuat(env.c, env.vb, list(ds))
    if nguoi:
        hd.duyet(env.c, env.vb, nguoi=nguoi, **kw)
    env.c.commit()


def sua_khoan_3_1(env):  # noqa: F811
    """Điều 3 khoản 1 được luật sửa đổi viết lại từ D1: có hai phiên bản, cả hai đều chứa cụm 'trộm cắp tài sản thì bị'."""
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1,
            noi_dung="1. Người nào trộm cắp tài sản thì bị phạt tù từ 02 năm đến 04 năm.", vi_tri="Điều 1 khoản 4")


# ---------- lưu / duyệt ----------


def test_luu_de_xuat_idempotent_va_kiem_tra_loai(env):  # noqa: F811
    assert hd.luu_de_xuat(env.c, env.vb, [de_xuat(), de_xuat(tu_cu="phạt tù", thanh_moi="phạt giam")]) == (2, 0)
    assert hd.luu_de_xuat(env.c, env.vb, [de_xuat()]) == (0, 1)                       # đã có: giữ nguyên
    assert env.c.execute("SELECT COUNT(*), MIN(trang_thai_duyet) FROM hieu_dinh").fetchone()[:] == (2, "cho_duyet")
    with pytest.raises(hd.HieuDinhError):
        hd.luu_de_xuat(env.c, env.vb, [de_xuat(loai="khong_co_loai_nay")])


def test_duyet_phai_co_ten_nguoi_va_chon_duoc_theo_id_hoac_loai(env):  # noqa: F811
    them(env, de_xuat(), de_xuat(tu_cu="phạt tù", thanh_moi="phạt giam"),
         de_xuat(tu_cu="01 năm", thanh_moi="05 năm", loai="sai_so_lieu"))
    for ten in ("", "   "):
        with pytest.raises(hd.HieuDinhError):
            hd.duyet(env.c, env.vb, nguoi=ten)
    assert env.c.execute("SELECT COUNT(*) FROM hieu_dinh WHERE trang_thai_duyet <> 'cho_duyet'").fetchone()[0] == 0   # chưa gì được duyệt
    assert hd.duyet(env.c, env.vb, nguoi="Người duyệt", loai=["loi_go"], ghi_chu="đã đọc") == 2
    r = env.c.execute("SELECT * FROM hieu_dinh WHERE loai = 'sai_so_lieu'").fetchone()
    assert r["trang_thai_duyet"] == "cho_duyet" and r["nguoi_duyet"] is None            # số liệu chưa được duyệt theo loại khác
    assert hd.duyet(env.c, env.vb, nguoi="Người duyệt", ids=[r["id"]], tu_choi=True) == 1
    assert env.c.execute("SELECT trang_thai_duyet, nguoi_duyet FROM hieu_dinh WHERE id = ?", (r["id"],)).fetchone()[:] == ("tu_choi", "Người duyệt")
    assert hd.duyet(env.c, env.vb, nguoi="Người duyệt") == 0                             # không còn gì chờ duyệt


# ---------- áp lên phiên bản ----------


def test_ap_dung_len_moi_phien_ban_giu_ban_goc(env):  # noqa: F811
    sua_khoan_3_1(env)
    them(env, de_xuat(), nguoi="Người duyệt")
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 1 and rep.hieu_dinh.n_ap == 1 and rep.hieu_dinh.khong_ap_duoc() == []
    kq = rep.hieu_dinh.ket_qua[0]
    assert (kq.n_phien_ban, kq.n_mo_ho, kq.co_nut) == (2, 0, True)
    assert env.snap("2017-12-31")[K1][1].startswith("Người nào trộm cắp tài sản thì sẽ bị phạt tù từ 01 năm")
    assert env.snap(D1)[K1][1] == "Người nào trộm cắp tài sản thì sẽ bị phạt tù từ 02 năm đến 04 năm."
    rows = env.c.execute("SELECT noi_dung, noi_dung_goc, hieu_dinh_json FROM phien_ban_noi_dung WHERE noi_dung_goc IS NOT NULL ORDER BY hieu_luc_tu").fetchall()
    assert [r["noi_dung_goc"] for r in rows] == [GOC, "Người nào trộm cắp tài sản thì bị phạt tù từ 02 năm đến 04 năm."]   # như luật ban hành
    assert all(json.loads(r["hieu_dinh_json"]) == [1] for r in rows)
    assert env.c.execute("SELECT COUNT(*) FROM phien_ban_noi_dung WHERE noi_dung_goc IS NULL AND hieu_dinh_json IS NOT NULL").fetchone()[0] == 0


def test_chua_duyet_hoac_bi_tu_choi_thi_khong_ap(env):  # noqa: F811
    them(env, de_xuat(), de_xuat(tu_cu="phạt tù", thanh_moi="phạt giam"))
    hd.duyet(env.c, env.vb, nguoi="Người duyệt", ids=[2], tu_choi=True)
    env.c.commit()
    rep = rebuild(env.c, env.vb)
    assert rep.hieu_dinh.ket_qua == [] and env.snap("2017-12-31")[K1][1] == GOC          # một chờ duyệt, một từ chối: bản vẫn như ban hành
    assert env.c.execute("SELECT COUNT(*) FROM phien_ban_noi_dung WHERE noi_dung_goc IS NOT NULL").fetchone()[0] == 0


def test_xem_truoc_ap_ca_de_xuat_cho_duyet_nhung_khong_dung_csdl_that(env):  # noqa: F811
    them(env, de_xuat())
    rep, mem = preview(env.c, env.vb)
    try:
        assert rep.hieu_dinh.n_ap == 1
        assert mem.execute("SELECT noi_dung FROM phien_ban_noi_dung WHERE noi_dung LIKE '%thì sẽ bị%'").fetchone() is not None
    finally:
        mem.close()
    assert env.snap("2017-12-31")[K1][1] == GOC                                       # CSDL thật không đổi
    assert rebuild(env.c, env.vb).hieu_dinh.ket_qua == []


def test_quy_tac_cu_mo_ho_va_khong_co_nut(env):  # noqa: F811
    them(env,
         de_xuat(tu_cu="không có trong văn bản", thanh_moi="x"),             # cũ: không còn chỗ nào chứa
         de_xuat(khoa="dieu 2/khoan 1", tu_cu="vi", thanh_moi="VI"),            # mơ hồ: "vi" xuất hiện nhiều chỗ
         de_xuat(khoa="dieu 99", tu_cu="a", thanh_moi="b"),                     # không có nút
         nguoi="Người duyệt")
    rep = rebuild(env.c, env.vb)
    a, b, c = rep.hieu_dinh.ket_qua
    assert (a.n_phien_ban, a.co_nut) == (0, True) and a.cu
    assert (b.n_phien_ban, b.n_mo_ho) == (0, 1) and b.cu
    assert (c.n_phien_ban, c.co_nut) == (0, False)
    assert rep.hieu_dinh.n_ap == 0 and len(rep.hieu_dinh.khong_ap_duoc()) == 3
    assert env.snap("2017-12-31")["dieu 2/khoan 1"][1].startswith("Mọi hành vi vi phạm")   # không bị đụng tới


def test_tieu_de(env):  # noqa: F811
    them(env, de_xuat(khoa="dieu 4", truong="tieu_de", tu_cu="lừa đảo", thanh_moi="lừa gạt"), nguoi="Người duyệt")
    rebuild(env.c, env.vb)
    assert env.snap("2017-12-31")["dieu 4"][0] == "Tội lừa gạt"
    assert env.c.execute("SELECT tieu_de_goc FROM phien_ban_noi_dung WHERE tieu_de_goc IS NOT NULL").fetchone()[0] == "Tội lừa đảo"


def test_rebuild_tat_dinh_va_khoi_phuc(env):  # noqa: F811
    sua_khoan_3_1(env)
    them(env, de_xuat(), nguoi="Người duyệt")
    rebuild(env.c, env.vb)
    truoc = env.dump()
    rebuild(env.c, env.vb)
    assert env.dump() == truoc                                                      # chạy lại không áp chồng, không đổi
    assert hd.khoi_phuc(env.c, env.vb) == 2
    assert env.snap(D1)[K1][1] == "Người nào trộm cắp tài sản thì bị phạt tù từ 02 năm đến 04 năm."
    assert env.c.execute("SELECT COUNT(*) FROM phien_ban_noi_dung WHERE noi_dung_goc IS NOT NULL OR hieu_dinh_json IS NOT NULL").fetchone()[0] == 0
    assert hd.khoi_phuc(env.c, env.vb) == 0
    env.c.execute("UPDATE hieu_dinh SET trang_thai_duyet = 'tu_choi' WHERE id = 1")   # đổi quyết định rồi dựng lại -> văn bản như ban hành
    env.c.commit()
    rebuild(env.c, env.vb)
    assert env.snap("2017-12-31")[K1][1] == GOC


def test_luat_sua_doi_sau_do_thay_doan_thi_chi_phien_ban_cu_duoc_hieu_dinh(env):  # noqa: F811
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1,
            noi_dung="1. Người nào trộm cắp tài sản thì phạt tù từ 02 năm đến 04 năm.", vi_tri="Điều 1 khoản 4")   # bản mới không còn cụm cũ
    them(env, de_xuat(), nguoi="Người duyệt")
    rep = rebuild(env.c, env.vb)
    kq = rep.hieu_dinh.ket_qua[0]
    assert kq.n_phien_ban == 1 and not kq.cu
    assert "sẽ bị" in env.snap("2017-12-31")[K1][1] and "sẽ bị" not in env.snap(D1)[K1][1]


def test_dieu_ap_dung(env):  # noqa: F811
    sua_khoan_3_1(env)
    them(env, de_xuat(), nguoi="Người duyệt")
    rebuild(env.c, env.vb)
    k1 = next(r["don_vi_id"] for r in env.c.execute("SELECT don_vi_id FROM phien_ban_noi_dung WHERE noi_dung_goc IS NOT NULL"))
    assert [r["tu_cu"] for r in hd.dieu_ap_dung(env.c, k1, "2016-07-01")] == ["trộm cắp tài sản thì bị"]
    assert [r["id"] for r in hd.dieu_ap_dung(env.c, k1, D1)] == [1]
    assert hd.dieu_ap_dung(env.c, k1, "1999-01-01") == []


# ---------- xuất / nạp ----------


def test_xuat_nap_giu_quyet_dinh_qua_init_db_reset(env):  # noqa: F811
    them(env, de_xuat(bang_chung_them=1), de_xuat(tu_cu="phạt tù", thanh_moi="phạt giam"), de_xuat(tu_cu="01 năm", thanh_moi="05 năm", loai="sai_so_lieu"))
    hd.duyet(env.c, env.vb, nguoi="Người duyệt", ids=[1], ghi_chu="ok")
    hd.duyet(env.c, env.vb, nguoi="Người duyệt", ids=[3], tu_choi=True)
    env.c.commit()
    file = json.loads(json.dumps(hd.xuat(env.c, env.vb)))                           # qua JSON như file hieu_dinh.json
    assert [r["trang_thai_duyet"] for r in file] == ["da_duyet", "cho_duyet", "tu_choi"]
    # CSDL mới: nạp lại -> quyết định còn nguyên
    c2 = connect()
    init_db(c2)
    vb2 = c2.execute("INSERT INTO van_ban (so_hieu, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban, ngay_hieu_luc) "
                     "VALUES ('X', 'X', 'luat', '2015-01-01', '2016-01-01', '2016-01-01')").lastrowid
    assert hd.nap(c2, vb2, file) == (3, 0)
    assert hd.nap(c2, vb2, file) == (0, 0)                                          # nạp lại không nhân đôi
    assert [(r["trang_thai_duyet"], r["nguoi_duyet"], r["ghi_chu_duyet"]) for r in hd.xuat(c2, vb2)] == \
        [("da_duyet", "Người duyệt", "ok"), ("cho_duyet", None, None), ("tu_choi", "Người duyệt", None)]
    assert hd.xuat(c2, vb2)[0]["bang_chung"]["bang_chung_them"] == 1
    # quy tắc đang chờ duyệt trong CSDL thì nhận quyết định từ file; quy tắc đã quyết định thì không bị file ghi đè
    c3 = connect()
    init_db(c3)
    vb3 = c3.execute("INSERT INTO van_ban (so_hieu, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban, ngay_hieu_luc) "
                     "VALUES ('X', 'X', 'luat', '2015-01-01', '2016-01-01', '2016-01-01')").lastrowid
    hd.luu_de_xuat(c3, vb3, [de_xuat(), de_xuat(tu_cu="phạt tù", thanh_moi="phạt giam")])
    c3.execute("UPDATE hieu_dinh SET trang_thai_duyet = 'tu_choi', nguoi_duyet = 'Khác', ngay_duyet = '2026-01-01' WHERE tu_cu = 'phạt tù'")
    assert hd.nap(c3, vb3, file) == (1, 1)                                         # thêm quy tắc số liệu; cập nhật quy tắc 1
    st = {r["tu_cu"]: (r["trang_thai_duyet"], r["nguoi_duyet"]) for r in hd.xuat(c3, vb3)}
    assert st["trộm cắp tài sản thì bị"] == ("da_duyet", "Người duyệt") and st["phạt tù"] == ("tu_choi", "Khác")


def test_rang_buoc_csdl_chi_duyet_khi_co_nguoi(env):  # noqa: F811
    hd.luu_de_xuat(env.c, env.vb, [de_xuat()])
    with pytest.raises(sqlite3.IntegrityError):
        env.c.execute("UPDATE hieu_dinh SET trang_thai_duyet = 'da_duyet'")          # không có người duyệt/ngày duyệt thì CSDL từ chối
    with pytest.raises(sqlite3.IntegrityError):
        env.c.execute("UPDATE hieu_dinh SET thanh_moi = tu_cu")                      # từ cũ = từ mới vô nghĩa


# ---------- tra cứu ----------


def test_tra_cuu_ghi_chu_nguyen_van_va_thong_bao_cho_duyet(env):  # noqa: F811
    sua_khoan_3_1(env)
    them(env, de_xuat(xac_minh=[{"nguon": "Công báo số 1263, tr. 7"}]), nguoi="Người duyệt")
    them(env, de_xuat(khoa="dieu 3/khoan 2", tu_cu="tái phạm", thanh_moi="tái phạm nhiều lần"))        # còn chờ duyệt
    rebuild(env.c, env.vb)
    u = get_dieu(env.c, env.vb, "3", D1)
    k1 = next(c for c in u.children if c.ky_hieu == "1")
    assert k1.noi_dung == "Người nào trộm cắp tài sản thì sẽ bị phạt tù từ 02 năm đến 04 năm."
    h = k1.hieu_dinh[0]
    assert (h["tu_cu"], h["thanh_moi"], h["nguoi_duyet"], h["nguon_so_sanh"].split(" (")[0], h["da_kiem_nguon"]) == \
        ("trộm cắp tài sản thì bị", "trộm cắp tài sản thì sẽ bị", "Người duyệt", "135/VBHN-VPQH", ["Công báo số 1263, tr. 7"])
    text = render(u, ghi_chu=True)
    assert "[hiệu đính kỹ thuật: “trộm cắp tài sản thì bị” → “trộm cắp tài sản thì sẽ bị” (theo 135/VBHN-VPQH, đã kiểm Công báo; duyệt: Người duyệt)]" in text
    assert "[hiệu đính" not in render(u)                                                                   # mặc định không kèm ghi chú
    # nguyên văn: như luật ban hành, không ghi chú hiệu đính
    ng = get_dieu(env.c, env.vb, "3", D1, nguyen_van=True)
    k1n = next(c for c in ng.children if c.ky_hieu == "1")
    assert k1n.noi_dung == "Người nào trộm cắp tài sản thì bị phạt tù từ 02 năm đến 04 năm." and k1n.hieu_dinh == []
    assert "hiệu đính" not in render(ng, ghi_chu=True)
    # nút không bị hiệu đính thì không có ghi chú
    assert all(c.hieu_dinh == [] for c in u.children if c.ky_hieu != "1")
    # đề xuất chưa duyệt chỉ được báo, không áp
    assert so_hieu_dinh_cho_duyet(env.c, env.vb) == 1
    assert [r["khoa"] for r in hieu_dinh_cho_duyet_dieu(env.c, env.vb, "3")] == ["dieu 3/khoan 2"]
    assert hieu_dinh_cho_duyet_dieu(env.c, env.vb, "4") == [] and hieu_dinh_cho_duyet_dieu(env.c, env.vb, "30") == []   # 'dieu 30' không lẫn vào 'dieu 3'
    assert "tái phạm nhiều lần" not in render(u)
