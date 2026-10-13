"""Engine áp lệnh sửa đổi (src/apply/rebuild.py) trên một bộ luật thử nghiệm nạp qua đường ống thật (stage -> duyệt -> nạp)."""
import json

import pytest

from src.apply.rebuild import LOI, RebuildError, clear_derived, preview, rebuild
from src.ingest.base_law import ingest_base_law, stage_base_law
from src.store import connect, init_db

from test_ingest_lookup import approved_review, build_docx

BASE_LINES = [
    "BỘ LUẬT", "THỬ NGHIỆM", "Quốc hội ban hành Bộ luật thử nghiệm.",
    "Chương I", "ĐIỀU KHOẢN CHUNG",
    "Điều 1. Phạm vi",
    "Bộ luật này quy định về tội phạm.",
    "Điều 2. Nguyên tắc",
    "1. Mọi hành vi vi phạm bị xử lý theo quy định sau đây:",
    "a) phạt cảnh cáo;",
    "b) phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng;",
    "c) phạt tù từ 01 năm đến 03 năm.",
    "2. Người phạm tội tự thú được giảm nhẹ.",
    "3. Không áp dụng đối với cơ quan tư pháp.",
    "Chương II", "CÁC TỘI DANH",
    "Điều 3. Tội trộm cắp",
    "1. Người nào trộm cắp tài sản thì bị phạt tù từ 01 năm đến 03 năm.",
    "2. Phạm tội thuộc một trong các trường hợp sau đây thì bị phạt tù từ 03 năm đến 07 năm:",
    "a) có tổ chức;",
    "b) tái phạm nguy hiểm.",
    "Điều 4. Tội lừa đảo",
    "Người nào lừa đảo thì bị phạt tù từ 01 năm đến 03 năm.",
    "Điều 5. Hiệu lực thi hành",
    "Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 07 năm 2016.",
    "________________",
    "Bộ luật này đã được Quốc hội khóa XIII thông qua ngày 27 tháng 11 năm 2015.",
]
BASE_DATE = "2016-07-01"
D1, D2, D3 = "2018-01-01", "2025-07-01", "2026-01-01"


class Env:
    def __init__(self, conn, vb):
        self.c, self.vb = conn, vb
        self._nguon: dict[str, int] = {}
        self._log: dict[str, int] = {}
        self._thu: dict[str, int] = {}

    def nguon(self, so_hieu: str, ban_hanh: str) -> int:
        if so_hieu not in self._nguon:
            self._nguon[so_hieu] = self.c.execute(
                "INSERT INTO van_ban (so_hieu, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban, ngay_hieu_luc) "
                "VALUES (?, ?, 'luat', ?, ?, ?)", (so_hieu, f"Luật {so_hieu}", ban_hanh, ban_hanh, ban_hanh)).lastrowid
            self._log[so_hieu] = self.c.execute(
                "INSERT INTO log_nap (van_ban_id, file_nguon, vai_tro, phuong_phap, ket_qua) "
                "VALUES (?, 'x.docx', 'sua_doi', 'regex', 'thanh_cong')", (self._nguon[so_hieu],)).lastrowid
        return self._nguon[so_hieu]

    def cmd(self, loai, dich, *, tu, nguon="12/2017/QH14", ban_hanh="2017-06-20", noi_dung=None, cu=None, moi=None,
            pham_vi=None, trang_thai="da_duyet", vi_tri="Điều 1 khoản 1", ngay_moi=None) -> int:
        nid = self.nguon(nguon, ban_hanh)
        thu = self._thu[nguon] = self._thu.get(nguon, 0) + 1
        return self.c.execute(
            """INSERT INTO lenh_sua_doi (van_ban_nguon_id, log_nap_id, thu_tu, loai_thao_tac, van_ban_dich_id, dich_json,
                   noi_dung_moi, cum_tu_cu, cum_tu_moi, pham_vi, ngay_hieu_luc_moi, hieu_luc_tu, vi_tri_nguon,
                   trang_thai_duyet, nguoi_duyet, ngay_duyet)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nid, self._log[nguon], thu, loai, self.vb, json.dumps(dich, ensure_ascii=False) if dich is not None else None,
             noi_dung, cu, moi, pham_vi, ngay_moi, tu, vi_tri, trang_thai, "pytest", "2026-01-01")).lastrowid

    def snap(self, ngay: str) -> dict[str, tuple]:
        """{'dieu 2/khoan 1/diem a': (tieu_de, noi_dung)} của những nút có hiệu lực tại ngày; kiểm tra bất biến cây."""
        rows = self.c.execute(
            """SELECT d.id, d.cha_id, d.loai, p.ky_hieu, p.tieu_de, p.noi_dung FROM don_vi_luat d
               JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
               WHERE d.van_ban_id = ? AND p.hieu_luc_tu <= ? AND (p.hieu_luc_den IS NULL OR ? < p.hieu_luc_den)""",
            (self.vb, ngay, ngay)).fetchall()
        by_id = {r["id"]: r for r in rows}
        out: dict[str, tuple] = {}

        def path(r) -> str:
            """Khoá dạng 'dieu 2/khoan 1/diem a'; Điều không kèm Chương (số Điều duy nhất), Chương là 'chuong II'."""
            here = f"{r['loai']} {r['ky_hieu']}"
            if r["cha_id"] is None:
                return here
            parent = by_id.get(r["cha_id"])
            assert parent is not None, f"nút {here} còn hiệu lực nhưng cha thì không (ngày {ngay})"
            return here if r["loai"] == "dieu" else f"{path(parent)}/{here}"

        for r in rows:
            k = path(r)
            assert k not in out, f"trùng ký hiệu anh em: {k} (ngày {ngay})"
            out[k] = (r["tieu_de"], r["noi_dung"])
        return out

    def versions(self, path_label: str) -> list[tuple]:
        """Các phiên bản (tu, den, noi_dung) của nút, theo thời gian. path_label như 'dieu 2/khoan 1'."""
        parts = [p.split(" ", 1) for p in path_label.split("/")]
        cur = None
        for loai, ky in parts:
            row = self.c.execute(
                """SELECT DISTINCT d.id FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
                   WHERE d.van_ban_id = ? AND d.loai = ? AND p.ky_hieu = ? AND d.cha_id IS ?""" if cur is None else
                """SELECT DISTINCT d.id FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
                   WHERE d.van_ban_id = ? AND d.loai = ? AND p.ky_hieu = ? AND d.cha_id = ?""",
                (self.vb, loai, ky, cur)).fetchone() if cur is not None else self.c.execute(
                """SELECT DISTINCT d.id FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
                   WHERE d.van_ban_id = ? AND d.loai = ? AND p.ky_hieu = ?""", (self.vb, loai, ky)).fetchone()
            assert row is not None, path_label
            cur = row["id"]
        return [(r["hieu_luc_tu"], r["hieu_luc_den"], r["noi_dung"]) for r in self.c.execute(
            "SELECT * FROM phien_ban_noi_dung WHERE don_vi_id = ? ORDER BY hieu_luc_tu, id", (cur,))]

    def dump(self) -> list[tuple]:
        return [tuple(r) for r in self.c.execute(
            """SELECT d.loai, p.ky_hieu, p.thu_tu, p.tieu_de, p.noi_dung, p.hieu_luc_tu, p.hieu_luc_den, p.lenh_tao_ra_id,
                      p.lenh_dong_id, p.van_ban_tao_ra_id, d.lenh_tao_ra_id
               FROM phien_ban_noi_dung p JOIN don_vi_luat d ON d.id = p.don_vi_id
               ORDER BY d.id, p.hieu_luc_tu, p.id""")]


def P(*pairs):
    it = iter(pairs)
    return [{"loai": a, "ky_hieu": b} for a, b in zip(it, it)]


@pytest.fixture
def env(tmp_path):
    src = build_docx(tmp_path / "BLTN.docx", BASE_LINES)
    st = stage_base_law(src, tmp_path / "raw", ten_viet_tat="BLTN")
    approved_review(st)
    c = connect()
    init_db(c)
    vb = ingest_base_law(c, st.directory, raw_root=tmp_path / "raw")["van_ban_id"]
    yield Env(c, vb)
    c.close()


def test_khong_co_lenh_thi_giu_nguyen_ban_goc(env):
    before = env.dump()
    rep = rebuild(env.c, env.vb)
    assert rep.results == [] and rep.ngay_hieu_luc_goc == BASE_DATE and env.dump() == before
    assert len(env.snap(BASE_DATE)) == 17 and env.snap("2016-06-30") == {}


# ---------- sua_doi ----------

def test_sua_doi_khoan_tao_phien_ban_moi_co_nguon(env):
    lid = env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1,
                  noi_dung="2. Người phạm tội tự thú được miễn trách nhiệm hình sự.", vi_tri="Điều 1 khoản 3")
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 1 and rep.results[0].versions_created == 1 and rep.results[0].versions_closed == 1
    assert env.snap("2017-12-31")["dieu 2/khoan 2"][1] == "Người phạm tội tự thú được giảm nhẹ."
    assert env.snap(D1)["dieu 2/khoan 2"][1] == "Người phạm tội tự thú được miễn trách nhiệm hình sự."
    old, new = env.versions("dieu 2/khoan 2")
    assert (old[0], old[1], new[0], new[1]) == (BASE_DATE, D1, D1, None)
    row = env.c.execute("SELECT * FROM phien_ban_noi_dung WHERE noi_dung LIKE '%miễn trách nhiệm%'").fetchone()
    assert row["lenh_tao_ra_id"] == lid and row["van_ban_tao_ra_id"] == env.nguon("12/2017/QH14", "x") and row["nguoi_duyet"] == "pytest"
    assert env.c.execute("SELECT lenh_dong_id FROM phien_ban_noi_dung WHERE hieu_luc_den = ?", (D1,)).fetchone()[0] == lid
    # nút khác không bị đụng tới
    assert len(env.versions("dieu 2/khoan 1")) == 1 and len(env.versions("dieu 3")) == 1


def test_sua_doi_ca_dieu_dong_bo_con_theo_ky_hieu(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2")}]}, tu=D1, noi_dung=(
        "Điều 2. Nguyên tắc chung\nMở đầu điều.\n"
        "1. Mọi hành vi vi phạm bị xử lý theo quy định sau đây:\na) phạt cảnh cáo;\nb) phạt tiền từ 20.000.000 đồng đến 50.000.000 đồng.\n"
        "2. Người phạm tội tự thú được giảm nhẹ.\n4. Khoản bốn mới."))
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 1
    s = env.snap(D1)
    assert s["dieu 2"] == ("Nguyên tắc chung", "Mở đầu điều.")
    assert s["dieu 2/khoan 1/diem b"][1] == "phạt tiền từ 20.000.000 đồng đến 50.000.000 đồng."
    assert "dieu 2/khoan 1/diem c" not in s and "dieu 2/khoan 3" not in s          # điểm c, khoản 3 bị bỏ
    assert s["dieu 2/khoan 4"][1] == "Khoản bốn mới."
    # nút không đổi thì KHÔNG sinh phiên bản mới; nút bị bỏ được đóng, nút mới có lenh_tao_ra
    assert len(env.versions("dieu 2/khoan 1/diem a")) == 1 and len(env.versions("dieu 2/khoan 2")) == 1
    assert env.versions("dieu 2/khoan 3")[0][:2] == (BASE_DATE, D1)
    assert env.c.execute("SELECT COUNT(*) FROM don_vi_luat WHERE lenh_tao_ra_id IS NOT NULL").fetchone()[0] == 1
    order = [k for k in s if k.startswith("dieu 2/khoan") and k.count("/") == 1]
    tt = {r["ky_hieu"]: r["thu_tu"] for r in env.c.execute(
        "SELECT p.ky_hieu, p.thu_tu FROM phien_ban_noi_dung p JOIN don_vi_luat d ON d.id = p.don_vi_id "
        "WHERE d.loai = 'khoan' AND p.hieu_luc_den IS NULL AND d.cha_id = (SELECT d2.id FROM don_vi_luat d2 JOIN phien_ban_noi_dung p2 "
        "ON p2.don_vi_id = d2.id WHERE d2.loai = 'dieu' AND p2.ky_hieu = '2')")}
    assert tt["1"] < tt["2"] < tt["4"] and order == ["dieu 2/khoan 1", "dieu 2/khoan 2", "dieu 2/khoan 4"]


def test_sua_doi_tieu_de_dieu_va_cac_khoan_tu_mot_khoi(env):
    env.cmd("sua_doi", {"muc_tieu": [
        {"duong_dan": P("dieu", "3"), "phan": "tieu_de"},
        {"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1,
        noi_dung="Điều 3. Tội trộm cắp tài sản\n1. Người nào trộm cắp tài sản thì bị phạt tù từ 02 năm đến 05 năm.")
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 1 and not rep.problems()
    s = env.snap(D1)
    assert s["dieu 3"][0] == "Tội trộm cắp tài sản" and s["dieu 3/khoan 1"][1].endswith("từ 02 năm đến 05 năm.")
    assert s["dieu 3/khoan 2/diem a"] == env.snap(BASE_DATE)["dieu 3/khoan 2/diem a"]      # khoản 2 không đụng tới
    assert len(env.versions("dieu 3/khoan 2")) == 1


def test_sua_doi_chi_noi_dung_giu_nut_con(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "1"), "phan": "chi_noi_dung"}]}, tu=D1,
            noi_dung="1. Mọi hành vi vi phạm bị xử lý như sau:")
    rebuild(env.c, env.vb)
    s = env.snap(D1)
    assert s["dieu 2/khoan 1"][1] == "Mọi hành vi vi phạm bị xử lý như sau:" and "dieu 2/khoan 1/diem c" in s


def test_sua_doi_canh_bao_khi_khong_doi_gi_va_khi_khoi_thua(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1,
            noi_dung="2. Người phạm tội tự thú được giảm nhẹ.")
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1,
            noi_dung="1. Người nào trộm cắp thì bị phạt.\n2. Khoản thừa.")
    rep = rebuild(env.c, env.vb)
    msgs = [p.message for _, p in rep.problems()]
    assert rep.n_ok == 2 and any("không làm đổi nội dung" in m for m in msgs) and any("không thuộc đích nào" in m for m in msgs)
    assert len(env.versions("dieu 2/khoan 2")) == 1


def test_sua_doi_dich_khong_co_hoac_da_bai_bo_thi_loi(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "99")}]}, tu=D1, noi_dung="Điều 99. X\nY")
    env.cmd("bai_bo", {"muc_tieu": [P("dieu", "4")]}, tu=D1)
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "4")}]}, tu=D2, noi_dung="Điều 4. Tội lừa đảo\nMới.")
    rep = rebuild(env.c, env.vb, strict=False)
    assert [r.ok for r in rep.results] == [False, True, False]
    assert "Điều 99" in rep.results[0].problems[0].message and "Điều 4" in rep.results[2].problems[0].message
    assert env.snap(D1).get("dieu 4") is None and "dieu 4" in env.snap("2017-12-31")


def test_sua_doi_khoi_khong_chua_dich_thi_loi(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1, noi_dung="3. Khoản ba.")
    rep = rebuild(env.c, env.vb, strict=False)
    assert not rep.results[0].ok and "không chứa" in rep.results[0].problems[0].message


# ---------- bo_sung ----------

def test_bo_sung_khoan_sau_khoan_xen_giua_thu_tu(env):
    env.cmd("bo_sung", {"cha": P("dieu", "3"), "sau": P("dieu", "3", "khoan", "1"), "loai": "khoan", "ky_hieu": "1a"}, tu=D1,
            noi_dung="1a. Khoản chèn vào giữa.")
    rep = rebuild(env.c, env.vb)
    assert rep.results[0].nodes_created == 1
    rows = env.c.execute(
        "SELECT p.ky_hieu, p.thu_tu FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id "
        "WHERE d.loai = 'khoan' AND p.hieu_luc_den IS NULL AND p.ky_hieu IN ('1','1a','2') AND d.cha_id = "
        "(SELECT d2.id FROM don_vi_luat d2 JOIN phien_ban_noi_dung p2 ON p2.don_vi_id = d2.id WHERE d2.loai='dieu' AND p2.ky_hieu='3') "
        "ORDER BY p.thu_tu").fetchall()
    assert [r["ky_hieu"] for r in rows] == ["1", "1a", "2"]
    assert env.snap(D1)["dieu 3/khoan 1a"][1] == "Khoản chèn vào giữa." and "dieu 3/khoan 1a" not in env.snap("2017-12-31")
    assert env.c.execute("SELECT d.lenh_tao_ra_id IS NOT NULL FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id "
                         "WHERE p.ky_hieu = '1a'").fetchone()[0] == 1


def test_bo_sung_dieu_moi_co_khoan_va_diem(env):
    env.cmd("bo_sung", {"cha": P("chuong", "II"), "sau": P("dieu", "3"), "loai": "dieu", "ky_hieu": "3a"}, tu=D2,
            noi_dung="Điều 3a. Tội mới\n1. Người nào phạm tội mới:\na) bị phạt tiền;\nb) bị phạt tù.\n2. Khoản hai.")
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 1 and rep.results[0].nodes_created == 5
    s = env.snap(D2)
    assert s["dieu 3a"] == ("Tội mới", "") and s["dieu 3a/khoan 1/diem b"][1] == "bị phạt tù."
    assert "dieu 3a" not in env.snap(D1)
    tt = {r["ky_hieu"]: (r["thu_tu"], r["cha"]) for r in env.c.execute(
        "SELECT p.ky_hieu, p.thu_tu, (SELECT c.ky_hieu FROM phien_ban_noi_dung c WHERE c.don_vi_id = d.cha_id AND c.hieu_luc_den IS NULL) AS cha "
        "FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id WHERE d.loai = 'dieu' AND p.hieu_luc_den IS NULL")}
    assert tt["3"][0] < tt["3a"][0] < tt["4"][0] and tt["3a"][1] == "II"


def test_bo_sung_vao_cuoi_khi_khong_co_sau_va_trung_ky_hieu_thi_loi(env):
    env.cmd("bo_sung", {"cha": P("dieu", "3"), "sau": None, "loai": "khoan", "ky_hieu": "3"}, tu=D1, noi_dung="3. Khoản ba.")
    env.cmd("bo_sung", {"cha": P("dieu", "3"), "sau": None}, tu=D2, noi_dung="2. Khoản hai bị trùng.")
    rep = rebuild(env.c, env.vb, strict=False)
    assert [r.ok for r in rep.results] == [True, False] and "đã có" in rep.results[1].problems[0].message
    assert "dieu 3/khoan 3" in env.snap(D1)


def test_bo_sung_lech_loai_thi_loi(env):
    env.cmd("bo_sung", {"cha": P("dieu", "3"), "sau": P("dieu", "3", "khoan", "1"), "loai": "khoan", "ky_hieu": "1a"}, tu=D1,
            noi_dung="a) đây là điểm chứ không phải khoản.")
    rep = rebuild(env.c, env.vb, strict=False)
    assert not rep.results[0].ok


# ---------- bai_bo ----------

def test_bai_bo_chuong_bai_bo_ca_cay(env):
    lid = env.cmd("bai_bo", {"muc_tieu": [P("chuong", "II")]}, tu=D3, vi_tri="Điều 177 khoản 1 điểm a")
    rep = rebuild(env.c, env.vb)
    assert rep.results[0].versions_closed == 8                     # chương + Điều 3,4,5 + khoản 1,2 + điểm a,b của Điều 3
    before, after = env.snap("2025-12-31"), env.snap(D3)
    assert "dieu 3/khoan 2/diem b" in before and "chuong II" in before
    assert "chuong II" not in after and not any(k.startswith(("dieu 3", "dieu 4", "dieu 5")) for k in after)
    assert "chuong I" in after and "dieu 2/khoan 1" in after
    assert {r[0] for r in env.c.execute("SELECT lenh_dong_id FROM phien_ban_noi_dung WHERE hieu_luc_den IS NOT NULL")} == {lid}


def test_bai_bo_mot_khoan(env):
    env.cmd("bai_bo", {"muc_tieu": [P("dieu", "2", "khoan", "3")]}, tu=D1)
    rebuild(env.c, env.vb)
    assert "dieu 2/khoan 3" in env.snap("2017-12-31") and "dieu 2/khoan 3" not in env.snap(D1) and "dieu 2/khoan 2" in env.snap(D1)


# ---------- thay_cum_tu ----------

def test_thay_cum_tu_trong_dieu_ap_cho_ca_nut_con(env):
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "3")], "kieu": "thay"}, tu=D1, cu="phạt tù", moi="phạt tù có thời hạn")
    rep = rebuild(env.c, env.vb)
    assert rep.results[0].replacements == 2 and rep.results[0].versions_created == 2
    s = env.snap(D1)
    assert "phạt tù có thời hạn từ 01 năm" in s["dieu 3/khoan 1"][1] and "phạt tù có thời hạn từ 03 năm" in s["dieu 3/khoan 2"][1]
    assert s["dieu 4"] == env.snap(BASE_DATE)["dieu 4"] and len(env.versions("dieu 3/khoan 2/diem a")) == 1


def test_thay_cum_tu_bo_chen_sau_chen_cuoi(env):
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "2", "khoan", "3")], "kieu": "bo"}, tu=D1, cu="tư pháp")
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "3", "khoan", "1")], "kieu": "chen_sau"}, tu=D1, cu="trộm cắp", moi="hoặc lừa đảo")
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "4")], "kieu": "chen_cuoi"}, tu=D2, moi="Tài sản thu giữ được xử lý theo pháp luật.")
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 3
    s = env.snap(D2)
    assert s["dieu 2/khoan 3"][1] == "Không áp dụng đối với cơ quan."
    assert s["dieu 3/khoan 1"][1].startswith("Người nào trộm cắp hoặc lừa đảo tài sản")
    assert s["dieu 4"][1].endswith("03 năm. Tài sản thu giữ được xử lý theo pháp luật.") and s["dieu 4"][0] == "Tội lừa đảo"


def test_thay_cum_tu_khong_thay_thi_loi_va_hoan_tac_ca_lenh(env):
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "3", "khoan", "1"), P("dieu", "4", "khoan", "1")], "kieu": "thay"},
            tu=D1, cu="trộm cắp", moi="cướp")
    rep = rebuild(env.c, env.vb, strict=False)
    assert not rep.results[0].ok and rep.results[0].versions_created == 0
    assert env.snap(D1)["dieu 3/khoan 1"] == env.snap(BASE_DATE)["dieu 3/khoan 1"]      # phần đã đổi trước khi gặp lỗi được hoàn tác


def test_thay_cum_tu_toan_van_ban(env):
    env.cmd("thay_cum_tu", {"muc_tieu": None, "kieu": "thay"}, tu=D1, cu="từ 01 năm", moi="từ 02 năm", pham_vi="toan_van_ban")
    rep = rebuild(env.c, env.vb)
    assert rep.results[0].replacements == 3                     # Điều 2 khoản 1 điểm c, Điều 3 khoản 1, Điều 4
    assert "từ 02 năm" in env.snap(D1)["dieu 4"][1] and "từ 01 năm" in env.snap("2017-12-31")["dieu 4"][1]


# ---------- thứ tự, thời gian, hoãn hiệu lực ----------

def test_phat_lai_theo_ngay_hieu_luc_khong_theo_thu_tu_them_vao(env):
    a = env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D2, nguon="86/2025/QH15",
                ban_hanh="2025-06-25", noi_dung="2. Bản 2025.")
    b = env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1, noi_dung="2. Bản 2018.")
    rebuild(env.c, env.vb)
    v = env.versions("dieu 2/khoan 2")
    assert [(x[0], x[1], x[2]) for x in v] == [(BASE_DATE, D1, "Người phạm tội tự thú được giảm nhẹ."), (D1, D2, "Bản 2018."), (D2, None, "Bản 2025.")]
    assert env.snap("2020-01-01")["dieu 2/khoan 2"][1] == "Bản 2018."
    ids = {r["lenh_tao_ra_id"] for r in env.c.execute("SELECT lenh_tao_ra_id FROM phien_ban_noi_dung WHERE lenh_tao_ra_id IS NOT NULL")}
    assert ids == {a, b}


def test_hai_lenh_cung_ngay_de_lai_khoang_rong(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1, noi_dung="1. Bản trung gian.")
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "3", "khoan", "1")], "kieu": "thay"}, tu=D1, cu="trung gian", moi="cuối cùng")
    rebuild(env.c, env.vb)
    v = env.versions("dieu 3/khoan 1")
    assert [(x[0], x[1]) for x in v] == [(BASE_DATE, D1), (D1, D1), (D1, None)]
    assert env.snap(D1)["dieu 3/khoan 1"][1] == "Bản cuối cùng." and env.snap("2017-12-31")["dieu 3/khoan 1"][1].startswith("Người nào")


def test_lenh_truoc_ngay_hieu_luc_cua_ban_goc_thi_loi(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu="2016-01-01", noi_dung="2. Quá sớm.")
    rep = rebuild(env.c, env.vb, strict=False)
    assert not rep.results[0].ok and "sớm hơn" in rep.results[0].problems[0].message


def test_hoan_hieu_luc_doi_ngay_ban_goc_va_bien_ban_chua_tung_hieu_luc(env):
    env.cmd("hoan_hieu_luc", None, tu="2016-06-01", nguon="41/2017/QH14", ban_hanh="2016-06-01", ngay_moi=D1, vi_tri="Điều 1")
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1, noi_dung="2. Có hiệu lực cùng ngày với bộ luật.")
    rep = rebuild(env.c, env.vb)
    assert rep.ngay_hieu_luc_goc == D1 and env.c.execute("SELECT ngay_hieu_luc FROM van_ban WHERE id = ?", (env.vb,)).fetchone()[0] == D1
    assert env.snap("2017-06-01") == {} and env.snap("2016-07-01") == {}          # hoãn: chưa có hiệu lực
    s = env.snap(D1)
    assert s["dieu 2/khoan 2"][1] == "Có hiệu lực cùng ngày với bộ luật." and len(s) == 17
    v = env.versions("dieu 2/khoan 2")
    assert (v[0][0], v[0][1]) == (D1, D1)                                            # bản gốc của khoản 2: khoảng rỗng, chưa từng hiệu lực
    ngay_theo_van_ban = env.c.execute("SELECT ngay_hieu_luc_theo_van_ban FROM van_ban WHERE id = ?", (env.vb,)).fetchone()[0]
    assert ngay_theo_van_ban == BASE_DATE                                            # ngày theo văn bản vẫn được giữ để đối chiếu


# ---------- tính chất của rebuild ----------

def test_chi_dung_lenh_da_duyet_va_xem_truoc_khong_dung_csdl_that(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1, noi_dung="2. Chưa duyệt.", trang_thai="cho_duyet")
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "3")}]}, tu=D1, noi_dung="3. Đã duyệt.", trang_thai="da_sua")
    before = env.dump()
    rep, mem = preview(env.c, env.vb)
    try:
        assert rep.n_ok == 2 and env.dump() == before
        assert mem.execute("SELECT COUNT(*) FROM phien_ban_noi_dung").fetchone()[0] == len(before) + 2
    finally:
        mem.close()
    rep = rebuild(env.c, env.vb)
    assert rep.n_ok == 1 and env.snap(D1)["dieu 2/khoan 3"][1] == "Đã duyệt." and env.snap(D1)["dieu 2/khoan 2"][1].startswith("Người phạm tội")


def test_rebuild_tat_dinh_va_tu_lanh_khi_sua_lenh(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1, noi_dung="2. Bản A.")
    env.cmd("bai_bo", {"muc_tieu": [P("chuong", "II")]}, tu=D2)
    env.cmd("thay_cum_tu", {"muc_tieu": [P("dieu", "2")], "kieu": "thay"}, tu=D3, cu="Bản A", moi="Bản B")
    rebuild(env.c, env.vb)
    first = env.dump()
    rebuild(env.c, env.vb)
    assert env.dump() == first
    env.c.execute("UPDATE lenh_sua_doi SET hieu_luc_tu = ? WHERE loai_thao_tac = 'bai_bo'", (D3,))
    rebuild(env.c, env.vb)
    assert "chuong II" in env.snap("2025-12-31") and "chuong II" not in env.snap(D3)
    with pytest.raises(Exception):                                   # lệnh còn được phiên bản dẫn xuất tham chiếu: không xoá thẳng được
        env.c.execute("DELETE FROM lenh_sua_doi WHERE loai_thao_tac = 'bai_bo'")
    clear_derived(env.c, env.vb)
    env.c.execute("DELETE FROM lenh_sua_doi WHERE loai_thao_tac = 'bai_bo'")
    rebuild(env.c, env.vb)
    assert "chuong II" in env.snap(D3) and env.snap(D3)["dieu 2/khoan 2"][1] == "Bản B."


def test_strict_hoan_tac_toan_bo_khi_co_lenh_loi(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "2")}]}, tu=D1, noi_dung="2. Hợp lệ.")
    env.c.commit()
    before = env.dump()
    env.cmd("bai_bo", {"muc_tieu": [P("dieu", "77")]}, tu=D2)
    with pytest.raises(RebuildError) as ei:
        rebuild(env.c, env.vb)
    assert env.dump() == before and "Điều 77" in str(ei.value)
    assert ei.value.report.n_ok == 1 and ei.value.report.n_loi == 1
    rep = rebuild(env.c, env.vb, strict=False)               # xem trước: lệnh hợp lệ vẫn áp, lệnh lỗi bị bỏ qua
    assert [r.ok for r in rep.results] == [True, False] and env.snap(D3)["dieu 2/khoan 2"][1] == "Hợp lệ."


def test_dich_json_hong_va_thao_tac_chua_ho_tro_bao_loi_thay_vi_ngoai_le(env):
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": [{"loai": "dieu"}]}]}, tu=D1, noi_dung="Điều 2. X")
    env.cmd("danh_so_lai", None, tu=D1)
    env.cmd("sua_doi", None, tu=D1, noi_dung="Điều 2. X")
    env.cmd("bo_sung", {"cha": P("dieu", "3")}, tu=D1, noi_dung="Nội dung không có ký hiệu")
    rep = rebuild(env.c, env.vb, strict=False)
    assert [r.ok for r in rep.results] == [False, False, False, False]
    assert "chưa được hỗ trợ" in rep.results[1].problems[0].message
    assert all(p.level == LOI for r in rep.results for p in r.problems if not r.ok)
