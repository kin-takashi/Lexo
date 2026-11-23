"""Nhập tập huấn luyện, bộ đo, nhật ký sửa nhãn và bộ bản án thật vào db/du_lieu.sqlite.

Nguồn chính vẫn là file JSON (train/tinh_huong.json, eval/bo_cau_hoi.json); DB là bản nhập kèm sha256 của file nguồn.
Nhập lại cùng file: bỏ qua, không nhân đôi. File nguồn đã đổi: báo lỗi, bắt dùng --reset (DB cũ được đổi tên, không mất).

Điều được ghi nhận ở đây và KHÔNG bịa thêm:
  * Mọi mẫu có trang_thai = da_duyet được ghi một dòng duyet {Kintakashi, tac_gia, dong_y, suy_ra = 1}: file nguồn chỉ có
    trường trang_thai, không có bản ghi ai duyệt lúc nào. Ngày duyệt lấy từ chính ghi_chu / mo_ta_tap của file (xem NGAY_DUYET);
    tập nào file không nêu ngày thì để trống.
  * Nhãn «trước» của một lần sửa chỉ có khi nhật ký ghi rõ «nhãn `A` → `B`». Không dựng lại nhãn cũ từ suy đoán.
  * Bộ bản án (bo = 'ban_an', từ inbox/anle_hf/ban_an_hinh_su.json): mỗi mẫu một dòng duyet {tòa án ra bản án, toa_an, dong_y,
    suy_ra = 1}. Đó là Điều TÒA ÁN đã áp dụng, nhưng do src/ban_an/tach.py ĐỌC TỰ ĐỘNG từ văn bản, chưa có người đối chiếu
    từng mẫu; ghi_chu của dòng duyet nói rõ điều này. trang_thai = 'nhap' vì file nguồn không có trạng thái duyệt của người.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

from src.index import bo_cau_hoi, tap_train

ROOT = Path(__file__).resolve().parents[2]
TRAIN_MAC_DINH = tap_train.MAC_DINH
DO_MAC_DINH = bo_cau_hoi.MAC_DINH
NHAT_KY_MAC_DINH = ROOT / "train" / "nhat_ky_sua_nhan.md"
BAN_VA_MAC_DINH = ROOT / "train" / "sua_nhan_train.md"
BAN_AN_MAC_DINH = ROOT / "inbox" / "anle_hf" / "ban_an_hinh_su.json"

NGUOI_DUYET = "Kintakashi"          # train/tinh_huong.json: «da_duyet nghĩa là Kintakashi đã duyệt nhãn»
NGUOI_DE_XUAT_BAN_VA = "Claude"      # sua_nhan_train.md do Claude soạn («mình chưa đối chiếu từng chữ với văn bản BLHS 2015»)
VAN_BAN_MAC_DINH = "100/2015/QH13"
# Ngày duyệt do chính file nguồn nêu: ghi_chu của tinh_huong.json (2026-10-14); mo_ta_tap của bo_cau_hoi.json:
# «phu … người dùng đã duyệt nhãn 2026-10-14», «kiem_tra … người dùng xác nhận ổn (2026-10-07)».
NGAY_DUYET = {("train", "train"): "2026-10-14", ("do", "phu"): "2026-10-14", ("do", "kiem_tra"): "2026-10-07"}


class NhapError(ValueError):
    pass


def chuan_van(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).lower().split())


def hash_van(s: str) -> str:
    return hashlib.sha256(chuan_van(s).encode("utf-8")).hexdigest()


def sha256_file(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _ten_file(p: Path) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _ghi_log(conn: sqlite3.Connection, loai: str, duong_dan: Path, so_ban_ghi: int, ghi_chu: str | None = None) -> int | None:
    """Ghi log_nhap. Trả None nếu đúng file này (cùng sha256) đã nhập; báo lỗi nếu cùng loại nhưng file đã đổi."""
    sha = sha256_file(duong_dan)
    cu = conn.execute("SELECT sha256 FROM log_nhap WHERE loai = ?", (loai,)).fetchall()
    if any(r["sha256"] == sha for r in cu):
        return None
    if cu:
        raise NhapError(f"nguồn «{loai}» đã đổi so với lần nhập trước ({_ten_file(duong_dan)}). "
                        "Nhập lại từ đầu bằng --reset (DB cũ được đổi tên thành bản sao lưu).")
    cur = conn.execute("INSERT INTO log_nhap (loai, duong_dan, sha256, so_ban_ghi, ghi_chu_file) VALUES (?, ?, ?, ?, ?)",
                       (loai, _ten_file(duong_dan), sha, so_ban_ghi, ghi_chu))
    return cur.lastrowid


def _ghi_duyet_tac_gia(conn: sqlite3.Connection, mau_id: int, bo: str, tap: str) -> None:
    conn.execute(
        "INSERT INTO duyet (mau_id, nguoi, vai_tro, ket_qua, ngay, suy_ra, ghi_chu) VALUES (?, ?, 'tac_gia', 'dong_y', ?, 1, ?)",
        (mau_id, NGUOI_DUYET, NGAY_DUYET.get((bo, tap)), "suy ra từ trang_thai = da_duyet của file nguồn; chưa có bản ghi duyệt riêng"))


def nhap_train(conn: sqlite3.Connection, duong_dan: str | Path = TRAIN_MAC_DINH, cau_do: list[str] | None = None) -> int:
    """Nhập tập huấn luyện. cau_do: các câu của bộ đo để dò rò rỉ (không truyền thì bỏ bước dò). Trả số mẫu mới nhập."""
    p = Path(duong_dan)
    d = tap_train.doc_tho(p)
    mau = d["mau"]
    loi = tap_train.kiem_tra_hop_le(mau, cau_do)
    if loi:
        raise NhapError(f"{p.name} không hợp lệ ({len(loi)} lỗi), ví dụ: {loi[0]}")
    log_id = _ghi_log(conn, "train", p, len(mau), d.get("ghi_chu"))
    if log_id is None:
        return 0
    for x in mau:
        mid = conn.execute(
            "INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) VALUES ('train', ?, 'train', ?, ?, ?, ?, ?, ?)",
            (x["id"], x["tinh_huong"], hash_van(x["tinh_huong"]), x["loai"], x["nguon"], x["trang_thai"], log_id)).lastrowid
        for i, h in enumerate(x["hanh_vi"], 1):
            hid = conn.execute("INSERT INTO hanh_vi (mau_id, thu_tu, mo_ta) VALUES (?, ?, ?)", (mid, i, h["mo_ta"])).lastrowid
            for j, dieu in enumerate(h["dieu"], 1):
                conn.execute("INSERT INTO nhan_dieu (mau_id, hanh_vi_id, nhom, thu_tu, van_ban_so_hieu, dieu) VALUES (?, ?, ?, ?, ?, ?)",
                             (mid, hid, i, j, VAN_BAN_MAC_DINH, dieu))
        if x["trang_thai"] == "da_duyet":
            _ghi_duyet_tac_gia(conn, mid, "train", "train")
    return len(mau)


def nhap_do(conn: sqlite3.Connection, duong_dan: str | Path = DO_MAC_DINH) -> int:
    """Nhập bộ đo (mọi tập, cả loại don và nhieu_dieu). Trả số câu mới nhập."""
    p = Path(duong_dan)
    d = bo_cau_hoi.doc_tho(p)
    cau = d["cau_hoi"]
    loi = bo_cau_hoi.kiem_tra_hop_le(cau)
    if loi:
        raise NhapError(f"{p.name} không hợp lệ ({len(loi)} lỗi), ví dụ: {loi[0]}")
    log_id = _ghi_log(conn, "do", p, len(cau), d.get("ghi_chu"))
    if log_id is None:
        return 0
    for x in cau:
        mid = conn.execute(
            "INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) VALUES ('do', ?, ?, ?, ?, ?, ?, ?, ?)",
            (x["id"], x["tap"], x["cau_hoi"], hash_van(x["cau_hoi"]), x["loai"], x["nguon"], x["trang_thai"], log_id)).lastrowid
        for j, dieu in enumerate(x["dieu"], 1):
            nhom, thu_tu = (1, j) if x["loai"] == "don" else (j, 1)   # don: mọi Điều chấp nhận cùng một nhóm; nhieu_dieu: mỗi Điều một nhóm (tìm đủ)
            conn.execute("INSERT INTO nhan_dieu (mau_id, hanh_vi_id, nhom, thu_tu, van_ban_so_hieu, dieu) VALUES (?, NULL, ?, ?, ?, ?)",
                         (mid, nhom, thu_tu, VAN_BAN_MAC_DINH, dieu))
        if x["trang_thai"] == "da_duyet":
            _ghi_duyet_tac_gia(conn, mid, "do", x["tap"])
    return len(cau)


# ---------------------------------------------------------------- bộ bản án thật (dataset tmquan/anle-toaan-gov-vn)

_NGUOI_TOA_AN_KHONG_RO = "Tòa án (không đọc được tên)"


def _ngay_iso(s: str | None) -> str | None:
    """Ngày ISO hợp lệ thì giữ; bộ tách đọc sai (vd '2025-13-40') thì để trống, không đoán."""
    try:
        return date.fromisoformat(s).isoformat() if s and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None
    except ValueError:
        return None


def kiem_tra_ban_an(mau: list[dict]) -> list[str]:
    """Lỗi của file bản án trước khi nhập. Rỗng = ổn."""
    loi: list[str] = []
    da_thay: set[str] = set()
    tap_nhom: dict[str, set[str]] = {}
    for b in mau:
        ma = b.get("ma") or "?"
        if ma in da_thay:
            loi.append(f"{ma}: trùng mã")
        da_thay.add(ma)
        if b.get("tap") not in ("train", "test"):
            loi.append(f"{ma}: tap phải là train / test (đang {b.get('tap')!r})")
        if not b.get("dieu") or len(set(b["dieu"])) != len(b["dieu"]):
            loi.append(f"{ma}: danh sách Điều rỗng hoặc lặp")
        if not (b.get("dau_vao") or "").strip():
            loi.append(f"{ma}: đầu vào rỗng")
        if b.get("lo_nhan_con_lai"):
            loi.append(f"{ma}: đầu vào còn lộ nhãn {b['lo_nhan_con_lai']} (che lại bằng scripts/xu_ly_anle_hf.py trước khi nhập)")
        if not b.get("nhom_vu"):
            loi.append(f"{ma}: thiếu nhom_vu")
        else:
            tap_nhom.setdefault(b["nhom_vu"], set()).add(b.get("tap"))
    loi += [f"nhóm vụ {g} nằm ở cả hai tập {sorted(t)}" for g, t in tap_nhom.items() if len(t) > 1]
    return loi


def nhap_ban_an(conn: sqlite3.Connection, duong_dan: str | Path = BAN_AN_MAC_DINH) -> int:
    """Nhập bộ bản án (bo = 'ban_an'). Trả số mẫu mới nhập."""
    p = Path(duong_dan)
    d = json.loads(p.read_text(encoding="utf-8"))
    mau = d["mau"]
    loi = kiem_tra_ban_an(mau)
    if loi:
        raise NhapError(f"{p.name} không hợp lệ ({len(loi)} lỗi), ví dụ: {loi[0]}")
    g = d.get("nguon") or {}
    log_id = _ghi_log(conn, "ban_an_hf", p, len(mau), f"{g.get('dataset')} / {g.get('file')} sha256 {g.get('sha256')}")
    if log_id is None:
        return 0
    for b in mau:
        mid = conn.execute(
            "INSERT INTO mau (bo, ma, tap, van_ban, hash_van_ban, loai, nguon, trang_thai, log_nhap_id) "
            "VALUES ('ban_an', ?, ?, ?, ?, ?, 'ban_an', 'nhap', ?)",
            (b["ma"], b["tap"], b["dau_vao"], hash_van(b["dau_vao"]), "don" if len(b["dieu"]) == 1 else "nhieu_dieu", log_id)).lastrowid
        for j, dieu in enumerate(b["dieu"], 1):           # mỗi Điều tòa án áp dụng là một việc phải tìm đủ
            conn.execute("INSERT INTO nhan_dieu (mau_id, hanh_vi_id, nhom, thu_tu, van_ban_so_hieu, dieu) VALUES (?, NULL, ?, 1, ?, ?)",
                         (mid, j, VAN_BAN_MAC_DINH, dieu))
        conn.execute(
            "INSERT INTO ban_an_meta (mau_id, ma_goc, so_ban_an, cap, cap_dataset, ngay_ban_an, toa_an, nguon_nhan, so_tham_tham_chieu, "
            "nhom_vu, toi_danh, da_che, ten_toi_trong_loi_ke) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, b["ma"], b.get("so_ban_an"), b.get("cap") or "khong_ro", b.get("cap_dataset"), _ngay_iso(b.get("ngay")), b.get("toa_an"),
             b["nguon_nhan"], b.get("so_tham_tham_chieu"), b["nhom_vu"], json.dumps(b.get("toi_danh") or [], ensure_ascii=False),
             json.dumps(b.get("da_che") or {}, ensure_ascii=False), int(b.get("ten_toi_trong_loi_ke") or 0)))
        conn.execute(
            "INSERT INTO duyet (mau_id, nguoi, vai_tro, ket_qua, ngay, suy_ra, ghi_chu) VALUES (?, ?, 'toa_an', 'dong_y', ?, 1, ?)",
            (mid, b.get("toa_an") or _NGUOI_TOA_AN_KHONG_RO, _ngay_iso(b.get("ngay")),
             f"Điều do tòa án áp dụng, đọc tự động bằng src/ban_an/tach.py (nguồn nhãn: {b['nguon_nhan']}); chưa có người đối chiếu"))
    return len(mau)


def xuat_ban_an(conn: sqlite3.Connection) -> list[dict]:
    """Xuất ngược bộ bản án (các trường để đối chiếu với file nguồn), theo thứ tự nhập."""
    ra = []
    for m in conn.execute("SELECT m.*, b.nguon_nhan, b.nhom_vu FROM mau m JOIN ban_an_meta b ON b.mau_id = m.id WHERE m.bo = 'ban_an' ORDER BY m.id"):
        dieu = [r["dieu"] for r in conn.execute("SELECT dieu FROM nhan_dieu WHERE mau_id = ? ORDER BY nhom", (m["id"],))]
        ra.append({"ma": m["ma"], "tap": m["tap"], "dau_vao": m["van_ban"], "dieu": dieu, "nguon_nhan": m["nguon_nhan"], "nhom_vu": m["nhom_vu"]})
    return ra


def doc_ban_an_de_doi_chieu(duong_dan: str | Path = BAN_AN_MAC_DINH) -> list[dict]:
    """Cùng dạng với xuat_ban_an(), đọc từ file nguồn."""
    mau = json.loads(Path(duong_dan).read_text(encoding="utf-8"))["mau"]
    return [{k: b[k] for k in ("ma", "tap", "dau_vao", "dieu", "nguon_nhan", "nhom_vu")} for b in mau]


# ---------------------------------------------------------------- nhật ký sửa nhãn

_HANG = re.compile(r"^\|\s*(t\d{3})\s*\|")
_NHAN_DOI = re.compile(r"nhãn\s+`([^`]+)`\s*→\s*`([^`]+)`")


def _cac_o(dong: str) -> list[str]:
    return [c.strip() for c in dong.strip().strip("|").split("|")]


def doc_nhat_ky(duong_dan: str | Path) -> tuple[dict[str, dict], str]:
    """Đọc train/nhat_ky_sua_nhan.md → ({mã mẫu: thông tin}, ngày áp bản vá). Mục 1 = khác bản vá, mục 2 = áp đúng bản vá."""
    van = Path(duong_dan).read_text(encoding="utf-8")
    dong = van.splitlines()
    m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", dong[0]) if dong else None
    if not m:
        raise NhapError(f"{Path(duong_dan).name}: dòng đầu phải có ngày áp bản vá dạng (YYYY-MM-DD)")
    ngay, muc, ra = m.group(1), None, {}
    for d in dong:
        h = re.match(r"^##\s+(\d)\.", d)
        if d.startswith("## "):
            muc = int(h.group(1)) if h else None
            continue
        r = _HANG.match(d)
        if not r or muc not in (1, 2):
            continue
        o = _cac_o(d)
        ma = r.group(1)
        if ma in ra:
            raise NhapError(f"{Path(duong_dan).name}: mục {ma} xuất hiện hai lần")
        if muc == 1:
            if len(o) != 4:
                raise NhapError(f"{Path(duong_dan).name}: hàng {ma} ở mục 1 phải có 4 cột (Mục | Bản vá | Đã làm | Căn cứ), đang {len(o)}")
            ra[ma] = {"nhom_xu_ly": "khong_ap" if re.match(r"Không\b", o[2]) else "ap_co_chinh",
                      "ban_va": o[1], "da_lam": o[2], "can_cu": o[3], "nhan_truoc": None, "nhan_sau": None}
        else:
            if len(o) != 2:
                raise NhapError(f"{Path(duong_dan).name}: hàng {ma} ở mục 2 phải có 2 cột (Mục | Thay đổi), đang {len(o)}")
            n = _NHAN_DOI.search(o[1])
            ra[ma] = {"nhom_xu_ly": "ap_dung_dung", "ban_va": None, "da_lam": o[1], "can_cu": None,
                      "nhan_truoc": n.group(1) if n else None, "nhan_sau": n.group(2) if n else None}
    return ra, ngay


def doc_ban_va(duong_dan: str | Path) -> dict[str, dict]:
    """Đọc train/sua_nhan_train.md → {mã mẫu: {nhom_ban_va A-D, hanh_dong, muc_chac, ban_va}}."""
    ten = Path(duong_dan).name
    nhom, ra = None, {}
    for d in Path(duong_dan).read_text(encoding="utf-8").splitlines():
        if d.startswith("## "):
            h = re.match(r"^##\s+([A-D])\.", d)
            nhom = h.group(1) if h else None
            continue
        r = _HANG.match(d)
        if not r or nhom is None:
            continue
        o, ma = _cac_o(d), r.group(1)
        so_cot = {"A": 6, "B": 3, "C": 4, "D": 4}[nhom]
        if len(o) != so_cot:
            raise NhapError(f"{ten}: hàng {ma} ở nhóm {nhom} phải có {so_cot} cột, đang {len(o)}")
        if ma in ra:
            raise NhapError(f"{ten}: mục {ma} xuất hiện hai lần")
        mc = re.match(r"(Cao|TB|KC)\b", o[-1])
        if not mc:
            raise NhapError(f"{ten}: hàng {ma} không có mức chắc (Cao / TB / KC) ở cột cuối: {o[-1]!r}")
        if nhom == "A":
            hanh_dong, ban_va = o[1], f"Hiện tại: {o[2]} → Sửa thành: {o[3]}. Lý do: {o[4]}"
        elif nhom == "B":
            hanh_dong, ban_va = "SỬA ĐỀ", o[1]
        else:
            hanh_dong, ban_va = o[1], o[2]
        ra[ma] = {"nhom_ban_va": nhom, "hanh_dong": hanh_dong, "muc_chac": mc.group(1), "ban_va": ban_va}
    return ra


def nhap_sua_nhan(conn: sqlite3.Connection, nhat_ky: str | Path = NHAT_KY_MAC_DINH, ban_va: str | Path = BAN_VA_MAC_DINH) -> int:
    """Nhập lịch sử sửa nhãn: ghép nhật ký (đã làm gì) với bản vá gốc (đề xuất gì, mức chắc). Trả số mục mới nhập."""
    nk, ngay = doc_nhat_ky(nhat_ky)
    bv = doc_ban_va(ban_va)
    loi = []
    if set(nk) != set(bv):
        loi.append(f"nhật ký có {len(nk)} mục, bản vá có {len(bv)} mục; chỉ có ở nhật ký: {sorted(set(nk) - set(bv))}; chỉ có ở bản vá: {sorted(set(bv) - set(nk))}")
    chua_co = [ma for ma in nk if conn.execute("SELECT 1 FROM mau WHERE bo = 'train' AND ma = ?", (ma,)).fetchone() is None]
    if chua_co:
        loi.append(f"mục không có trong tập huấn luyện đã nhập (nhập tập huấn luyện trước): {sorted(chua_co)}")
    if loi:
        raise NhapError("; ".join(loi))
    id_nk = _ghi_log(conn, "nhat_ky_sua_nhan", Path(nhat_ky), len(nk))
    id_bv = _ghi_log(conn, "ban_va_sua_nhan", Path(ban_va), len(bv))
    if id_nk is None and id_bv is None:
        return 0
    if id_nk is None or id_bv is None:
        raise NhapError("chỉ một trong hai file (nhật ký, bản vá) là mới; nhập lại cả hai bằng --reset")
    for ma, a in nk.items():
        b = bv[ma]
        mid = conn.execute("SELECT id FROM mau WHERE bo = 'train' AND ma = ?", (ma,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO lich_su_nhan (mau_id, nhom_xu_ly, nhom_ban_va, hanh_dong, muc_chac, ban_va, da_lam, can_cu, nhan_truoc, nhan_sau, "
            "nguoi_de_xuat, nguoi_quyet, ngay, nguon_ban_va, log_nhap_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, a["nhom_xu_ly"], b["nhom_ban_va"], b["hanh_dong"], b["muc_chac"], b["ban_va"], a["da_lam"], a["can_cu"],
             a["nhan_truoc"], a["nhan_sau"], NGUOI_DE_XUAT_BAN_VA, NGUOI_DUYET, ngay, Path(ban_va).name, id_nk))
    return len(nk)


def nhap_tat_ca(conn: sqlite3.Connection, train: str | Path = TRAIN_MAC_DINH, do: str | Path = DO_MAC_DINH,
                nhat_ky: str | Path | None = NHAT_KY_MAC_DINH, ban_va: str | Path | None = BAN_VA_MAC_DINH,
                ban_an: str | Path | None = None) -> dict[str, int]:
    """Nhập mọi nguồn trong MỘT giao dịch: lỗi ở đâu cũng hoàn tác hết. Dò rò rỉ train → bộ đo trước khi nhập.
    ban_an: file inbox/anle_hf/ban_an_hinh_su.json (None = không nhập bộ bản án; kết quả khi đó không có khóa 'ban_an')."""
    cau_do = [x["cau_hoi"] for x in bo_cau_hoi.doc_bo(do, None, None)]
    try:
        with conn:
            kq = {"train": nhap_train(conn, train, cau_do), "do": nhap_do(conn, do), "sua_nhan": 0}
            if nhat_ky is not None and ban_va is not None:
                kq["sua_nhan"] = nhap_sua_nhan(conn, nhat_ky, ban_va)
            if ban_an is not None:
                kq["ban_an"] = nhap_ban_an(conn, ban_an)
    except sqlite3.IntegrityError as e:
        raise NhapError(f"vi phạm ràng buộc của DB: {e}") from e
    return kq


# ---------------------------------------------------------------- xuất lại (để đối chiếu không mất mẫu)

def xuat_train(conn: sqlite3.Connection) -> list[dict]:
    ra = []
    for m in conn.execute("SELECT * FROM mau WHERE bo = 'train' ORDER BY id"):
        hv = []
        for h in conn.execute("SELECT id, mo_ta FROM hanh_vi WHERE mau_id = ? ORDER BY thu_tu", (m["id"],)):
            dieu = [r["dieu"] for r in conn.execute("SELECT dieu FROM nhan_dieu WHERE hanh_vi_id = ? ORDER BY thu_tu", (h["id"],))]
            hv.append({"mo_ta": h["mo_ta"], "dieu": dieu})
        ra.append({"id": m["ma"], "tinh_huong": m["van_ban"], "hanh_vi": hv, "loai": m["loai"], "nguon": m["nguon"], "trang_thai": m["trang_thai"]})
    return ra


def xuat_do(conn: sqlite3.Connection) -> list[dict]:
    ra = []
    for m in conn.execute("SELECT * FROM mau WHERE bo = 'do' ORDER BY id"):
        dieu = [r["dieu"] for r in conn.execute("SELECT dieu FROM nhan_dieu WHERE mau_id = ? ORDER BY nhom, thu_tu", (m["id"],))]
        ra.append({"id": m["ma"], "cau_hoi": m["van_ban"], "dieu": dieu, "loai": m["loai"], "tap": m["tap"], "nguon": m["nguon"],
                   "trang_thai": m["trang_thai"]})
    return ra


def kiem_tra_toan_ven(conn: sqlite3.Connection) -> list[str]:
    """Kiểm tra bất biến mà CHECK của SQL không diễn tả được. Rỗng = ổn."""
    loi = []
    for r in conn.execute("SELECT m.bo, m.ma FROM mau m WHERE NOT EXISTS (SELECT 1 FROM nhan_dieu n WHERE n.mau_id = m.id)"):
        loi.append(f"{r['bo']}/{r['ma']}: không có nhãn Điều nào")
    for r in conn.execute("SELECT m.ma FROM mau m WHERE m.bo = 'train' AND NOT EXISTS (SELECT 1 FROM hanh_vi h WHERE h.mau_id = m.id)"):
        loi.append(f"train/{r['ma']}: không có hành vi nào")
    for r in conn.execute("SELECT m.ma, COUNT(h.id) AS n FROM mau m JOIN hanh_vi h ON h.mau_id = m.id WHERE m.bo = 'train' AND m.loai = 'don' GROUP BY m.id HAVING n <> 1"):
        loi.append(f"train/{r['ma']}: loai don phải có đúng 1 hành vi (đang {r['n']})")
    for r in conn.execute("SELECT m.ma, m.tap, COUNT(DISTINCT n.nhom) AS k FROM mau m JOIN nhan_dieu n ON n.mau_id = m.id WHERE m.bo = 'do' AND m.loai = 'don' GROUP BY m.id HAVING k <> 1"):
        loi.append(f"do/{r['ma']}: loai don phải có đúng 1 nhóm đáp án (đang {r['k']})")
    for r in conn.execute("SELECT ma_train, ma_do FROM v_trung_van_ban"):
        loi.append(f"train/{r['ma_train']} trùng nguyên văn do/{r['ma_do']}")
    for r in conn.execute("SELECT ma_ban_an, tap_ban_an, bo_khac, ma_khac, tap_khac FROM v_trung_ban_an"):
        loi.append(f"ban_an/{r['ma_ban_an']} ({r['tap_ban_an']}) trùng nguyên văn {r['bo_khac']}/{r['ma_khac']} ({r['tap_khac']})")
    for r in conn.execute("SELECT m.ma FROM mau m WHERE m.bo = 'ban_an' AND NOT EXISTS (SELECT 1 FROM ban_an_meta b WHERE b.mau_id = m.id)"):
        loi.append(f"ban_an/{r['ma']}: thiếu ban_an_meta")
    for r in conn.execute("SELECT m.ma, m.loai, COUNT(n.id) AS k FROM mau m JOIN nhan_dieu n ON n.mau_id = m.id WHERE m.bo = 'ban_an' "
                          "GROUP BY m.id HAVING (m.loai = 'don') <> (k = 1)"):
        loi.append(f"ban_an/{r['ma']}: loai {r['loai']} nhưng có {r['k']} Điều")
    for r in conn.execute("SELECT b.nhom_vu FROM ban_an_meta b JOIN mau m ON m.id = b.mau_id GROUP BY b.nhom_vu HAVING COUNT(DISTINCT m.tap) > 1"):
        loi.append(f"ban_an: nhóm vụ {r['nhom_vu']} nằm ở cả train và test")
    return loi


def thong_ke(conn: sqlite3.Connection) -> dict:
    """Số liệu tóm tắt để in: số mẫu theo bộ/tập, tầng tin cậy theo bộ, kiểu xử lý nhãn."""
    mau = {(r["bo"], r["tap"]): r["n"] for r in conn.execute("SELECT bo, tap, COUNT(*) AS n FROM mau GROUP BY bo, tap ORDER BY bo, tap")}
    tang = {(r["bo"], r["tang"]): r["n"] for r in conn.execute("SELECT bo, tang, COUNT(*) AS n FROM v_tin_cay GROUP BY bo, tang ORDER BY bo, tang")}
    nguon = {(r["bo"], r["nguon"]): r["n"] for r in conn.execute("SELECT bo, nguon, COUNT(*) AS n FROM mau GROUP BY bo, nguon")}
    sua = {r["nhom_xu_ly"]: r["n"] for r in conn.execute("SELECT nhom_xu_ly, COUNT(*) AS n FROM lich_su_nhan GROUP BY nhom_xu_ly")}
    muc = {r["muc_chac"]: r["n"] for r in conn.execute("SELECT muc_chac, COUNT(*) AS n FROM lich_su_nhan GROUP BY muc_chac")}
    return {"mau": mau, "tang": tang, "nguon": nguon, "sua_nhan": sua, "muc_chac": muc}
