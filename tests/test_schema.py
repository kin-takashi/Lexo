"""Kiểm tra schema SQLite (Bước 0): bảng, ràng buộc, trigger chống chồng lấn, truy vấn theo ngày.

Dữ liệu trong test là giả lập ('BLTEST'), không phải số liệu pháp lý thật.
"""
import sqlite3

import pytest

from src.store import SCHEMA_VERSION, connect, init_db

AS_OF = """
    SELECT p.* FROM phien_ban_noi_dung p
    WHERE p.don_vi_id = :dv AND p.hieu_luc_tu <= :x
      AND (p.hieu_luc_den IS NULL OR :x < p.hieu_luc_den)
"""

LOOKUP = """
    SELECT p.noi_dung FROM van_ban v
    JOIN don_vi_luat d ON d.van_ban_id = v.id AND d.loai = 'dieu'
    JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
    WHERE v.ten_viet_tat = :ten AND substr(v.ngay_ban_hanh, 1, 4) = :nam AND p.ky_hieu = :ky
      AND p.hieu_luc_tu <= :x AND (p.hieu_luc_den IS NULL OR :x < p.hieu_luc_den)
"""


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    yield c
    c.close()


def add_van_ban(conn, so_hieu="01/2015/TEST", viet_tat="BLTEST", ban_hanh="2015-01-01", hieu_luc="2016-01-01"):
    return conn.execute(
        "INSERT INTO van_ban (so_hieu, ten_viet_tat, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban,"
        " ngay_hieu_luc) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (so_hieu, viet_tat, "Bộ luật thử nghiệm", "bo_luat", ban_hanh, hieu_luc, hieu_luc),
    ).lastrowid


def add_don_vi(conn, van_ban_id, loai, cha_id=None):
    return conn.execute(
        "INSERT INTO don_vi_luat (van_ban_id, cha_id, loai) VALUES (?, ?, ?)", (van_ban_id, cha_id, loai)
    ).lastrowid


def add_pb(conn, don_vi_id, van_ban_id, ky_hieu, tu, den=None, noi_dung="", thu_tu=1000, tieu_de=None):
    return conn.execute(
        "INSERT INTO phien_ban_noi_dung (don_vi_id, ky_hieu, thu_tu, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den,"
        " van_ban_tao_ra_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (don_vi_id, ky_hieu, thu_tu, tieu_de, noi_dung, tu, den, van_ban_id),
    ).lastrowid


def add_log(conn, van_ban_id=None, vai_tro="sua_doi", phuong_phap="regex"):
    return conn.execute(
        "INSERT INTO log_nap (van_ban_id, file_nguon, vai_tro, phuong_phap, ket_qua)"
        " VALUES (?, 'raw/test.docx', ?, ?, 'thanh_cong')",
        (van_ban_id, vai_tro, phuong_phap),
    ).lastrowid


def add_lenh(conn, nguon, dich, log, thu_tu=1, loai="sua_doi", **extra):
    cols = {"van_ban_nguon_id": nguon, "van_ban_dich_id": dich, "log_nap_id": log,
            "thu_tu": thu_tu, "loai_thao_tac": loai, **extra}
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    return conn.execute(f"INSERT INTO lenh_sua_doi ({names}) VALUES ({marks})", tuple(cols.values())).lastrowid


# ---------- khởi tạo ----------

def test_tables_exist(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"van_ban", "log_nap", "don_vi_luat", "lenh_sua_doi", "phien_ban_noi_dung", "quan_he_van_ban",
            "dieu_khoan_van_ban"} <= names


def test_init_is_idempotent_and_sets_version(conn):
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_init_refuses_other_schema_version():
    c = connect(":memory:")
    c.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError):
        init_db(c)


# ---------- ràng buộc cơ bản ----------

def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_don_vi(conn, 999, "dieu")


def test_so_hieu_is_unique(conn):
    add_van_ban(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_van_ban(conn)


def test_enum_checks(conn):
    vb = add_van_ban(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_don_vi(conn, vb, "khong_co_loai_nay")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE van_ban SET trang_thai = 'sai' WHERE id = ?", (vb,))


@pytest.mark.parametrize("bad", ["2015-02-30", "2015-02-29", "2015-04-31", "2015-13-01", "2015-1-1", "01/02/2015"])
def test_impossible_or_malformed_dates_are_rejected(conn, bad):
    with pytest.raises(sqlite3.IntegrityError):
        add_van_ban(conn, ban_hanh=bad)


def test_leap_day_is_accepted(conn):
    add_van_ban(conn, ban_hanh="2016-02-29", hieu_luc="2016-03-01")


def test_effective_date_cannot_precede_promulgation(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_van_ban(conn, so_hieu="02/2015/TEST", ban_hanh="2016-01-01", hieu_luc="2015-01-01")  # hiệu lực trước ban hành


def test_version_end_cannot_precede_start(conn):
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    with pytest.raises(sqlite3.IntegrityError):
        add_pb(conn, dv, vb, "5", "2018-01-01", "2017-01-01")


def test_empty_interval_is_allowed_and_never_visible(conn):
    """Bản gốc của một Điều bị sửa đúng ngày luật gốc bắt đầu có hiệu lực: khoảng rỗng, chưa từng có hiệu lực."""
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv, vb, "5", "2018-01-01", "2018-01-01", "bản gốc chưa từng hiệu lực")
    add_pb(conn, dv, vb, "5", "2018-01-01", None, "bản sửa")     # nối tiếp đúng mốc: không chồng lấn với bản rỗng
    for x in ("2017-12-31", "2018-01-01", "2030-01-01"):
        got = [r["noi_dung"] for r in conn.execute(AS_OF, {"dv": dv, "x": x})]
        assert "bản gốc chưa từng hiệu lực" not in got
    assert [r["noi_dung"] for r in conn.execute(AS_OF, {"dv": dv, "x": "2018-01-01"})] == ["bản sửa"]
    assert conn.execute("SELECT COUNT(*) FROM phien_ban_noi_dung WHERE don_vi_id = ?", (dv,)).fetchone()[0] == 2     # lịch sử còn


def test_empty_interval_inside_another_version_is_rejected(conn):
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv, vb, "5", "2016-01-01", "2020-01-01")
    with pytest.raises(sqlite3.IntegrityError, match="chong lan"):
        add_pb(conn, dv, vb, "5", "2018-01-01", "2018-01-01")


# ---------- khoảng hiệu lực ----------

def test_overlapping_versions_are_rejected(conn):
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv, vb, "5", "2016-01-01", "2018-01-01")
    with pytest.raises(sqlite3.IntegrityError, match="chong lan"):
        add_pb(conn, dv, vb, "5", "2017-01-01", None)
    with pytest.raises(sqlite3.IntegrityError, match="chong lan"):
        add_pb(conn, dv, vb, "5", "2015-06-01", "2016-06-01")


def test_adjacent_versions_and_other_nodes_are_allowed(conn):
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv, vb, "5", "2016-01-01", "2018-01-01")
    add_pb(conn, dv, vb, "5", "2018-01-01", None)  # nối tiếp đúng mốc: hợp lệ
    dv2 = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv2, vb, "6", "2016-01-01")  # nút khác được trùng khoảng


def test_close_then_insert_works_and_extending_is_rejected(conn):
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    old = add_pb(conn, dv, vb, "5", "2016-01-01", None)
    conn.execute("UPDATE phien_ban_noi_dung SET hieu_luc_den = '2018-01-01' WHERE id = ?", (old,))
    add_pb(conn, dv, vb, "5", "2018-01-01", None)
    with pytest.raises(sqlite3.IntegrityError, match="chong lan"):
        conn.execute("UPDATE phien_ban_noi_dung SET hieu_luc_den = '2019-01-01' WHERE id = ?", (old,))


def test_as_of_query_handles_open_ended_version(conn):
    vb = add_van_ban(conn)
    dv = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv, vb, "5", "2016-01-01", "2018-01-01", "bản gốc")
    add_pb(conn, dv, vb, "5", "2018-01-01", None, "bản sửa")

    def at(x):
        return [r["noi_dung"] for r in conn.execute(AS_OF, {"dv": dv, "x": x})]

    assert at("2015-12-31") == []
    assert at("2016-01-01") == ["bản gốc"]
    assert at("2017-12-31") == ["bản gốc"]
    assert at("2018-01-01") == ["bản sửa"]  # sát mốc chuyển giao
    assert at("2099-01-01") == ["bản sửa"]  # hieu_luc_den NULL vẫn khớp


# ---------- cây đơn vị và tra chính xác ----------

def test_exact_lookup_by_abbreviation_year_and_symbol(conn):
    vb = add_van_ban(conn)
    old = add_van_ban(conn, so_hieu="99/1999/TEST", ban_hanh="1999-01-01", hieu_luc="2000-01-01")  # cùng viết tắt, khác năm
    chuong = add_don_vi(conn, vb, "chuong")
    add_pb(conn, chuong, vb, "XIX", "2016-01-01", tieu_de="Chương thử")
    d173 = add_don_vi(conn, vb, "dieu", chuong)
    d173a = add_don_vi(conn, vb, "dieu", chuong)
    add_pb(conn, d173, vb, "173", "2016-01-01", noi_dung="trộm cắp")
    add_pb(conn, d173a, vb, "173a", "2018-01-01", noi_dung="điều chèn")
    d_old = add_don_vi(conn, old, "dieu")
    add_pb(conn, d_old, old, "173", "2000-01-01", noi_dung="bản 1999")

    def lookup(ky, x="2019-01-01", nam="2015"):
        return [r[0] for r in conn.execute(LOOKUP, {"ten": "BLTEST", "nam": nam, "ky": ky, "x": x})]

    assert lookup("173") == ["trộm cắp"]
    assert lookup("173a") == ["điều chèn"]  # ký hiệu là TEXT
    assert lookup("173a", x="2017-12-31") == []  # chưa có hiệu lực
    assert lookup("173", nam="1999") == ["bản 1999"]


def test_renumbering_is_new_versions_of_the_same_node(conn):
    vb = add_van_ban(conn)
    dieu = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dieu, vb, "5", "2016-01-01", tieu_de="Điều thử")
    khoan = add_don_vi(conn, vb, "khoan", dieu)
    add_pb(conn, khoan, vb, "3", "2016-01-01", "2018-01-01", "nội dung khoản")
    add_pb(conn, khoan, vb, "4", "2018-01-01", None, "nội dung khoản", thu_tu=2000)  # cùng nút, đổi ký hiệu

    q = """SELECT count(*) FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
           WHERE d.cha_id = :dieu AND p.ky_hieu = :ky AND p.hieu_luc_tu <= :x
             AND (p.hieu_luc_den IS NULL OR :x < p.hieu_luc_den)"""

    def has(ky, x):
        return conn.execute(q, {"dieu": dieu, "ky": ky, "x": x}).fetchone()[0] == 1

    assert has("3", "2017-06-01") and not has("4", "2017-06-01")
    assert has("4", "2019-01-01") and not has("3", "2019-01-01")


def test_khoan_with_points_keeps_lead_in_text(conn):
    vb = add_van_ban(conn)
    dieu = add_don_vi(conn, vb, "dieu")
    khoan = add_don_vi(conn, vb, "khoan", dieu)
    add_pb(conn, khoan, vb, "1", "2016-01-01", noi_dung="Người nào ... thì bị phạt:")
    for i, ky in enumerate(["a", "b", "c"], start=1):
        diem = add_don_vi(conn, vb, "diem", khoan)
        add_pb(conn, diem, vb, ky, "2016-01-01", noi_dung=f"điểm {ky}", thu_tu=i * 1000)

    rows = conn.execute(
        "SELECT p.ky_hieu FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id"
        " WHERE d.cha_id = ? ORDER BY p.thu_tu", (khoan,)
    ).fetchall()
    assert [r["ky_hieu"] for r in rows] == ["a", "b", "c"]
    lead = conn.execute("SELECT noi_dung FROM phien_ban_noi_dung WHERE don_vi_id = ?", (khoan,)).fetchone()[0]
    assert lead.endswith("thì bị phạt:")


# ---------- lệnh sửa đổi và quan hệ văn bản ----------

def test_lenh_sua_doi_rules(conn):
    nguon = add_van_ban(conn, so_hieu="02/2017/TEST", ban_hanh="2017-06-01", hieu_luc="2018-01-01")
    dich = add_van_ban(conn)
    log = add_log(conn, nguon)

    add_lenh(conn, nguon, dich, log, thu_tu=1)  # chờ duyệt: chưa cần hieu_luc_tu
    with pytest.raises(sqlite3.IntegrityError):  # đã duyệt thì bắt buộc có hieu_luc_tu
        add_lenh(conn, nguon, dich, log, thu_tu=2, trang_thai_duyet="da_duyet")
    add_lenh(conn, nguon, dich, log, thu_tu=2, trang_thai_duyet="da_duyet", hieu_luc_tu="2018-01-01")

    with pytest.raises(sqlite3.IntegrityError):  # trùng thứ tự trong cùng đợt trích xuất
        add_lenh(conn, nguon, dich, log, thu_tu=1)
    with pytest.raises(sqlite3.IntegrityError):  # thao tác lạ
        add_lenh(conn, nguon, dich, log, thu_tu=3, loai="thao_tac_la")
    with pytest.raises(sqlite3.IntegrityError):  # JSON hỏng
        add_lenh(conn, nguon, dich, log, thu_tu=3, lenh_goc_json="{hong")
    with pytest.raises(sqlite3.IntegrityError):  # ngày sai
        add_lenh(conn, nguon, dich, log, thu_tu=3, ngay_hieu_luc_moi="2018-13-40")
    with pytest.raises(sqlite3.IntegrityError):  # dich_json không phải JSON
        add_lenh(conn, nguon, dich, log, thu_tu=3, dich_json="{hong")
    add_lenh(conn, nguon, dich, log, thu_tu=3, dich_json='{"muc_tieu": []}', vi_tri_nguon="Điều 1 khoản 2",
             can_cu_hieu_luc="Điều 3 (mặc định)", khoi_nguon="D1.2", nguon_dong_tu=5, nguon_dong_den=9)
    with pytest.raises(sqlite3.IntegrityError):  # dòng đến < dòng từ
        add_lenh(conn, nguon, dich, log, thu_tu=4, nguon_dong_tu=9, nguon_dong_den=5)

    log2 = add_log(conn, nguon)  # đợt trích xuất khác (vd so sánh mô hình local với API): cùng thứ tự được
    add_lenh(conn, nguon, dich, log2, thu_tu=1)
    add_lenh(conn, nguon, dich, log2, thu_tu=2, loai="hoan_hieu_luc", ngay_hieu_luc_moi="2018-01-01")  # nhắm cả văn bản


def test_quan_he_van_ban_rules(conn):
    a = add_van_ban(conn, so_hieu="A/TEST")
    b = add_van_ban(conn, so_hieu="B/TEST")
    ins = "INSERT INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id) VALUES (?, ?, ?)"
    conn.execute(ins, (a, "sua_doi", b))
    conn.execute(ins, (a, "hoan_hieu_luc", b))  # cùng cặp, khác loại: được
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, (a, "sua_doi", b))  # trùng
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, (a, "sua_doi", a))  # tự quan hệ
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, (a, "quan_he_la", b))


# ---------- v2: vai trò nạp, ngày hiệu lực kép, nút do lệnh tạo, điều khoản chuyển tiếp ----------

def test_log_nap_requires_role_and_method(conn):
    vb = add_van_ban(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_log(conn, vb, vai_tro="vai_la")
    with pytest.raises(sqlite3.IntegrityError):
        add_log(conn, vb, phuong_phap="phuong_phap_la")
    for role in ("goc", "sua_doi", "hoan_dinh_chi"):
        add_log(conn, vb, vai_tro=role)          # một văn bản có thể có nhiều vai qua nhiều lần nạp
    add_log(conn, vb, phuong_phap="llm")


def test_effective_date_as_written_vs_actual_are_separate_columns(conn):
    vb = add_van_ban(conn, hieu_luc="2016-07-01")
    conn.execute("UPDATE van_ban SET ngay_hieu_luc = '2018-01-01' WHERE id = ?", (vb,))       # sau nghị quyết hoãn
    row = conn.execute("SELECT ngay_hieu_luc_theo_van_ban, ngay_hieu_luc FROM van_ban WHERE id = ?", (vb,)).fetchone()
    assert (row[0], row[1]) == ("2016-07-01", "2018-01-01")
    with pytest.raises(sqlite3.IntegrityError):                                                # theo văn bản cũng phải sau ban hành
        conn.execute("UPDATE van_ban SET ngay_hieu_luc_theo_van_ban = '2014-01-01' WHERE id = ?", (vb,))


def test_node_created_by_command_is_marked(conn):
    vb = add_van_ban(conn)
    nguon = add_van_ban(conn, so_hieu="02/2017/TEST", ban_hanh="2017-06-01", hieu_luc="2018-01-01")
    lenh = add_lenh(conn, nguon, vb, add_log(conn, nguon), loai="bo_sung")
    base = add_don_vi(conn, vb, "dieu")
    moi = conn.execute("INSERT INTO don_vi_luat (van_ban_id, loai, lenh_tao_ra_id) VALUES (?, 'dieu', ?)", (vb, lenh)).lastrowid
    rows = {r["id"]: r["lenh_tao_ra_id"] for r in conn.execute("SELECT id, lenh_tao_ra_id FROM don_vi_luat")}
    assert rows[base] is None and rows[moi] == lenh


def test_provenance_columns_link_version_to_law_and_command(conn):
    vb = add_van_ban(conn)
    nguon = add_van_ban(conn, so_hieu="02/2017/TEST", ban_hanh="2017-06-01", hieu_luc="2018-01-01")
    lenh = add_lenh(conn, nguon, vb, add_log(conn, nguon), vi_tri_nguon="Điều 1 khoản 21", hieu_luc_tu="2018-01-01",
                    trang_thai_duyet="da_duyet")
    dv = add_don_vi(conn, vb, "dieu")
    add_pb(conn, dv, vb, "113", "2016-01-01", "2018-01-01", "gốc")
    conn.execute(
        "INSERT INTO phien_ban_noi_dung (don_vi_id, ky_hieu, thu_tu, noi_dung, hieu_luc_tu, van_ban_tao_ra_id, lenh_tao_ra_id)"
        " VALUES (?, '113', 1000, 'sửa', '2018-01-01', ?, ?)", (dv, nguon, lenh))
    row = conn.execute(
        "SELECT v.so_hieu, l.vi_tri_nguon FROM phien_ban_noi_dung p JOIN van_ban v ON v.id = p.van_ban_tao_ra_id"
        " JOIN lenh_sua_doi l ON l.id = p.lenh_tao_ra_id WHERE p.hieu_luc_tu = '2018-01-01'").fetchone()
    assert (row[0], row[1]) == ("02/2017/TEST", "Điều 1 khoản 21")


def test_dieu_khoan_van_ban_rules(conn):
    vb = add_van_ban(conn)
    ins = "INSERT INTO dieu_khoan_van_ban (van_ban_id, loai, vi_tri, noi_dung) VALUES (?, ?, ?, ?)"
    conn.execute(ins, (vb, "hieu_luc", "Điều 3", "Luật này có hiệu lực từ ..."))
    conn.execute(ins, (vb, "chuyen_tiep", "Điều 4", "Kể từ ngày ..."))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, (vb, "hieu_luc", "Điều 3", "trùng"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, (vb, "loai_la", "Điều 5", "x"))
