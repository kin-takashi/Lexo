"""db/du_lieu.sqlite: schema, nhập tập huấn luyện / bộ đo / nhật ký sửa nhãn / bộ bản án, chỉ ghi thêm, tầng tin cậy, xuất ngược khớp nguồn."""
import json
import sqlite3

import pytest

from src.dulieu import kho, nhap
from src.index import bo_cau_hoi, tap_train

VAN_A = "Anh A thấy chiếc xe máy dựng trước cửa hàng nên lén dắt đi bán lấy tiền tiêu xài."
VAN_B = "Chị B cho người quen vay tiền rồi bị bỏ trốn, sau đó phát hiện người này còn đập phá cửa kính nhà chị."


def mau(id_, van, hv, loai="don", trang_thai="da_duyet", nguon="claude"):
    return {"id": id_, "tinh_huong": van, "hanh_vi": hv, "loai": loai, "nguon": nguon, "trang_thai": trang_thai}


def hv(mo_ta, *dieu):
    return {"mo_ta": mo_ta, "dieu": list(dieu)}


def cau(id_, q, dieu, loai="don", tap="dev", trang_thai="nhap", nguon="claude"):
    return {"id": id_, "cau_hoi": q, "dieu": list(dieu), "loai": loai, "tap": tap, "nguon": nguon, "trang_thai": trang_thai}


TRAIN = [
    mau("t001", VAN_A, [hv("lén lấy trộm một chiếc xe máy rồi đem bán", "173", "172")]),
    mau("t002", VAN_B, [hv("lừa vay tiền rồi bỏ trốn không trả", "174"), hv("đập phá cửa kính nhà người khác", "178")],
        loai="nhieu", trang_thai="nhap"),
]
DO = [
    cau("d01", "ép vợ hoặc chồng phải ly hôn, hoặc cấm không cho hai người yêu nhau cưới nhau", ["181"], tap="dev"),
    cau("d02", "người nhận hối lộ rồi mới nhờ giúp đỡ người đưa tiền", ["354", "364"], tap="kiem_tra", trang_thai="da_duyet"),
    cau("q01", "một tình huống nhiều hành vi khác nhau của cùng một người trong một đêm", ["173", "178"], loai="nhieu_dieu", tap="kiem_tra"),
    cau("p01", "bán thực phẩm đã hết hạn sử dụng cho khách hàng ở chợ", ["193"], tap="phu", trang_thai="da_duyet"),
]

NHAT_KY = """# Nhật ký áp bản vá `sua_nhan_train.md` (2026-10-14)

## 1. Mục khác bản vá

| Mục | Bản vá | Đã làm | Căn cứ trong văn bản Điều |
|---|---|---|---|
| t001 | Thêm «đã bị xử phạt» | Không thêm | Điều luật không đòi điều kiện này. |
| t002 | Đổi 291 → 288 | Đổi 288 và thêm số tiền | Điều 288 đòi thu lợi từ 50 triệu. |

## 2. Mục áp đúng bản vá

| Mục | Thay đổi |
|---|---|
| t003 | nhãn `185 + 186` → `140 + 186`; đề sửa |
| t004 | đề sửa; mô tả hành vi sửa |

## 3. Quy tắc đã chốt

- ghi chú tự do, không phải bảng
"""
BAN_VA = """# Bản sửa tập train

## A. Sai Điều (2 mục)

| Mục | Hành động | Hiện tại | Sửa thành | Lý do | Mức chắc |
|---|---|---|---|---|---|
| t003 | ĐỔI NHÃN | HV1: 185 | HV1: **140** | Nạn nhân không thuộc danh sách chủ thể. | TB |

## B. Thiếu yếu tố (1 mục)

| Mục | Câu cần thêm vào đề | Mức chắc |
|---|---|---|
| t004 | Cuối đoạn: thêm «đã từng bị xử phạt hành chính». | KC |

## C. Không nhất quán

| Mục | Hành động | Chi tiết | Mức chắc |
|---|---|---|---|
| t001 | THÊM HV | Thêm hành vi mới | TB ⚠ |
| t002 | SỬA ĐỀ | Bổ sung yếu tố | Cao |

## Việc cần bạn quyết thêm

| Mục | không phải dữ liệu |
|---|---|
"""
TRAIN4 = TRAIN + [
    mau("t003", "Chiếc xe đạp để ngoài sân bị một thanh niên lạ mặt lén lấy đi vào ban đêm khi cả nhà ngủ.", [hv("lén lấy trộm chiếc xe đạp", "173")]),
    mau("t004", "Ông C mở lò mổ lậu rồi bán thịt không kiểm dịch cho các quán ăn quanh khu phố.", [hv("bán thịt không kiểm dịch cho quán ăn", "317")]),
]


def ghi(tmp_path, ten, noi_dung):
    p = tmp_path / ten
    p.write_text(noi_dung if isinstance(noi_dung, str) else json.dumps(noi_dung, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def nguon(tmp_path):
    return {
        "train": ghi(tmp_path, "tinh_huong.json", {"phien_ban": 1, "ghi_chu": "ghi chú train", "mau": TRAIN4}),
        "do": ghi(tmp_path, "bo_cau_hoi.json", {"phien_ban": 1, "ghi_chu": "ghi chú đo", "cau_hoi": DO}),
        "nhat_ky": ghi(tmp_path, "nhat_ky.md", NHAT_KY),
        "ban_va": ghi(tmp_path, "sua_nhan_train.md", BAN_VA),
    }


@pytest.fixture
def db(nguon):
    conn = kho.connect()
    kho.init_db(conn)
    nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"])
    return conn


def test_schema_tao_duoc_va_goi_lai_an_toan():
    conn = kho.connect()
    kho.init_db(conn)
    kho.init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == kho.SCHEMA_VERSION
    ten = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    assert {"log_nhap", "mau", "hanh_vi", "nhan_dieu", "lich_su_nhan", "duyet", "ban_an_meta", "v_tin_cay", "v_trung_van_ban",
            "v_trung_ban_an"} <= ten


def test_schema_phien_ban_khac_bao_loi():
    conn = kho.connect()
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="--reset"):
        kho.init_db(conn)


def test_nhap_dem_dung_va_nhom_dap_an(db):
    n = lambda sql, *a: db.execute(sql, a).fetchone()[0]
    assert n("SELECT COUNT(*) FROM mau WHERE bo = 'train'") == 4 and n("SELECT COUNT(*) FROM mau WHERE bo = 'do'") == 4
    assert n("SELECT COUNT(*) FROM hanh_vi") == 1 + 2 + 1 + 1
    # train: nhóm = thứ tự hành vi; các Điều chấp nhận của một hành vi cùng nhóm
    t1 = db.execute("SELECT nhom, dieu FROM nhan_dieu WHERE mau_id = (SELECT id FROM mau WHERE ma = 't001') ORDER BY thu_tu").fetchall()
    assert [(r["nhom"], r["dieu"]) for r in t1] == [(1, "173"), (1, "172")]
    t2 = db.execute("SELECT nhom, dieu FROM nhan_dieu WHERE mau_id = (SELECT id FROM mau WHERE ma = 't002') ORDER BY nhom").fetchall()
    assert [(r["nhom"], r["dieu"]) for r in t2] == [(1, "174"), (2, "178")]
    # đo: loại don = MỘT nhóm chấp nhận; nhieu_dieu = mỗi Điều một nhóm (phải tìm đủ)
    d2 = db.execute("SELECT nhom FROM nhan_dieu WHERE mau_id = (SELECT id FROM mau WHERE ma = 'd02')").fetchall()
    q1 = db.execute("SELECT nhom FROM nhan_dieu WHERE mau_id = (SELECT id FROM mau WHERE ma = 'q01') ORDER BY nhom").fetchall()
    assert {r["nhom"] for r in d2} == {1} and [r["nhom"] for r in q1] == [1, 2]
    assert nhap.kiem_tra_toan_ven(db) == []


def test_xuat_nguoc_khop_nguon(db, nguon):
    assert nhap.xuat_train(db) == tap_train.doc_train(nguon["train"])
    assert nhap.xuat_do(db) == bo_cau_hoi.doc_tho(nguon["do"])["cau_hoi"]


def test_nhap_lai_cung_file_khong_nhan_doi(db, nguon):
    kq = nhap.nhap_tat_ca(db, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"])
    assert kq == {"train": 0, "do": 0, "sua_nhan": 0}
    assert db.execute("SELECT COUNT(*) FROM mau").fetchone()[0] == 8
    assert db.execute("SELECT COUNT(*) FROM log_nhap").fetchone()[0] == 4


def test_file_nguon_doi_phai_reset(db, nguon):
    d = json.loads(nguon["train"].read_text(encoding="utf-8"))
    d["mau"][0]["hanh_vi"][0]["dieu"] = ["173"]
    nguon["train"].write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(nhap.NhapError, match="--reset"):
        nhap.nhap_tat_ca(db, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"])


def test_loi_o_buoc_sau_hoan_tac_ca_giao_dich(nguon, tmp_path):
    conn = kho.connect()
    kho.init_db(conn)
    xau = ghi(tmp_path, "xau.md", NHAT_KY.replace("| t003 |", "| t999 |"))          # t999 không có trong tập huấn luyện
    with pytest.raises(nhap.NhapError):
        nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], xau, nguon["ban_va"])
    assert conn.execute("SELECT COUNT(*) FROM mau").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM log_nhap").fetchone()[0] == 0


def test_bat_ro_ri_cung_van_ban_voi_bo_do(nguon, tmp_path):
    train = [mau("t001", "Ép vợ hoặc chồng phải ly hôn, hoặc cấm không cho hai người yêu nhau cưới nhau", [hv("ép buộc ly hôn", "181")])]
    conn = kho.connect()
    kho.init_db(conn)
    with pytest.raises(nhap.NhapError, match="không hợp lệ"):
        nhap.nhap_tat_ca(conn, ghi(tmp_path, "x.json", {"mau": train}), nguon["do"], None, None)


def test_duyet_suy_ra_tu_trang_thai(db):
    r = db.execute("SELECT nguoi, vai_tro, ket_qua, suy_ra, ngay FROM duyet d JOIN mau m ON m.id = d.mau_id WHERE m.ma = 't001'").fetchone()
    assert (r["nguoi"], r["vai_tro"], r["ket_qua"], r["suy_ra"], r["ngay"]) == ("Kintakashi", "tac_gia", "dong_y", 1, "2026-10-14")
    # t002 trang_thai = nhap → không có dòng duyệt; d02 (kiem_tra) lấy ngày file nêu; d01 (dev, nhap) không có
    assert db.execute("SELECT COUNT(*) FROM duyet d JOIN mau m ON m.id = d.mau_id WHERE m.ma IN ('t002', 'd01')").fetchone()[0] == 0
    assert db.execute("SELECT ngay FROM duyet d JOIN mau m ON m.id = d.mau_id WHERE m.ma = 'd02'").fetchone()[0] == "2026-10-07"


def test_tang_tin_cay(db):
    def tang(ma):
        return db.execute("SELECT tang FROM v_tin_cay WHERE ma = ?", (ma,)).fetchone()["tang"]

    def them(ma, nguoi, vai, kq):
        db.execute("INSERT INTO duyet (mau_id, nguoi, vai_tro, ket_qua) VALUES ((SELECT id FROM mau WHERE ma = ?), ?, ?, ?)", (ma, nguoi, vai, kq))

    assert tang("t001") == "bac" and tang("t002") == "nhap"                      # chỉ tác giả duyệt / chưa ai duyệt
    them("t001", "SV1", "sinh_vien_luat", "dong_y")
    assert tang("t001") == "bac"                                                 # một sinh viên chưa đủ
    them("t001", "SV2", "sinh_vien_luat", "dong_y")
    assert tang("t001") == "vang"                                                # hai sinh viên khác nhau đồng ý
    them("t002", "LS1", "nguoi_phap_ly", "dong_y")
    assert tang("t002") == "vang"                                                # một người pháp lý đồng ý
    them("t001", "LS2", "nguoi_phap_ly", "sua")
    assert tang("t001") == "tranh_chap"                                          # có người độc lập đòi sửa
    them("d01", "claude-x", "mo_hinh", "dong_y")
    assert tang("d01") == "nhap"                                                 # mô hình không được tính


def test_chi_ghi_them(db):
    with pytest.raises(sqlite3.IntegrityError, match="chỉ được ghi thêm"):
        db.execute("UPDATE duyet SET ket_qua = 'tu_choi'")
    with pytest.raises(sqlite3.IntegrityError, match="chỉ được ghi thêm"):
        db.execute("DELETE FROM duyet")
    with pytest.raises(sqlite3.IntegrityError, match="chỉ được ghi thêm"):
        db.execute("UPDATE lich_su_nhan SET ngay = '2026-01-01'")
    with pytest.raises(sqlite3.IntegrityError, match="chỉ được ghi thêm"):
        db.execute("DELETE FROM lich_su_nhan")
    with pytest.raises(sqlite3.IntegrityError):                                  # mẫu đã có lịch sử/duyệt thì không xóa được
        db.execute("DELETE FROM mau WHERE ma = 't001'")


def test_rang_buoc_gia_tri(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE mau SET trang_thai = 'xong' WHERE ma = 't002'")
    with pytest.raises(sqlite3.IntegrityError):                                   # bo đo không thể có tap = train
        db.execute("INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) "
                   "VALUES ('do', 'z', 'train', 'x', ?, 'don', 'claude', 'nhap', 1)", ("0" * 64,))
    with pytest.raises(sqlite3.IntegrityError):                                   # loai nhieu_dieu không thuộc bộ huấn luyện
        db.execute("INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) "
                   "VALUES ('train', 'z', 'train', 'x', ?, 'nhieu_dieu', 'claude', 'nhap', 1)", ("0" * 64,))


def test_trung_van_ban_nhin_thay_qua_view(db):
    db.execute("INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) "
               "SELECT 'train', 'tx', 'train', 'x', hash_van_ban, 'don', 'claude', 'nhap', log_nhap_id FROM mau WHERE ma = 'd01'")
    assert [(r["ma_train"], r["ma_do"]) for r in db.execute("SELECT ma_train, ma_do FROM v_trung_van_ban")] == [("tx", "d01")]
    assert any("trùng nguyên văn" in x for x in nhap.kiem_tra_toan_ven(db))


def test_sua_nhan_ghep_nhat_ky_voi_ban_va(db):
    r = {x["ma"]: x for x in db.execute(
        "SELECT m.ma, l.* FROM lich_su_nhan l JOIN mau m ON m.id = l.mau_id")}
    assert len(r) == 4
    assert r["t001"]["nhom_xu_ly"] == "khong_ap" and r["t002"]["nhom_xu_ly"] == "ap_co_chinh"
    assert r["t003"]["nhom_xu_ly"] == "ap_dung_dung" and (r["t003"]["nhan_truoc"], r["t003"]["nhan_sau"]) == ("185 + 186", "140 + 186")
    assert r["t004"]["nhan_truoc"] is None and r["t004"]["nhan_sau"] is None        # nhật ký không ghi nhãn cũ thì không bịa
    assert (r["t003"]["nhom_ban_va"], r["t003"]["hanh_dong"], r["t003"]["muc_chac"]) == ("A", "ĐỔI NHÃN", "TB")
    assert (r["t004"]["nhom_ban_va"], r["t004"]["hanh_dong"], r["t004"]["muc_chac"]) == ("B", "SỬA ĐỀ", "KC")
    assert r["t001"]["muc_chac"] == "TB"                                            # «TB ⚠» → TB
    assert r["t003"]["ngay"] == "2026-10-14" and (r["t003"]["nguoi_de_xuat"], r["t003"]["nguoi_quyet"]) == ("Claude", "Kintakashi")


def test_ban_va_va_nhat_ky_lech_nhau_bao_loi(nguon, tmp_path):
    conn = kho.connect()
    kho.init_db(conn)
    thieu = ghi(tmp_path, "thieu.md", BAN_VA.replace("| t002 | SỬA ĐỀ | Bổ sung yếu tố | Cao |\n", ""))
    with pytest.raises(nhap.NhapError, match="chỉ có ở nhật ký"):
        nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], nguon["nhat_ky"], thieu)


def test_ban_va_hang_thieu_cot_hoac_muc_chac(tmp_path):
    with pytest.raises(nhap.NhapError, match="phải có 6 cột"):
        nhap.doc_ban_va(ghi(tmp_path, "a.md", "## A. x\n\n| t001 | ĐỔI NHÃN | a | b | TB |\n"))
    with pytest.raises(nhap.NhapError, match="mức chắc"):
        nhap.doc_ban_va(ghi(tmp_path, "b.md", "## B. x\n\n| t001 | thêm câu | Chưa rõ |\n"))
    with pytest.raises(nhap.NhapError, match="hai lần"):
        nhap.doc_nhat_ky(ghi(tmp_path, "c.md", "# x (2026-10-14)\n\n## 2. y\n\n| t001 | a |\n| t001 | b |\n"))


def test_hash_van_chuan_hoa():
    assert nhap.hash_van("Anh  A\n lấy  xe") == nhap.hash_van("anh a lấy xe")
    assert nhap.hash_van("a") != nhap.hash_van("b")


# ---- bộ bản án (bo = 'ban_an') ------------------------------------------------------------------------

def ba(ma, tap, dieu, dau_vao=None, nhom_vu=None, **kw):
    b = {"ma": ma, "tap": tap, "dieu": list(dieu), "dau_vao": dau_vao or f"Sự việc của bản án {ma}: bị cáo lấy tài sản của người khác.",
         "nhom_vu": nhom_vu or ma, "nguon_nhan": "so_tham_trich", "so_ban_an": f"{ma[-1]}/2025/HS-PT", "cap": "phuc_tham",
         "cap_dataset": "First-instance", "ngay": "2025-02-03", "toa_an": "TÒA ÁN NHÂN DÂN TỈNH XYZ", "so_tham_tham_chieu": None,
         "toi_danh": ["Trộm cắp tài sản"], "da_che": {"dan_chieu_blhs": 1}, "ten_toi_trong_loi_ke": 0, "lo_nhan_con_lai": {}}
    b.update(kw)
    return b


BAN_AN = [ba("TAND1", "test", ["173"]), ba("TAND2", "train", ["174", "341"]), ba("TAND3", "test", ["123"], ngay="2025-13-40", toa_an=None)]


def file_ban_an(tmp_path, mau_ba=BAN_AN, ten="ban_an.json"):
    return ghi(tmp_path, ten, {"nguon": {"dataset": "tmquan/anle-toaan-gov-vn", "file": "x.parquet", "sha256": "0" * 64}, "mau": mau_ba})


@pytest.fixture
def db_ba(nguon, tmp_path):
    conn = kho.connect()
    kho.init_db(conn)
    p = file_ban_an(tmp_path)
    kq = nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"], p)
    assert kq["ban_an"] == 3
    return conn, p


def test_ban_an_nhap_nhan_tang_vang_va_meta(db_ba):
    db, _ = db_ba
    r = {x["ma"]: x for x in db.execute("SELECT m.ma, m.tap, m.loai, m.nguon, m.trang_thai, v.tang FROM mau m JOIN v_tin_cay v ON v.mau_id = m.id "
                                        "WHERE m.bo = 'ban_an'")}
    assert {m: (x["tap"], x["loai"], x["tang"]) for m, x in r.items()} == {
        "TAND1": ("test", "don", "vang"), "TAND2": ("train", "nhieu_dieu", "vang"), "TAND3": ("test", "don", "vang")}
    assert {x["nguon"] for x in r.values()} == {"ban_an"} and {x["trang_thai"] for x in r.values()} == {"nhap"}
    nhom = [(x["nhom"], x["dieu"]) for x in db.execute(
        "SELECT nhom, dieu FROM nhan_dieu WHERE mau_id = (SELECT id FROM mau WHERE bo = 'ban_an' AND ma = 'TAND2') ORDER BY nhom")]
    assert nhom == [(1, "174"), (2, "341")]                                       # mỗi Điều một nhóm: phải tìm đủ
    d = db.execute("SELECT d.nguoi, d.vai_tro, d.suy_ra, d.ngay, d.ghi_chu FROM duyet d JOIN mau m ON m.id = d.mau_id WHERE m.ma = 'TAND3'").fetchone()
    assert (d["vai_tro"], d["suy_ra"], d["ngay"]) == ("toa_an", 1, None)          # ngày không hợp lệ -> để trống, không bịa
    assert d["nguoi"].startswith("Tòa án") and "đọc tự động" in d["ghi_chu"]
    meta = db.execute("SELECT * FROM ban_an_meta b JOIN mau m ON m.id = b.mau_id WHERE m.ma = 'TAND1'").fetchone()
    assert (meta["cap"], meta["cap_dataset"], meta["ngay_ban_an"], json.loads(meta["toi_danh"])) == (
        "phuc_tham", "First-instance", "2025-02-03", ["Trộm cắp tài sản"])
    assert nhap.kiem_tra_toan_ven(db) == []


def test_ban_an_xuat_nguoc_khop_va_nhap_lai_khong_doi(db_ba, nguon):
    db, p = db_ba
    assert nhap.xuat_ban_an(db) == nhap.doc_ban_an_de_doi_chieu(p)
    kq = nhap.nhap_tat_ca(db, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"], p)
    assert kq == {"train": 0, "do": 0, "sua_nhan": 0, "ban_an": 0}
    assert db.execute("SELECT COUNT(*) FROM mau WHERE bo = 'ban_an'").fetchone()[0] == 3


def test_ban_an_khong_lam_doi_tang_cua_bo_cu(db_ba):
    db, _ = db_ba
    t = {(r["bo"], r["tang"]): r["n"] for r in db.execute("SELECT bo, tang, COUNT(*) n FROM v_tin_cay WHERE bo <> 'ban_an' GROUP BY 1, 2")}
    assert ("train", "vang") not in t and ("do", "vang") not in t


@pytest.mark.parametrize("xau, khop", [
    ([ba("A", "dev", ["173"])], "tap phải là"),
    ([ba("A", "test", [])], "rỗng hoặc lặp"),
    ([ba("A", "test", ["173"], lo_nhan_con_lai={"dieu_luat": 1})], "còn lộ nhãn"),
    ([ba("A", "test", ["173"], nhom_vu="g"), ba("B", "train", ["173"], nhom_vu="g")], "cả hai tập"),
    ([ba("A", "test", ["173"]), ba("A", "train", ["174"])], "trùng mã"),
])
def test_ban_an_file_xau_bi_tu_choi_va_hoan_tac(nguon, tmp_path, xau, khop):
    conn = kho.connect()
    kho.init_db(conn)
    with pytest.raises(nhap.NhapError, match=khop):
        nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"], file_ban_an(tmp_path, xau))
    assert conn.execute("SELECT COUNT(*) FROM mau").fetchone()[0] == 0


def test_ban_an_trung_van_ban_bo_khac_hien_qua_view(nguon, tmp_path):
    conn = kho.connect()
    kho.init_db(conn)
    p = file_ban_an(tmp_path, [ba("A", "test", ["181"], dau_vao=DO[0]["cau_hoi"]), ba("B", "train", ["173"], dau_vao="x y z"),
                               ba("C", "test", ["173"], dau_vao="X  y z")])
    nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], nguon["nhat_ky"], nguon["ban_va"], p)
    trung = {(r["ma_ban_an"], r["ma_khac"]) for r in conn.execute("SELECT ma_ban_an, ma_khac FROM v_trung_ban_an")}
    assert trung == {("A", "d01"), ("B", "C")}
    assert sum("trùng nguyên văn" in x for x in nhap.kiem_tra_toan_ven(conn)) == 2


def test_ban_an_rang_buoc_bo_tap(db_ba):
    db, _ = db_ba
    with pytest.raises(sqlite3.IntegrityError):                                   # bộ bản án chỉ có tap train / test
        db.execute("INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) "
                   "VALUES ('ban_an', 'z', 'dev', 'x', ?, 'don', 'ban_an', 'nhap', 1)", ("0" * 64,))
    with pytest.raises(sqlite3.IntegrityError):                                   # bộ đo không có tap = test
        db.execute("INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) "
                   "VALUES ('do', 'z', 'test', 'x', ?, 'don', 'claude', 'nhap', 1)", ("0" * 64,))


BAN_AN_THAT = pytest.mark.skipif(not nhap.BAN_AN_MAC_DINH.exists(), reason="chưa có inbox/anle_hf/ban_an_hinh_su.json")


@BAN_AN_THAT
def test_ban_an_that_nhap_duoc_va_khop(nguon):
    conn = kho.connect()
    kho.init_db(conn)
    kq = nhap.nhap_tat_ca(conn, nguon["train"], nguon["do"], None, None, nhap.BAN_AN_MAC_DINH)
    assert kq["ban_an"] > 150
    assert nhap.xuat_ban_an(conn) == nhap.doc_ban_an_de_doi_chieu()
    assert nhap.kiem_tra_toan_ven(conn) == []
    assert {r[0] for r in conn.execute("SELECT DISTINCT tang FROM v_tin_cay WHERE bo = 'ban_an'")} == {"vang"}


# ---- file thật (bỏ qua nếu thiếu) ------------------------------------------------------------------

THAT = pytest.mark.skipif(not (nhap.TRAIN_MAC_DINH.exists() and nhap.DO_MAC_DINH.exists() and nhap.NHAT_KY_MAC_DINH.exists()
                                and nhap.BAN_VA_MAC_DINH.exists()), reason="thiếu file dữ liệu thật")


@pytest.fixture(scope="module")
def db_that():
    conn = kho.connect()
    kho.init_db(conn)
    nhap.nhap_tat_ca(conn)
    return conn


@THAT
def test_that_dem_450_370_53(db_that):
    n = lambda sql: db_that.execute(sql).fetchone()[0]
    assert n("SELECT COUNT(*) FROM mau WHERE bo = 'train'") == 450
    assert n("SELECT COUNT(*) FROM mau WHERE bo = 'do'") == 370
    assert n("SELECT COUNT(*) FROM lich_su_nhan") == 53
    assert {r[0]: r[1] for r in db_that.execute("SELECT nhom_xu_ly, COUNT(*) FROM lich_su_nhan GROUP BY 1")} == {
        "ap_dung_dung": 40, "ap_co_chinh": 11, "khong_ap": 2}                        # đúng như nhật ký ghi: 40 / 11 / 2
    assert {r[0] for r in db_that.execute("SELECT ma FROM mau m JOIN lich_su_nhan l ON l.mau_id = m.id WHERE l.nhom_xu_ly = 'khong_ap'")} == {"t142", "t220"}


@THAT
def test_that_xuat_nguoc_khop_tung_mau(db_that):
    assert nhap.xuat_train(db_that) == tap_train.doc_train()
    assert nhap.xuat_do(db_that) == bo_cau_hoi.doc_tho(bo_cau_hoi.MAC_DINH)["cau_hoi"]
    assert nhap.kiem_tra_toan_ven(db_that) == []


@THAT
def test_that_tang_tin_cay_hien_tai_chua_co_vang(db_that):
    """Dữ liệu hiện tại: toàn bộ nhãn do Claude soạn, chỉ tác giả duyệt. Test này khóa sự thật đó để số liệu báo cáo không bị thổi phồng."""
    t = {(r["bo"], r["tang"]): r["n"] for r in db_that.execute("SELECT bo, tang, COUNT(*) n FROM v_tin_cay GROUP BY 1, 2")}
    assert t == {("train", "bac"): 450, ("do", "bac"): 170, ("do", "nhap"): 200}
    assert db_that.execute("SELECT COUNT(*) FROM mau WHERE nguon <> 'claude'").fetchone()[0] == 0
