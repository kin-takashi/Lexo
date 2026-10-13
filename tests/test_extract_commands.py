"""Bộ đọc tham chiếu, bộ trích lệnh (regex), bộ nạp lệnh chờ duyệt, duyệt theo lô — và cả đường ống trên dữ liệu thật (nếu có inbox/)."""
import json

import pytest

from src.apply.approve import ApproveError, bao_cao_markdown, duyet_theo_lo, tong_quan
from src.apply.rebuild import preview, rebuild
from src.extract.refs import find_groups, resolve_targets
from src.extract.regex_extractor import extract_commands
from src.ingest.amending_commands import load_extraction
from src.ingest.amending_law import stage_amending_law
from src.ingest.base_law import IngestError
from src.query.lookup import find_van_ban, get_dieu, lich_su_dieu
from src.store import connect, init_db

from test_apply_rebuild import env  # noqa: F401  (fixture: BLTN đã nạp)
from test_ingest_lookup import build_docx, real  # noqa: F401  (real: fixture BLHS 2015 thật)
from test_parse_amending import ALI, LINES, REAL, SCOPE, parse

BLTN = "99/2098/QH99"
ALI2, SCOPE2 = {"bộ luật thử nghiệm": BLTN}, {BLTN}
LUAT = "11/2029/QH99"
HL = "2030-01-01"
AMEND = [
    "LUẬT", "SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU CỦA BỘ LUẬT THỬ NGHIỆM", "Quốc hội ban hành Luật này.",
    f"Điều 1. Sửa đổi, bổ sung một số điều của Bộ luật Thử nghiệm số {BLTN}",
    "1. Sửa đổi, bổ sung khoản 2 Điều 2 như sau:",
    "“2. Người phạm tội tự thú được miễn trách nhiệm hình sự.”",
    "2. Bổ sung Điều 3a vào sau Điều 3 như sau:",
    "“Điều 3a. Tội mới",
    "Người nào phạm tội mới thì bị phạt tù từ 01 năm đến 02 năm.”",
    "3. Bãi bỏ Điều 4.",
    "4. Thay thế cụm từ “01 năm” bằng cụm từ “02 năm” tại khoản 1 Điều 3.",
    "Điều 2. Hiệu lực thi hành",
    "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2030.",
    "________________",
    "Luật này đã được Quốc hội khóa XIV, kỳ họp thứ 3 thông qua ngày 20 tháng 6 năm 2029.",
]


def stage(tmp_path, lines=AMEND):
    src = build_docx(tmp_path / "LSD.docx", lines, so_hieu=LUAT)
    st = stage_amending_law(src, tmp_path / "raw", aliases=ALI2, pham_vi_so_hieu=SCOPE2)
    return st, extract_commands(st.law)


def nap(env, st, res, **kw):  # noqa: F811
    return load_extraction(env.c, st.law, res, van_ban_dich_so_hieu=BLTN, file_nguon="LSD.docx", **kw)


# ---------- tham chiếu ----------

def _paths(text, inherited=None):
    ts, ok = resolve_targets(find_groups(text), text, inherited)
    return [(t.path, t.phan) for t in ts], ok


def test_tham_chieu_ngu_canh_lay_tu_nhom_lon_hon_ben_phai():
    p, ok = _paths("điểm a khoản 1, điểm b khoản 2 Điều 5")
    assert ok and p == [([("dieu", "5"), ("khoan", "1"), ("diem", "a")], "toan_bo"), ([("dieu", "5"), ("khoan", "2"), ("diem", "b")], "toan_bo")]


def test_tham_chieu_thieu_dieu_thi_khong_doan_tru_khi_duoc_ke_thua():
    assert _paths("các khoản 1, 2 và 3") == ([], False)
    p, ok = _paths("các khoản 1, 2 và 3", [("dieu", "195")])
    assert ok and [x[0][-1] for x in p] == [("khoan", "1"), ("khoan", "2"), ("khoan", "3")] and all(x[0][0] == ("dieu", "195") for x in p)


def test_tham_chieu_ten_dieu_va_khoan():
    p, ok = _paths("tên điều và khoản 1 Điều 40")
    assert ok and p == [([("dieu", "40")], "tieu_de"), ([("dieu", "40"), ("khoan", "1")], "toan_bo")]


# ---------- trích lệnh ----------

def test_trich_lenh_tu_luat_sua_doi_tong_hop():
    r = extract_commands(parse())
    assert r.n_leaf == 6 and r.n_parsed_leaf == 6 and r.coverage() == 1.0 and not r.unparsed
    kinds = [(c.loai_thao_tac, c.vi_tri_nguon) for c in r.commands]
    assert kinds == [("sua_doi", "Điều 1 khoản 1"), ("bo_sung", "Điều 1 khoản 2"), ("sua_doi", "Điều 1 khoản 3 điểm a"),
                     ("bai_bo", "Điều 1 khoản 3 điểm b"), ("bai_bo", "Điều 1 khoản 4"), ("thay_cum_tu", "Điều 1 khoản 5")]
    sd = r.commands[0]
    assert sd.dich == {"muc_tieu": [{"duong_dan": [{"loai": "dieu", "ky_hieu": "3"}], "phan": "toan_bo"}]} and sd.noi_dung_moi.startswith("Điều 3. Nguyên tắc")
    bs = r.commands[1]
    assert bs.dich == {"cha": None, "sau": [{"loai": "dieu", "ky_hieu": "5"}], "loai": "dieu", "ky_hieu": "5a"}
    assert r.commands[2].dich["muc_tieu"][0]["duong_dan"] == [{"loai": "dieu", "ky_hieu": "8"}, {"loai": "khoan", "ky_hieu": "1"}, {"loai": "diem", "ky_hieu": "b"}]
    assert r.commands[3].dich == {"muc_tieu": [[{"loai": "dieu", "ky_hieu": "8"}, {"loai": "khoan", "ky_hieu": "3"}]]}
    tc = r.commands[5]
    assert (tc.cum_tu_cu, tc.cum_tu_moi, tc.pham_vi, tc.dich["kieu"]) == ("của Bộ luật Hình sự", "của Luật này", "don_vi", "thay")
    assert all(c.pham_vi != "ngoai" for c in r.commands) and not any("12/2010" in json.dumps(c.dich) for c in r.commands)   # Điều 2: luật khác, bỏ qua


def test_thay_va_thay_the_cum_tu_la_mot():
    a = extract_commands(parse(LINES)).commands[-1]
    b = extract_commands(parse([x.replace("Thay cụm từ", "Thay thế cụm từ") for x in LINES])).commands[-1]
    assert (a.loai_thao_tac, a.dich, a.cum_tu_cu, a.cum_tu_moi) == (b.loai_thao_tac, b.dich, b.cum_tu_cu, b.cum_tu_moi)


def test_muc_khong_hieu_thi_khong_doan_ma_bao_chua_hieu():
    lines = LINES[:20] + ["6. Đánh số lại các khoản của Điều 12."] + LINES[20:]
    r = extract_commands(parse(lines))
    assert len(r.unparsed) == 1 and r.unparsed[0].item_id == "D1.6" and r.coverage() < 1 and len(r.commands) == 6
    assert r.to_dict()["unparsed"][0]["vi_tri_nguon"] == "Điều 1 khoản 6"


# ---------- nạp lệnh chờ duyệt ----------

def test_nap_lenh_cho_duyet_khong_dung_vao_phien_ban(env, tmp_path):  # noqa: F811
    st, res = stage(tmp_path)
    assert len(res.commands) == 4 and res.coverage() == 1.0
    before = env.dump()
    out = nap(env, st, res)
    assert out["so_lenh"] == 4 and out["so_chua_hieu"] == 0
    src = env.c.execute("SELECT * FROM van_ban WHERE so_hieu = ?", (LUAT,)).fetchone()
    assert (src["ngay_ban_hanh"], src["ngay_hieu_luc"]) == ("2029-06-20", "2030-01-01")
    rows = env.c.execute("SELECT * FROM lenh_sua_doi WHERE van_ban_nguon_id = ? ORDER BY thu_tu", (src["id"],)).fetchall()
    assert [r["loai_thao_tac"] for r in rows] == ["sua_doi", "bo_sung", "bai_bo", "thay_cum_tu"]
    assert all(r["trang_thai_duyet"] == "cho_duyet" and r["hieu_luc_tu"] == "2030-01-01" and r["van_ban_dich_id"] == env.vb for r in rows)
    assert json.loads(rows[0]["lenh_goc_json"])["vi_tri_nguon"] == "Điều 1 khoản 1"
    assert env.c.execute("SELECT COUNT(*) FROM quan_he_van_ban WHERE van_ban_a_id = ? AND van_ban_b_id = ?", (src["id"], env.vb)).fetchone()[0] == 1
    assert env.c.execute("SELECT loai FROM dieu_khoan_van_ban WHERE van_ban_id = ?", (src["id"],)).fetchall()[0][0] == "hieu_luc"
    rep = rebuild(env.c, env.vb)                                            # lệnh chờ duyệt KHÔNG được dùng
    assert rep.results == [] and env.dump() == before
    assert get_dieu(env.c, env.vb, "4", "2031-01-01") is not None


def test_nap_lai_can_co_thay_va_khong_de_len_lenh_da_duyet(env, tmp_path):  # noqa: F811
    st, res = stage(tmp_path)
    nap(env, st, res)
    with pytest.raises(IngestError, match="--thay"):
        nap(env, st, res)
    assert nap(env, st, res, thay_lenh_cho_duyet=True)["so_lenh"] == 4
    assert env.c.execute("SELECT COUNT(*) FROM lenh_sua_doi").fetchone()[0] == 4
    duyet_theo_lo(env.c, LUAT, env.vb, nguoi="pytest")
    with pytest.raises(IngestError, match="đã có"):
        nap(env, st, res, thay_lenh_cho_duyet=True)
    assert env.c.execute("SELECT COUNT(*) FROM lenh_sua_doi").fetchone()[0] == 4


def test_nap_thieu_van_ban_dich(env, tmp_path):  # noqa: F811
    st, res = stage(tmp_path)
    with pytest.raises(IngestError, match="chưa có trong CSDL"):
        load_extraction(env.c, st.law, res, van_ban_dich_so_hieu="1/1999/QH1", file_nguon="x.docx")


def test_ghi_chu_log_nap_liet_ke_muc_chua_hieu(env, tmp_path):  # noqa: F811
    lines = AMEND[:10] + ["4. Đánh số lại các khoản của Điều 2."] + AMEND[10:]
    st, res = stage(tmp_path, lines)
    assert [u.item_id for u in res.unparsed] == ["D1.4"]
    nap(env, st, res)
    note = env.c.execute("SELECT ghi_chu FROM log_nap WHERE vai_tro = 'sua_doi'").fetchone()[0]
    assert "chưa hiểu 1" in note and "D1.4" in note


# ---------- duyệt theo lô -> áp dụng -> tra cứu ----------

def test_duyet_ap_dung_va_tra_cuu_theo_ngay(env, tmp_path):  # noqa: F811
    st, res = stage(tmp_path)
    nap(env, st, res)
    (t,) = tong_quan(env.c, env.vb)
    assert (t["so_hieu"], t["cho_duyet"], t["da_duyet"], t["tong"]) == (LUAT, 4, 0, 4)
    rep, mem = preview(env.c, env.vb)
    mem.close()
    assert rep.n_ok == 4 and rep.n_loi == 0
    assert duyet_theo_lo(env.c, LUAT, env.vb, nguoi="Người duyệt thử", ghi_chu="pytest") == 4
    r = env.c.execute("SELECT * FROM lenh_sua_doi").fetchone()
    assert (r["trang_thai_duyet"], r["nguoi_duyet"], r["ghi_chu_duyet"]) == ("da_duyet", "Người duyệt thử", "pytest") and r["ngay_duyet"]
    assert rebuild(env.c, env.vb).n_ok == 4
    old, new = get_dieu(env.c, env.vb, "2", "2029-12-31"), get_dieu(env.c, env.vb, "2", HL)
    assert next(c for c in old.children if c.ky_hieu == "2").noi_dung == "Người phạm tội tự thú được giảm nhẹ."
    k2 = next(c for c in new.children if c.ky_hieu == "2")
    assert k2.noi_dung == "Người phạm tội tự thú được miễn trách nhiệm hình sự." and k2.nguon[0].so_hieu == LUAT and k2.nguon[0].vi_tri_nguon == "Điều 1 khoản 1"
    assert get_dieu(env.c, env.vb, "3a", "2029-12-31") is None and get_dieu(env.c, env.vb, "3a", HL) is not None
    assert get_dieu(env.c, env.vb, "4", "2029-12-31") is not None and get_dieu(env.c, env.vb, "4", HL) is None
    k1 = next(c for c in get_dieu(env.c, env.vb, "3", HL).children if c.ky_hieu == "1")
    assert "từ 02 năm đến 03 năm" in k1.noi_dung and k1.nguon[0].loai_thao_tac == "thay_cum_tu"
    assert [e.vi_tri_nguon for e in lich_su_dieu(env.c, env.vb, "3")] == ["Điều 1 khoản 4"]
    (t,) = tong_quan(env.c, env.vb)
    assert (t["cho_duyet"], t["da_duyet"]) == (0, 4)
    with pytest.raises(ApproveError, match="không còn lệnh"):
        duyet_theo_lo(env.c, LUAT, env.vb, nguoi="x")


def test_duyet_yeu_cau_ten_nguoi_va_tu_choi_khi_co_lenh_loi(env, tmp_path):  # noqa: F811
    st, res = stage(tmp_path)
    nap(env, st, res)
    with pytest.raises(ApproveError, match="tên người duyệt"):
        duyet_theo_lo(env.c, LUAT, env.vb, nguoi="  ")
    env.c.execute("UPDATE lenh_sua_doi SET dich_json = ? WHERE loai_thao_tac = 'bai_bo'",
                  (json.dumps({"muc_tieu": [[{"loai": "dieu", "ky_hieu": "99"}]]}),))
    with pytest.raises(ApproveError, match="không áp được"):
        duyet_theo_lo(env.c, LUAT, env.vb, nguoi="pytest")
    assert env.c.execute("SELECT COUNT(*) FROM lenh_sua_doi WHERE trang_thai_duyet <> 'cho_duyet'").fetchone()[0] == 0     # không duyệt nửa vời


def test_bao_cao_markdown_de_doi_chieu(env, tmp_path):  # noqa: F811
    st, res = stage(tmp_path)
    nap(env, st, res)
    md = bao_cao_markdown(env.c, LUAT, env.vb)
    assert md.startswith(f"# Lệnh sửa đổi của {LUAT}") and "4 lệnh; áp thử: 4 chạy được, 0 lỗi" in md
    assert "“01 năm” → “02 năm”" in md and "Kiểu thay từ: thay" in md and "Hiệu lực từ: 2030-01-01" in md
    assert md.count("## #") == 4 and "[OK; cho_duyet]" in md


# ---------- dữ liệu thật (chỉ chạy khi có inbox/) ----------

@pytest.fixture(scope="module")
def real_pipeline(tmp_path_factory, real_blhs_conn):
    if not all(p.exists() for p in REAL.values()):
        pytest.skip("thiếu file luật sửa đổi trong inbox/")
    tmp = tmp_path_factory.mktemp("ra")
    c = real_blhs_conn
    out = {}
    for so, p in REAL.items():
        st = stage_amending_law(p, tmp / "raw", aliases=ALI, pham_vi_so_hieu=SCOPE)
        res = extract_commands(st.law)
        load_extraction(c, st.law, res, van_ban_dich_so_hieu="100/2015/QH13", file_nguon=p.name)
        out[so] = res
    return c, out


@pytest.fixture(scope="module")
def real_blhs_conn(real):
    return real[1]


def test_real_do_phu_100_phan_tram_va_so_lenh(real_pipeline):
    _, out = real_pipeline
    assert {k: (v.n_leaf, v.n_parsed_leaf, len(v.commands)) for k, v in out.items()} == {
        "12/2017/QH14": (220, 220, 253), "86/2025/QH15": (36, 36, 36), "59/2024/QH15": (2, 2, 2)}


def test_real_xem_truoc_ap_het_va_so_dieu_theo_moc_hieu_luc(real_pipeline):
    c, _ = real_pipeline
    (vb,) = find_van_ban(c, "BLHS", 2015)
    rep, mem = preview(c, vb["id"])
    assert rep.n_loi == 0 and rep.n_ok == 291
    n = {d: mem.execute("SELECT COUNT(*) FROM don_vi_luat dv JOIN phien_ban_noi_dung p ON p.don_vi_id = dv.id WHERE dv.loai = 'dieu' "
                        "AND p.hieu_luc_tu <= ?1 AND (p.hieu_luc_den IS NULL OR ?1 < p.hieu_luc_den)", (d,)).fetchone()[0]
         for d in ("2017-12-31", "2018-01-01", "2025-06-30", "2025-07-01", "2025-12-31", "2026-01-01")}
    assert n == {"2017-12-31": 426, "2018-01-01": 426, "2025-06-30": 426, "2025-07-01": 427, "2025-12-31": 427, "2026-01-01": 409}
    # bất biến: nút đang hiệu lực thì cha cũng đang hiệu lực, và không trùng ký hiệu giữa các anh em
    for d in ("2018-01-01", "2025-07-01", "2026-01-01"):
        rows = mem.execute("SELECT dv.id, dv.cha_id, dv.loai, p.ky_hieu FROM don_vi_luat dv JOIN phien_ban_noi_dung p ON p.don_vi_id = dv.id "
                           "WHERE p.hieu_luc_tu <= ?1 AND (p.hieu_luc_den IS NULL OR ?1 < p.hieu_luc_den)", (d,)).fetchall()
        ids = {r["id"] for r in rows}
        assert all(r["cha_id"] is None or r["cha_id"] in ids for r in rows), d
        keys = [(r["cha_id"], r["loai"], r["ky_hieu"]) for r in rows]
        assert len(keys) == len(set(keys)), d
    mem.close()
    assert c.execute("SELECT COUNT(*) FROM phien_ban_noi_dung WHERE lenh_tao_ra_id IS NOT NULL").fetchone()[0] == 0     # CSDL thật không đổi


def test_real_duyet_ap_dung_roi_tra_cuu(real_pipeline):
    c, _ = real_pipeline
    (vb,) = find_van_ban(c, "BLHS", 2015)
    for so in ("12/2017/QH14", "86/2025/QH15", "59/2024/QH15"):
        duyet_theo_lo(c, so, vb["id"], nguoi="pytest", ghi_chu="kiểm thử")
    assert rebuild(c, vb["id"]).n_ok == 291
    old, cur = get_dieu(c, vb["id"], "173", "2017-12-31"), get_dieu(c, vb["id"], "173")
    assert not any(u.nguon for u in old.walk())
    assert {n.so_hieu for u in cur.walk() for n in u.nguon} == {"12/2017/QH14"}
    assert get_dieu(c, vb["id"], "217a", "2017-12-31") is None and get_dieu(c, vb["id"], "217a").nguon[0].vi_tri_nguon == "Điều 1 khoản 51"
    assert get_dieu(c, vb["id"], "91", "2025-12-31") is not None and get_dieu(c, vb["id"], "91", "2026-01-01") is None
