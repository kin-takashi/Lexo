"""Hiệu lực của cả văn bản: hoãn ngày bắt đầu (nghị quyết), ngày hết hiệu lực khi bị bộ luật mới thay, chọn bộ luật theo ngày,
và xem Điều «như khi Quốc hội thông qua» (goc=True)."""
import pytest

from src.apply.hieu_luc_vb import HieuLucError, dat_het_hieu_luc, ghi_hoan_hieu_luc
from src.apply.rebuild import rebuild
from src.ingest.base_law import ingest_base_law, stage_base_law
from src.query.lookup import get_dieu, luu_y_hieu_luc, ngay_cuoi_hieu_luc, render, van_ban_goc, van_ban_hieu_luc_tai
from src.store import connect, init_db

from test_apply_rebuild import BASE_LINES, Env, P
from test_ingest_lookup import approved_review, build_docx

MOI, CU = "99/2098/QH99", "10/2000/QH10"          # bộ luật mới (hiệu lực 2016-07-01) và bộ luật cũ (hiệu lực 2000-07-01)
D_CU, D_MOI = "2000-07-01", "2016-07-01"


def _dong_cu() -> list[str]:
    out = []
    for s in BASE_LINES:
        s = s.replace("01 tháng 07 năm 2016", "01 tháng 07 năm 2000").replace("27 tháng 11 năm 2015", "21 tháng 12 năm 1999")
        s = s.replace("khóa XIII", "khóa X").replace("phạt tù từ 03 năm đến 07 năm", "phạt tù từ 02 năm đến 05 năm")
        out.append(s)
    return out


@pytest.fixture
def hai(tmp_path):
    c = connect()
    init_db(c)
    ids = {}
    for ten, so_hieu, lines in (("CU", CU, _dong_cu()), ("MOI", MOI, BASE_LINES)):
        src = build_docx(tmp_path / f"{ten}.docx", lines, so_hieu=so_hieu)
        st = stage_base_law(src, tmp_path / "raw", ten_viet_tat="BLTN")
        approved_review(st)
        ids[ten] = ingest_base_law(c, st.directory, raw_root=tmp_path / "raw")["van_ban_id"]
    # luật sửa đổi riêng cho mỗi bộ luật (số hiệu nguồn khác nhau để không đụng UNIQUE)
    cu, moi = Env(c, ids["CU"]), Env(c, ids["MOI"])
    yield c, cu, moi
    c.close()


def _sua_khoan(env, tu, nguon, ban_hanh, noi_dung="2. Người phạm tội tự thú được miễn trách nhiệm hình sự."):
    return env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=tu, nguon=nguon, ban_hanh=ban_hanh,
                   noi_dung=noi_dung, vi_tri="Điều 1 khoản 1")


def test_hai_bo_luat_cung_ten_viet_tat_nap_dung_ngay(hai):
    c, cu, moi = hai
    ds = van_ban_goc(c, "BLTN")
    assert [r["so_hieu"] for r in ds] == [CU, MOI] and [r["ngay_hieu_luc"] for r in ds] == [D_CU, D_MOI]
    assert van_ban_goc(c, "KHAC") == []


def test_chon_bo_luat_theo_ngay_va_khoang_trong(hai):
    c, cu, moi = hai
    assert van_ban_hieu_luc_tai(c, "1999-12-31", "BLTN") is None                   # trước bộ luật đầu tiên
    assert van_ban_hieu_luc_tai(c, "2010-05-05", "BLTN")["so_hieu"] == CU          # bộ luật cũ chưa có ngày hết: vẫn là bộ cũ (bắt đầu sớm hơn)
    # bộ cũ chưa đặt ngày hết: hai bộ chồng nhau từ 2016-07-01 -> lấy bộ bắt đầu hiệu lực muộn hơn
    assert van_ban_hieu_luc_tai(c, "2016-07-01", "BLTN")["so_hieu"] == MOI
    r = dat_het_hieu_luc(c, CU, D_MOI, thay_boi=MOI)
    assert r["canh_bao"] == []
    assert van_ban_hieu_luc_tai(c, "2016-06-30", "BLTN")["so_hieu"] == CU
    assert van_ban_hieu_luc_tai(c, "2016-07-01", "BLTN")["so_hieu"] == MOI
    assert van_ban_hieu_luc_tai(c, "2099-01-01", "BLTN")["so_hieu"] == MOI


def test_ngay_cuoi_hieu_luc_la_hom_truoc_ngay_het(hai):
    c, cu, moi = hai
    assert ngay_cuoi_hieu_luc(van_ban_goc(c, "BLTN")[0]) is None
    dat_het_hieu_luc(c, CU, D_MOI)
    assert ngay_cuoi_hieu_luc(van_ban_goc(c, "BLTN")[0]) == "2016-06-30"
    assert ngay_cuoi_hieu_luc(van_ban_goc(c, "BLTN")[1]) is None


def test_dat_het_hieu_luc_cat_moi_phien_ban_dung_ngay(hai):
    c, cu, moi = hai
    _sua_khoan(cu, "2010-01-01", "37/2009/QH12", "2009-06-19")
    rebuild(c, cu.vb)
    assert cu.versions("dieu 2/khoan 2")[-1][1] is None                              # chưa đóng: bản sửa đổi còn mở
    dat_het_hieu_luc(c, CU, D_MOI, thay_boi=MOI)
    base, sua = cu.versions("dieu 2/khoan 2")
    assert (base[0], base[1]) == (D_CU, "2010-01-01") and (sua[0], sua[1]) == ("2010-01-01", D_MOI)
    assert cu.versions("dieu 4")[0][:2] == (D_CU, D_MOI)                             # nút không bị sửa cũng bị đóng
    assert "dieu 2/khoan 2" in cu.snap("2016-06-30") and cu.snap(D_MOI) == {}
    assert cu.snap("2012-01-01")["dieu 2/khoan 2"][1].endswith("miễn trách nhiệm hình sự.")
    assert cu.snap("2009-12-31")["dieu 2/khoan 2"][1] == "Người phạm tội tự thú được giảm nhẹ."
    # bộ luật mới không bị ảnh hưởng
    assert len(moi.snap(D_MOI)) == 17
    # quan hệ thay thế + trạng thái
    assert c.execute("SELECT loai_quan_he FROM quan_he_van_ban WHERE van_ban_a_id = ? AND van_ban_b_id = ?", (moi.vb, cu.vb)).fetchone()[0] == "thay_the"
    assert c.execute("SELECT trang_thai, ngay_het_hieu_luc FROM van_ban WHERE id = ?", (cu.vb,)).fetchone()[:] == ("het_hieu_luc", D_MOI)


def test_het_hieu_luc_ben_vung_sau_khi_dung_lai(hai):
    c, cu, moi = hai
    _sua_khoan(cu, "2010-01-01", "37/2009/QH12", "2009-06-19")
    dat_het_hieu_luc(c, CU, D_MOI)
    truoc = cu.dump()
    rebuild(c, cu.vb)
    assert cu.dump() == truoc


def test_luat_sua_doi_hieu_luc_sau_ngay_het_thanh_khoang_rong(hai):
    c, cu, moi = hai
    _sua_khoan(cu, "2017-01-01", "37/2009/QH12", "2009-06-19")                       # dữ liệu bất thường: sau khi bộ cũ đã hết hiệu lực
    dat_het_hieu_luc(c, CU, D_MOI)
    base, sua = cu.versions("dieu 2/khoan 2")
    assert (base[0], base[1]) == (D_CU, D_MOI) and sua[0] == sua[1] == "2017-01-01"
    assert all("dieu 2/khoan 2" not in cu.snap(d) or d < D_MOI for d in ("2016-07-01", "2017-01-01", "2030-01-01"))
    assert cu.snap("2030-01-01") == {}


def test_dat_het_hieu_luc_canh_bao_khoang_trong_va_loi(hai):
    c, cu, moi = hai
    r = dat_het_hieu_luc(c, CU, "2016-01-01", thay_boi=MOI)
    assert len(r["canh_bao"]) == 1 and "khoảng trống" in r["canh_bao"][0]
    with pytest.raises(HieuLucError):
        dat_het_hieu_luc(c, CU, "2000-07-01")                                        # không sau ngày bắt đầu
    with pytest.raises(HieuLucError):
        dat_het_hieu_luc(c, CU, "01/07/2016")
    with pytest.raises(HieuLucError):
        dat_het_hieu_luc(c, "000/0000/XX", "2016-07-01")
    with pytest.raises(HieuLucError):
        dat_het_hieu_luc(c, CU, "2016-07-01", thay_boi="000/0000/XX")


# ---------- hoãn hiệu lực ----------

NQ = dict(so_hieu_nguon="144/2016/QH13", ten_nguon="Nghị quyết số 144/2016/QH13 về việc lùi hiệu lực thi hành của bộ luật thử nghiệm",
          ngay_ban_hanh_nguon="2016-06-29", can_cu="Nghị quyết 144/2016/QH13", nguoi="pytest")


def test_hoan_hieu_luc_doi_ngay_bat_dau_va_giu_nguon(hai):
    c, cu, moi = hai
    D1 = "2018-01-01"
    _sua_khoan(moi, D1, "12/2017/QH14", "2017-06-20")
    rebuild(c, moi.vb)
    assert moi.snap("2017-12-31")                                                   # trước khi hoãn: bộ luật có hiệu lực từ 2016-07-01
    assert luu_y_hieu_luc(c, moi.vb) is not None                                    # chưa có nghị quyết hoãn: còn cảnh báo
    r = ghi_hoan_hieu_luc(c, MOI, D1, **NQ)
    assert not r["da_co"] and r["ngay_cu"] == D_MOI and r["bao_cao"].n_loi == 0
    vb = c.execute("SELECT * FROM van_ban WHERE id = ?", (moi.vb,)).fetchone()
    assert vb["ngay_hieu_luc"] == D1 and vb["ngay_hieu_luc_theo_van_ban"] == D_MOI      # ngày theo văn bản giữ nguyên, ngày hiệu lực thực tế đổi
    assert moi.snap("2017-12-31") == {}                                              # trước 2018 chưa có hiệu lực
    s = moi.snap(D1)
    assert len(s) == 17 and s["dieu 2/khoan 2"][1].endswith("miễn trách nhiệm hình sự.")
    assert luu_y_hieu_luc(c, moi.vb) is None                                         # đã có nghị quyết hoãn đã duyệt
    # nguồn gốc: văn bản nguồn + nhật ký + lệnh đã duyệt + quan hệ
    lenh = c.execute("SELECT * FROM lenh_sua_doi WHERE id = ?", (r["lenh_id"],)).fetchone()
    assert (lenh["loai_thao_tac"], lenh["trang_thai_duyet"], lenh["nguoi_duyet"], lenh["ngay_hieu_luc_moi"], lenh["hieu_luc_tu"]) == \
        ("hoan_hieu_luc", "da_duyet", "pytest", D1, "2016-06-29")
    assert c.execute("SELECT loai, ngay_ban_hanh FROM van_ban WHERE so_hieu = '144/2016/QH13'").fetchone()[:] == ("nghi_quyet", "2016-06-29")
    assert c.execute("SELECT COUNT(*) FROM quan_he_van_ban WHERE van_ban_a_id = ? AND loai_quan_he = 'hoan_hieu_luc' AND van_ban_b_id = ?",
                     (r["van_ban_nguon_id"], moi.vb)).fetchone()[0] == 1
    # dựng lại nhiều lần vẫn cùng kết quả
    truoc = moi.dump()
    rebuild(c, moi.vb)
    assert moi.dump() == truoc


def test_hoan_hieu_luc_idempotent(hai):
    c, cu, moi = hai
    a = ghi_hoan_hieu_luc(c, MOI, "2018-01-01", **NQ)
    dem = lambda: [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("van_ban", "log_nap", "lenh_sua_doi", "quan_he_van_ban")]  # noqa: E731
    truoc = dem()
    b = ghi_hoan_hieu_luc(c, MOI, "2018-01-01", **NQ)
    assert b["da_co"] and b["lenh_id"] == a["lenh_id"] and dem() == truoc


def test_hoan_hieu_luc_loi_dau_vao(hai):
    c, cu, moi = hai
    truoc = moi.dump()
    for kw, ngay in (({}, "01/01/2018"), ({"nguoi": " "}, "2018-01-01"), ({"can_cu": ""}, "2018-01-01"), ({"ngay_ban_hanh_nguon": "29-06-2016"}, "2018-01-01")):
        with pytest.raises(HieuLucError):
            ghi_hoan_hieu_luc(c, MOI, ngay, **{**NQ, **kw})
    with pytest.raises(HieuLucError):
        ghi_hoan_hieu_luc(c, "000/0000/XX", "2018-01-01", **NQ)
    assert c.execute("SELECT COUNT(*) FROM van_ban WHERE so_hieu = '144/2016/QH13'").fetchone()[0] == 0 and moi.dump() == truoc


def test_xem_dieu_nhu_khi_thong_qua_khi_luat_sua_doi_cung_ngay_hieu_luc(hai):
    """Luật sửa đổi hiệu lực CÙNG ngày với bộ luật (BLHS 2015 + Luật 12/2017): bản gốc của Điều bị sửa chưa từng có hiệu lực,
    nhưng vẫn phải xem được nguyên văn Quốc hội thông qua."""
    c, cu, moi = hai
    D1 = "2018-01-01"
    _sua_khoan(moi, D1, "12/2017/QH14", "2017-06-20")
    ghi_hoan_hieu_luc(c, MOI, D1, **NQ)
    cuoi = get_dieu(c, moi.vb, "2", D1)
    assert "miễn trách nhiệm hình sự" in render(cuoi) and cuoi.children[1].nguon                    # bản có hiệu lực: đã sửa, kèm nguồn
    goc = get_dieu(c, moi.vb, "2", D1, goc=True)
    assert "giảm nhẹ" in render(goc) and "miễn trách nhiệm" not in render(goc)
    assert [u.nguon for u in goc.walk() if u.nguon] == []                                          # bản gốc: không có nguồn sửa đổi
    assert get_dieu(c, moi.vb, "2", "2017-12-31") is None                                          # trước 2018: chưa có hiệu lực
    assert get_dieu(c, moi.vb, "2", "2017-12-31", goc=True) is not None                            # nhưng nguyên văn thông qua vẫn xem được
    # Điều do lệnh bổ sung tạo ra không có bản gốc
    moi.cmd("bo_sung", {"cha": P("dieu", "3"), "sau": P("dieu", "3", "khoan", "2"), "loai": "khoan", "ky_hieu": "3"}, tu="2025-07-01",
            nguon="86/2025/QH15", ban_hanh="2025-06-25", noi_dung="3. Khoản ba mới.", vi_tri="Điều 1 khoản 5")
    rebuild(c, moi.vb)
    d3 = get_dieu(c, moi.vb, "3", "2026-01-01")
    d3g = get_dieu(c, moi.vb, "3", "2026-01-01", goc=True)
    assert [k.ky_hieu for k in d3.children] == ["1", "2", "3"] and [k.ky_hieu for k in d3g.children] == ["1", "2"]
