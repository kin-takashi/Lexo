"""Hiệu đính kỹ thuật: sửa chữ có bằng chứng lên văn bản đã dựng, do NGƯỜI duyệt từng quy tắc.

Vì sao có lớp này: văn bản hệ thống dựng = luật gốc + các luật sửa đổi, đúng NHƯ BAN HÀNH. Đối chiếu với VĂN BẢN HỢP NHẤT chính
thức (Văn phòng Quốc hội) cho thấy một số chỗ khác: lỗi gõ nằm sẵn trong bản đăng Công báo ("quyền dụng đất"), lỗi trong file
Word luật sửa đổi ("phạt liền", "d, d") hoặc con số chép sai ("dưới 100.000.000" thay vì "dưới 500.000.000"). Mỗi chỗ được lập thành một
quy tắc (khoá nút, từ cũ -> từ mới, bằng chứng) ở trạng thái cho_duyet; chỉ quy tắc da_duyet mới được áp.

Quy ước:
  * quy tắc thay ĐÚNG MỘT chỗ xuất hiện của tu_cu trong trường của từng phiên bản; 0 chỗ = phiên bản đó không có lỗi (bỏ qua),
    nhiều chỗ = mơ hồ (bỏ qua và báo); không phiên bản nào áp được = quy tắc "cũ" (báo, có thể do luật sửa đổi mới đã thay đoạn đó);
  * bản như luật ban hành được giữ ở phien_ban_noi_dung.*_goc; rebuild() khôi phục rồi áp lại, nên bỏ/đổi quy tắc là chạy lại rebuild;
  * không bao giờ tự duyệt: duyet() chỉ chạy khi người dùng ra lệnh và nêu tên.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from src.validate.vbhn import key_of

DA_DUYET = ("da_duyet",)
LOAI = ("loi_go", "nhieu_chu", "sai_so_lieu")


class HieuDinhError(Exception):
    pass


@dataclass
class KetQuaQuyTac:
    id: int
    khoa: str
    truong: str
    tu_cu: str
    thanh_moi: str
    n_phien_ban: int = 0          # số phiên bản đã áp
    n_mo_ho: int = 0              # số phiên bản có tu_cu nhiều hơn một chỗ (bỏ qua)
    co_nut: bool = True           # có nút mang khoá này trong văn bản không

    @property
    def cu(self) -> bool:
        return self.n_phien_ban == 0


@dataclass
class BaoCaoHieuDinh:
    ket_qua: list[KetQuaQuyTac] = field(default_factory=list)

    @property
    def n_ap(self) -> int:
        return sum(1 for r in self.ket_qua if r.n_phien_ban)

    def khong_ap_duoc(self) -> list[KetQuaQuyTac]:
        return [r for r in self.ket_qua if r.cu]


def khoa_nut(conn: sqlite3.Connection, van_ban_id: int) -> dict[str, list[int]]:
    """khoá nút (dạng 'dieu 229/khoan 1/diem b') -> các don_vi_id mang khoá đó (nhiều nút khi một Điều bị bãi bỏ rồi lập lại)."""
    rows = conn.execute(
        """SELECT d.id, d.cha_id, d.loai,
                  (SELECT p.ky_hieu FROM phien_ban_noi_dung p WHERE p.don_vi_id = d.id ORDER BY p.hieu_luc_tu DESC, p.id DESC LIMIT 1) AS ky
           FROM don_vi_luat d WHERE d.van_ban_id = ?""", (van_ban_id,)).fetchall()
    by_id = {r["id"]: r for r in rows}
    keys: dict[int, str] = {}

    def key(i: int) -> str:
        if i not in keys:
            r = by_id[i]
            parent = by_id.get(r["cha_id"]) if r["cha_id"] else None
            keys[i] = key_of(r["loai"], r["ky"], key(parent["id"]) if parent is not None else None)
        return keys[i]

    out: dict[str, list[int]] = {}
    for i in by_id:
        out.setdefault(key(i), []).append(i)
    return out


def luu_de_xuat(conn: sqlite3.Connection, van_ban_id: int, de_xuat: list[dict]) -> tuple[int, int]:
    """Thêm các đề xuất {khoa, truong, tu_cu, thanh_moi, loai, bang_chung}; trạng thái cho_duyet.
    Đề xuất đã có (cùng khoa/truong/tu_cu/thanh_moi) giữ nguyên, kể cả quyết định đã ghi. Trả về (mới, đã có). Không commit."""
    moi = co = 0
    for d in de_xuat:
        if d["loai"] not in LOAI:
            raise HieuDinhError(f"loai không hợp lệ: {d['loai']!r}")
        cur = conn.execute(
            """INSERT OR IGNORE INTO hieu_dinh (van_ban_id, khoa, truong, tu_cu, thanh_moi, loai, bang_chung_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (van_ban_id, d["khoa"], d["truong"], d["tu_cu"], d["thanh_moi"], d["loai"],
             json.dumps(d.get("bang_chung") or {}, ensure_ascii=False, sort_keys=True)))
        if cur.rowcount:
            moi += 1
        else:
            co += 1
    return moi, co


def duyet(conn: sqlite3.Connection, van_ban_id: int, *, nguoi: str, ids: list[int] | None = None, loai: list[str] | None = None,
          tu_choi: bool = False, ghi_chu: str | None = None) -> int:
    """Duyệt (hoặc từ chối) các quy tắc cho_duyet; mặc định tất cả, hoặc theo danh sách id / theo loại. Trả về số quy tắc đã đổi trạng thái."""
    if not nguoi or not nguoi.strip():
        raise HieuDinhError("Phải nêu tên người duyệt (--nguoi).")
    where, args = ["van_ban_id = ?", "trang_thai_duyet = 'cho_duyet'"], [van_ban_id]
    if ids:
        where.append(f"id IN ({','.join('?' * len(ids))})")
        args += list(ids)
    if loai:
        where.append(f"loai IN ({','.join('?' * len(loai))})")
        args += list(loai)
    with conn:
        cur = conn.execute(
            f"UPDATE hieu_dinh SET trang_thai_duyet = ?, nguoi_duyet = ?, ngay_duyet = ?, ghi_chu_duyet = ? WHERE {' AND '.join(where)}",
            ("tu_choi" if tu_choi else "da_duyet", nguoi.strip(), date.today().isoformat(), ghi_chu, *args))
    return cur.rowcount


def khoi_phuc(conn: sqlite3.Connection, van_ban_id: int) -> int:
    """Trả mọi phiên bản về văn bản NHƯ BAN HÀNH (xoá hiệu đính đã áp). Không commit. Trả về số phiên bản được khôi phục."""
    cur = conn.execute(
        """UPDATE phien_ban_noi_dung
              SET noi_dung = COALESCE(noi_dung_goc, noi_dung), tieu_de = COALESCE(tieu_de_goc, tieu_de),
                  noi_dung_goc = NULL, tieu_de_goc = NULL, hieu_dinh_json = NULL
            WHERE don_vi_id IN (SELECT id FROM don_vi_luat WHERE van_ban_id = ?)
              AND (noi_dung_goc IS NOT NULL OR tieu_de_goc IS NOT NULL OR hieu_dinh_json IS NOT NULL)""", (van_ban_id,))
    return cur.rowcount


def ap_dung(conn: sqlite3.Connection, van_ban_id: int, trang_thai: tuple[str, ...] = DA_DUYET) -> BaoCaoHieuDinh:
    """Áp các quy tắc có trạng thái thuộc `trang_thai` lên mọi phiên bản của nút tương ứng. Phải gọi sau khi dựng xong phiên bản
    và sau khoi_phuc(). Không commit."""
    rules = conn.execute(
        f"SELECT * FROM hieu_dinh WHERE van_ban_id = ? AND trang_thai_duyet IN ({','.join('?' * len(trang_thai))}) ORDER BY id",
        (van_ban_id, *trang_thai)).fetchall()
    bao = BaoCaoHieuDinh()
    if not rules:
        return bao
    nut = khoa_nut(conn, van_ban_id)
    for r in rules:
        kq = KetQuaQuyTac(r["id"], r["khoa"], r["truong"], r["tu_cu"], r["thanh_moi"])
        ids = nut.get(r["khoa"], [])
        kq.co_nut = bool(ids)
        goc_col = "noi_dung_goc" if r["truong"] == "noi_dung" else "tieu_de_goc"
        for did in ids:
            for pb in conn.execute("SELECT id, tieu_de, noi_dung, tieu_de_goc, noi_dung_goc, hieu_dinh_json FROM phien_ban_noi_dung WHERE don_vi_id = ?", (did,)).fetchall():
                cur = pb[r["truong"]]
                n = cur.count(r["tu_cu"]) if cur else 0
                if n == 0:
                    continue
                if n > 1:
                    kq.n_mo_ho += 1
                    continue
                da = json.loads(pb["hieu_dinh_json"]) if pb["hieu_dinh_json"] else []
                conn.execute(
                    f"UPDATE phien_ban_noi_dung SET {r['truong']} = ?, {goc_col} = COALESCE({goc_col}, ?), hieu_dinh_json = ? WHERE id = ?",
                    (cur.replace(r["tu_cu"], r["thanh_moi"], 1), cur, json.dumps(da + [r["id"]]), pb["id"]))
                kq.n_phien_ban += 1
        bao.ket_qua.append(kq)
    return bao


def dieu_ap_dung(conn: sqlite3.Connection, don_vi_id: int, hieu_luc_tu: str) -> list[sqlite3.Row]:
    """Các quy tắc đã áp vào phiên bản của nút bắt đầu hiệu lực từ `hieu_luc_tu` (để lookup hiển thị)."""
    r = conn.execute("SELECT hieu_dinh_json FROM phien_ban_noi_dung WHERE don_vi_id = ? AND hieu_luc_tu = ? AND hieu_dinh_json IS NOT NULL",
                     (don_vi_id, hieu_luc_tu)).fetchone()
    if r is None:
        return []
    ids = json.loads(r[0])
    return conn.execute(f"SELECT * FROM hieu_dinh WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id", ids).fetchall() if ids else []


# ---------------------------------------------------------------------------------------------------------------------
# Lưu/nạp quyết định ra file để sống sót qua init_db --reset (giống review.json của văn bản gốc)

_FIELDS = ("khoa", "truong", "tu_cu", "thanh_moi", "loai", "trang_thai_duyet", "nguoi_duyet", "ngay_duyet", "ghi_chu_duyet")


def xuat(conn: sqlite3.Connection, van_ban_id: int) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM hieu_dinh WHERE van_ban_id = ? ORDER BY id", (van_ban_id,)):
        d = {k: r[k] for k in _FIELDS}
        d["bang_chung"] = json.loads(r["bang_chung_json"])
        out.append(d)
    return out


def nap(conn: sqlite3.Connection, van_ban_id: int, rules: list[dict]) -> tuple[int, int]:
    """Nạp quy tắc từ file. Quy tắc chưa có thì thêm (kể cả quyết định đã duyệt); quy tắc đang cho_duyet trong CSDL mà file đã có
    quyết định thì lấy quyết định của file. Trả về (thêm, cập nhật). Không commit."""
    them = cap = 0
    for d in rules:
        row = conn.execute("SELECT id, trang_thai_duyet FROM hieu_dinh WHERE van_ban_id = ? AND khoa = ? AND truong = ? AND tu_cu = ? AND thanh_moi = ?",
                           (van_ban_id, d["khoa"], d["truong"], d["tu_cu"], d["thanh_moi"])).fetchone()
        bc = json.dumps(d.get("bang_chung") or {}, ensure_ascii=False, sort_keys=True)
        if row is None:
            conn.execute(
                """INSERT INTO hieu_dinh (van_ban_id, khoa, truong, tu_cu, thanh_moi, loai, bang_chung_json,
                       trang_thai_duyet, nguoi_duyet, ngay_duyet, ghi_chu_duyet) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (van_ban_id, d["khoa"], d["truong"], d["tu_cu"], d["thanh_moi"], d["loai"], bc, d.get("trang_thai_duyet", "cho_duyet"),
                 d.get("nguoi_duyet"), d.get("ngay_duyet"), d.get("ghi_chu_duyet")))
            them += 1
        elif row["trang_thai_duyet"] == "cho_duyet" and d.get("trang_thai_duyet", "cho_duyet") != "cho_duyet":
            conn.execute("UPDATE hieu_dinh SET trang_thai_duyet = ?, nguoi_duyet = ?, ngay_duyet = ?, ghi_chu_duyet = ? WHERE id = ?",
                         (d["trang_thai_duyet"], d.get("nguoi_duyet"), d.get("ngay_duyet"), d.get("ghi_chu_duyet"), row["id"]))
            cap += 1
    return them, cap
