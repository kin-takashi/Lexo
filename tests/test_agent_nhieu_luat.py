"""Agent khi kho có NHIỀU bộ luật nối tiếp nhau (BLHS 1999 → BLHS 2015): tự chọn bộ luật theo thời gian hiệu lực của từng bộ luật, và nói rõ khi
ngày được chọn thuộc thời kỳ kho chưa nạp. Kho thử mô phỏng đúng thực tế: bộ cũ 15/1999/QH10 (hiệu lực 01/07/2000, hết 01/01/2018, sửa đổi
01/01/2010), bộ mới 100/2015/QH13 (ghi trong văn bản 01/07/2016, nghị quyết lùi sang 01/01/2018, Luật 12/2017/QH14 sửa đổi từ đúng ngày đó)."""
from types import SimpleNamespace

import pytest

from src.agent import y_dinh as yd
from src.agent.agent import Agent, thanh_van_ban
from src.agent.cong_cu import CongCu, _kiem_tra_chi_muc_cu
from src.apply.hieu_luc_vb import dat_het_hieu_luc, ghi_hoan_hieu_luc
from src.apply.rebuild import rebuild
from src.index.embedder import HashEmbedder
from src.index.tach_hanh_vi import LLMGiaTach
from src.ingest.base_law import ingest_base_law, stage_base_law
from src.store import connect, init_db

from test_apply_rebuild import BASE_LINES, Env, P
from test_hieu_luc_vb import _dong_cu, _sua_khoan
from test_index import dung_chi_muc
from test_ingest_lookup import approved_review, build_docx

CU, MOI = "15/1999/QH10", "100/2015/QH13"
NQ = dict(so_hieu_nguon="41/2017/QH14", ten_nguon="Nghị quyết số 41/2017/QH14 về việc thi hành Bộ luật hình sự số 100/2015/QH13",
          ngay_ban_hanh_nguon="2017-06-20", hieu_luc_tu="2017-07-05", can_cu="Điều 1 khoản 1 điểm a Nghị quyết 41/2017/QH14", nguoi="pytest",
          vi_tri_nguon="Điều 1 khoản 1 điểm a")


def dung_kho(tmp_path, *, co_cu=True, co_chi_muc=True, ten="kho"):
    tmp_path = tmp_path / ten
    tmp_path.mkdir()
    c = connect()
    init_db(c)
    ids = {}
    for ten, so_hieu, lines in ((("CU", CU, _dong_cu()),) if co_cu else ()) + (("MOI", MOI, BASE_LINES),):
        st = stage_base_law(build_docx(tmp_path / f"{ten}.docx", lines, so_hieu=so_hieu), tmp_path / "raw", ten_viet_tat="BLHS")
        approved_review(st)
        ids[ten] = ingest_base_law(c, st.directory, raw_root=tmp_path / "raw")["van_ban_id"]
    moi = Env(c, ids["MOI"])
    _sua_khoan(moi, "2018-01-01", "12/2017/QH14", "2017-06-20")
    rebuild(c, moi.vb)
    ghi_hoan_hieu_luc(c, MOI, "2018-01-01", **NQ)
    cu = None
    if co_cu:
        cu = Env(c, ids["CU"])
        _sua_khoan(cu, "2010-01-01", "37/2009/QH12", "2009-06-19", noi_dung="2. Người phạm tội tự thú được miễn án phạt.")
        rebuild(c, cu.vb)
        dat_het_hieu_luc(c, CU, "2018-01-01", thay_boi=MOI)
    idx = emb = None
    if co_chi_muc:
        idx, emb = dung_chi_muc(moi, tmp_path)
    cc = CongCu(c, idx, embedder=emb, tach_llm=LLMGiaTach(), tach_ten="gia")
    return SimpleNamespace(c=c, cu=cu, moi=moi, cc=cc, ag=Agent(cc), idx=idx)


@pytest.fixture
def hai(tmp_path):
    k = dung_kho(tmp_path, ten="hai")
    yield k
    k.c.close()


@pytest.fixture
def mot(tmp_path):
    """Chỉ có BLHS 2015 (như kho thật hiện nay); BLHS 1999 và 1985 là các thời kỳ đã biết nhưng chưa nạp."""
    k = dung_kho(tmp_path, co_cu=False, ten="mot")
    yield k
    k.c.close()


# ------------------------------------------------------------------------------------------------ chọn bộ luật theo ngày

def test_ngay_truoc_2018_dung_bo_luat_cu(hai):
    tl = hai.ag.hoi("Điều 2 ngày 05/05/2010")
    assert tl.trang_thai == "ok" and "15/1999/QH10" in tl.dieu[0].van_ban and "BLHS 1999" in tl.tom_tat
    assert "miễn án phạt" in tl.dieu[0].markdown and "12/2017" not in "".join(tl.dieu[0].nguon) and "37/2009/QH12" in tl.dieu[0].nguon[0]
    assert (tl.dieu[0].hieu_luc_tu, tl.dieu[0].hieu_luc_den) == ("2010-01-01", "2018-01-01")
    assert "giảm nhẹ" in hai.ag.hoi("Điều 2 ngày 31/12/2009").dieu[0].markdown            # trước sửa đổi 2010 của bộ cũ
    tl = hai.ag.hoi("Điều 2 ngày 31/12/2017")
    assert "15/1999/QH10" in tl.dieu[0].van_ban and "miễn án phạt" in tl.dieu[0].markdown


def test_tu_2018_dung_bo_luat_moi_kem_nguon(hai):
    tl = hai.ag.hoi("Điều 2 ngày 01/01/2018")
    assert "100/2015/QH13" in tl.dieu[0].van_ban and "BLHS 2015" in tl.tom_tat
    assert "miễn trách nhiệm hình sự" in tl.dieu[0].markdown and "12/2017/QH14" in tl.dieu[0].nguon[0]
    d = hai.ag.hoi("Điều 2").dieu[0]                                                      # hôm nay
    assert "100/2015/QH13" in d.van_ban and d.hieu_luc_tu == "2018-01-01"
    assert hai.ag.hoi("Điều 2", ngay="2010-05-05").dieu[0].van_ban.startswith("BLHS (15/1999/QH10)")       # ngày chọn ở thanh bên


def test_ranh_gioi_giua_hai_bo_luat_la_nua_mo(hai):
    r = hai.cc.van_ban_tai_ngay
    assert r("2017-12-31").vb["so_hieu"] == CU and r("2018-01-01").vb["so_hieu"] == MOI
    assert r("2000-06-30").vb is None and r("2000-07-01").vb["so_hieu"] == CU


def test_ngay_thuoc_thoi_ky_chua_nap_noi_ro(hai):
    tl = hai.ag.hoi("Điều 2 ngày 01/01/1990")
    assert tl.trang_thai == "khong_co" and not tl.dieu
    msg = " ".join(tl.thong_bao)
    assert "Bộ luật hình sự năm 1985" in msg and "chưa nạp" in msg and "BLHS 1999" in msg        # kèm các bộ luật kho đang có


def test_kho_chi_co_blhs_2015_ngay_2010_giai_thich_blhs_1999(mot):
    tl = mot.ag.hoi("Điều 2 ngày 05/05/2010")
    assert tl.trang_thai == "khong_co" and not tl.dieu
    msg = " ".join(tl.thong_bao)
    assert "05/05/2010" in msg and "Bộ luật hình sự năm 1999" in msg and "01/07/2000" in msg and "31/12/2017" in msg
    assert "chưa nạp" in msg and "BLHS 2015 (hiệu lực từ 01/01/2018" in msg
    assert mot.ag.hoi("Điều 2 ngày 31/12/2017").trang_thai == "khong_co" and mot.ag.hoi("Điều 2 ngày 01/01/2018").dieu


def test_ngay_chon_o_thanh_ben_truoc_2018_cho_moi_loai_cau(mot):
    for cau in ("Điều 2", "lén lấy xe máy của hàng xóm", "so sánh Điều 2"):
        tl = mot.ag.hoi(cau, ngay="2010-05-05")
        assert any("Bộ luật hình sự năm 1999" in x or "chưa có hiệu lực" in x for x in tl.thong_bao), cau
    tl = mot.ag.hoi(TINH_HUONG_DAI, ngay="2010-05-05")
    assert tl.trang_thai == "khong_co" and not any(h.dieu for h in tl.hanh_vi) and any("Bộ luật hình sự năm 1999" in x for x in tl.thong_bao)
    assert mot.ag.lay_dieu("2", "2010-05-05") is None and mot.ag.lay_dieu("2", "2018-01-01") is not None


TINH_HUONG_DAI = "Anh A trộm cắp tài sản của người khác. Sau đó anh A lừa đảo chiếm đoạt tiền của bà B rồi bỏ trốn khỏi địa phương nhiều tháng."


# ------------------------------------------------------------------------------------------------ nêu rõ bộ luật

def test_neu_blhs_1999_hoac_2009_khi_chua_nap_hoac_da_nap(mot, hai):
    for cau in ("Điều 2 BLHS 1999", "Điều 2 BLHS 2009"):
        tl = mot.ag.hoi(cau)
        assert tl.trang_thai == "khong_co" and any("chưa nạp Bộ luật hình sự năm 1999" in x for x in tl.thong_bao), cau
        tl = hai.ag.hoi(cau)                                                               # kho có bộ cũ: không ngày thì lấy bản cuối cùng của nó
        assert tl.trang_thai == "ok" and "15/1999/QH10" in tl.dieu[0].van_ban and tl.ngay == "2017-12-31"
        assert any("đã hết hiệu lực từ 01/01/2018" in x and "ngày cuối cùng (31/12/2017)" in x for x in tl.thong_bao)
        assert "miễn án phạt" in tl.dieu[0].markdown


def test_neu_bo_luat_nhung_ngay_ngoai_thoi_gian_hieu_luc(hai):
    tl = hai.ag.hoi("Điều 2 BLHS 2015 ngày 05/05/2010")
    assert tl.trang_thai == "khong_co" and not tl.dieu
    msg = " ".join(tl.thong_bao)
    assert "BLHS 2015 chỉ có hiệu lực từ 01/01/2018" in msg and "bộ luật đang áp dụng là BLHS 1999" in msg
    tl = hai.ag.hoi("Điều 2 BLHS 1999 ngày 01/01/2020")
    assert tl.trang_thai == "khong_co" and "BLHS 1999 đã hết hiệu lực từ 01/01/2018" in " ".join(tl.thong_bao)
    assert "BLHS 2015" in " ".join(tl.thong_bao)                                          # nói bộ luật đang áp dụng lúc đó


def test_phan_loai_nam_bo_luat_da_biet(hai, mot):
    assert {1985, 1999, 2015} <= mot.cc.nam_van_ban() and {1985, 1999, 2015} <= hai.cc.nam_van_ban()
    y = yd.phan_loai("Điều 2 năm 1999", nam_van_ban=mot.cc.nam_van_ban())
    assert y.nam_van_ban == 1999 and not y.moc                                              # năm của văn bản, không phải ngày cần xem


# ------------------------------------------------------------------------------------------------ bản gốc, lịch sử, so sánh

def test_ban_goc_la_nguyen_van_thong_qua_du_chua_tung_ap_dung(hai):
    tl = hai.ag.hoi("Điều 2 bản gốc")
    d = tl.dieu[0]
    assert d.ban_goc and "100/2015/QH13" in d.van_ban and (d.hieu_luc_tu, d.hieu_luc_den) == (None, None)
    assert "giảm nhẹ" in d.markdown and "miễn" not in d.markdown and not d.nguon
    assert "bản gốc" in tl.tom_tat and tl.ngay == "2018-01-01"
    assert any("bản gốc, đúng như khi Quốc hội thông qua ngày 27/11/2015" in g for g in d.ghi_chu)
    assert any("sửa đổi ngay từ ngày bộ luật có hiệu lực" in g and "12/2017/QH14" in g for g in d.ghi_chu)
    assert not any("Sẽ có sửa đổi" in g for g in d.ghi_chu)
    assert "bản gốc (như khi Quốc hội thông qua)" in thanh_van_ban(tl)


def test_so_sanh_ban_goc_voi_hien_hanh(hai):
    tl = hai.ag.hoi("So sánh Điều 2 bản gốc và hiện hành")
    s = tl.so_sanh
    assert s is not None and (s.nhan_a, s.nhan_b) == ("bản gốc", fmt_hom_nay())
    assert s.co_a and s.co_b and s.so_dong_khac >= 1 and "giảm nhẹ" in s.unified and "miễn trách nhiệm" in s.unified
    assert any("12/2017/QH14" in x for x in s.thay_doi)                                     # lần sửa cùng ngày bộ luật có hiệu lực vẫn được liệt kê
    tl = hai.ag.hoi("So sánh Điều 2")                                                       # không nêu mốc: bản gốc với hiện nay
    assert tl.so_sanh.nhan_a == "bản gốc" and any("bản gốc" in x for x in tl.thong_bao)


def fmt_hom_nay():
    from datetime import date
    return date.today().strftime("%d/%m/%Y")


def test_so_sanh_hai_thoi_diem_cung_bo_luat_cu(hai):
    tl = hai.ag.hoi("So sánh Điều 2 ngày 31/12/2009 và ngày 01/01/2010")
    s = tl.so_sanh
    assert s is not None and s.co_a and s.co_b and "giảm nhẹ" in s.unified and "miễn án phạt" in s.unified
    assert any("37/2009/QH12" in x for x in s.thay_doi)


def test_so_sanh_hai_thoi_diem_khac_bo_luat_khong_so_tung_chu(hai):
    tl = hai.ag.hoi("So sánh Điều 2 ngày 05/05/2010 và ngày 05/05/2020")
    assert tl.so_sanh is None and tl.trang_thai == "ok" and len(tl.dieu) == 2
    assert [("15/1999/QH10" in d.van_ban, "100/2015/QH13" in d.van_ban) for d in tl.dieu] == [(True, False), (False, True)]
    msg = " ".join(tl.thong_bao)
    assert "hai bộ luật khác nhau" in msg and "BLHS 1999" in msg and "BLHS 2015" in msg and "không so từng chữ" in msg


def test_so_sanh_mot_ben_khong_co_bo_luat_van_hien_ben_kia(mot):
    tl = mot.ag.hoi("So sánh Điều 2 ngày 05/05/2010 và ngày 05/05/2020")
    assert tl.so_sanh is None and len(tl.dieu) == 1 and "100/2015/QH13" in tl.dieu[0].van_ban
    msg = " ".join(tl.thong_bao)
    assert "Bên 05/05/2010" in msg and "Bộ luật hình sự năm 1999" in msg
    tl = mot.ag.hoi("So sánh Điều 2 ngày 05/05/2010 và ngày 05/05/2012")
    assert tl.trang_thai == "khong_co" and not tl.dieu and tl.so_sanh is None


def test_lich_su_ghi_nguon_doi_ngay_hieu_luc(hai):
    tl = hai.ag.hoi("Lịch sử sửa đổi Điều 2")
    assert tl.lich_su[0].ngay == "2018-01-01" and "thực tế đã được dời sang 01/01/2018 theo 41/2017/QH14" in tl.lich_su[0].noi_dung
    assert [e.ngay for e in tl.lich_su][1:] == ["2018-01-01"] and "BLHS 2015" in tl.tom_tat
    tl = hai.ag.hoi("Lịch sử sửa đổi Điều 2 BLHS 1999")                                      # bộ luật cũ: lịch sử của nó, kèm lưu ý đã hết hiệu lực
    assert [e.ngay for e in tl.lich_su] == ["2000-07-01", "2010-01-01"] and "BLHS 1999" in tl.tom_tat
    assert any("đã hết hiệu lực từ 01/01/2018" in x for x in tl.thong_bao)


def test_quan_he_va_chuyen_tiep_la_cua_bo_luat_hien_hanh(hai):
    tl = hai.ag.hoi("Những luật nào đã sửa đổi Bộ luật Hình sự?")
    so_hieu = {r["so_hieu"]: r["loai_quan_he"] for r in tl.quan_he}
    assert so_hieu.get("41/2017/QH14") == "hoan_hieu_luc" and "15/1999/QH10" in so_hieu and so_hieu["15/1999/QH10"] == "thay_the"


# ------------------------------------------------------------------------------------------------ tìm theo mô tả, kho

def test_tim_mo_ta_chon_bo_luat_theo_ngay_va_chi_muc(hai):
    tl = hai.ag.hoi("lén lấy xe máy của hàng xóm", ngay="2020-01-01")
    assert tl.trang_thai == "ok" and tl.ket_qua
    tl = hai.ag.hoi("lén lấy xe máy của hàng xóm", ngay="2010-05-05")                       # có bộ luật cũ nhưng chỉ mục chưa dựng cho nó
    assert tl.trang_thai == "khong_co" and not tl.ket_qua
    assert any("Chỉ mục tìm kiếm chưa có BLHS 1999" in x for x in tl.thong_bao)
    assert any("chưa có BLHS số 15/1999/QH10" in w for w in _kiem_tra_chi_muc_cu(hai.c, hai.idx))        # khởi động cũng cảnh báo
    tl = hai.ag.hoi("lén lấy xe máy của hàng xóm", ngay="1990-05-05")
    assert tl.trang_thai == "khong_co" and any("Bộ luật hình sự năm 1985" in x for x in tl.thong_bao)


def test_chi_muc_cu_khong_bao_nham_khi_khop(mot):
    assert _kiem_tra_chi_muc_cu(mot.c, mot.idx) == []


def test_thong_tin_kho_nhieu_bo_luat(hai, mot):
    tt = hai.cc.thong_tin_kho()
    assert tt["so_hieu"] == MOI and [b["so_hieu"] for b in tt["cac_bo_luat"]] == [CU, MOI]
    assert [(b["ten"], b["hieu_luc_tu"], b["hieu_luc_den"]) for b in tt["cac_bo_luat"]] == [
        ("BLHS 1999", "2000-07-01", "2017-12-31"), ("BLHS 2015", "2018-01-01", None)]
    assert [c["ten"] for c in tt["chua_nap"]] == ["BLHS 1985"] and [x["so_hieu"] for x in tt["hieu_luc_theo"]] == ["41/2017/QH14"]
    for nguon, dich in (("37/2009/QH12", CU), ("12/2017/QH14", MOI)):                                                   # quan hệ «sửa đổi» như khi nạp luật sửa đổi thật
        hai.c.execute("INSERT OR IGNORE INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id) "
                      "SELECT a.id, 'sua_doi', b.id FROM van_ban a, van_ban b WHERE a.so_hieu = ? AND b.so_hieu = ?", (nguon, dich))
    tt = hai.cc.thong_tin_kho()
    assert [[s["so_hieu"] for s in b["sua_doi"]] for b in tt["cac_bo_luat"]] == [["37/2009/QH12"], ["12/2017/QH14"]]      # luật sửa đổi theo từng bộ luật
    assert [s["so_hieu"] for s in tt["sua_doi"]] == ["12/2017/QH14"]                                                    # `sua_doi` vẫn là của bộ đang áp dụng hôm nay
    tt = mot.cc.thong_tin_kho()
    assert [b["ten"] for b in tt["cac_bo_luat"]] == ["BLHS 2015"] and [c["ten"] for c in tt["chua_nap"]] == ["BLHS 1999", "BLHS 1985"]
    assert (tt["chua_nap"][0]["tu"], tt["chua_nap"][0]["den"]) == ("2000-07-01", "2017-12-31")


def test_tro_giup_cho_biet_pham_vi_kho(mot):
    tl = mot.ag.hoi("bạn làm được gì")
    assert "BLHS 2015 (từ 01/01/2018 đến nay)" in tl.tom_tat and "chưa nạp: BLHS 1999 (từ 01/07/2000 đến hết 31/12/2017)" in tl.tom_tat


def test_cau_hinh_luat_chua_nap_ghi_de_duoc(tmp_path):
    k = dung_kho(tmp_path, co_cu=False, co_chi_muc=False, ten="cauhinh")
    cc = CongCu(k.c, None, cau_hinh={"luat_chua_nap": []})
    assert cc.luat_chua_nap() == [] and "Không có bộ luật nào trong kho" in cc.van_ban_tai_ngay("2010-05-05").ly_do
    k.c.close()
