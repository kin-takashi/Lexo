"""Duyệt lệnh sửa đổi theo LÔ (một luật sửa đổi) và báo cáo để người duyệt đọc.

Duyệt là hành vi của con người: hàm ở đây chỉ chạy khi người dùng ra lệnh rõ ràng (kèm tên người duyệt) và từ chối nếu
xem trước cho thấy còn lệnh không áp được. Mọi lệnh duyệt đều ghi nguoi_duyet, ngay_duyet, ghi_chu_duyet.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from src.apply.rebuild import LOI, preview


class ApproveError(Exception):
    pass


def _one(conn: sqlite3.Connection, q: str, *a) -> sqlite3.Row:
    r = conn.execute(q, a).fetchone()
    if r is None:
        raise ApproveError(f"Không tìm thấy: {a}")
    return r


def tong_quan(conn: sqlite3.Connection, van_ban_dich_id: int) -> list[sqlite3.Row]:
    """Số lệnh theo từng luật sửa đổi và trạng thái duyệt."""
    return conn.execute(
        """SELECT v.so_hieu, v.ngay_ban_hanh, v.ngay_hieu_luc,
                  SUM(l.trang_thai_duyet = 'cho_duyet') AS cho_duyet, SUM(l.trang_thai_duyet IN ('da_duyet', 'da_sua')) AS da_duyet,
                  SUM(l.trang_thai_duyet = 'tu_choi') AS tu_choi, COUNT(*) AS tong
           FROM lenh_sua_doi l JOIN van_ban v ON v.id = l.van_ban_nguon_id
           WHERE l.van_ban_dich_id = ? GROUP BY v.id ORDER BY v.ngay_hieu_luc, v.so_hieu""", (van_ban_dich_id,)).fetchall()


def duyet_theo_lo(conn: sqlite3.Connection, so_hieu_nguon: str, van_ban_dich_id: int, *, nguoi: str, ghi_chu: str | None = None) -> int:
    """Duyệt mọi lệnh 'cho_duyet' của một luật sửa đổi. Từ chối nếu xem trước (gồm cả các lệnh còn lại) có lệnh lỗi."""
    if not nguoi.strip():
        raise ApproveError("Phải nêu tên người duyệt (--nguoi).")
    src = _one(conn, "SELECT id FROM van_ban WHERE so_hieu = ?", so_hieu_nguon)["id"]
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM lenh_sua_doi WHERE van_ban_nguon_id = ? AND van_ban_dich_id = ? AND trang_thai_duyet = 'cho_duyet'",
        (src, van_ban_dich_id))]
    if not ids:
        raise ApproveError(f"{so_hieu_nguon} không còn lệnh nào chờ duyệt.")
    report, mem = preview(conn, van_ban_dich_id)
    mem.close()
    bad = [r for r in report.results if not r.ok and r.lenh_id in set(ids)]
    if bad:
        raise ApproveError(f"{len(bad)} lệnh không áp được, chưa duyệt. Đầu tiên: " + "; ".join(
            f"#{r.lenh_id} {r.vi_tri_nguon}: {r.problems[0].message}" for r in bad[:3]))
    with conn:
        conn.execute(
            f"UPDATE lenh_sua_doi SET trang_thai_duyet = 'da_duyet', nguoi_duyet = ?, ngay_duyet = ?, ghi_chu_duyet = ? "
            f"WHERE id IN ({','.join('?' * len(ids))})", (nguoi.strip(), date.today().isoformat(), ghi_chu, *ids))
    return len(ids)


def _cut(text: str | None, n: int = 400) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + " …"


def bao_cao_markdown(conn: sqlite3.Connection, so_hieu_nguon: str, van_ban_dich_id: int) -> str:
    """Bảng đọc-duyệt: từng lệnh (vị trí trong luật sửa đổi, thao tác, đích, nội dung mới) và kết quả áp thử."""
    src = _one(conn, "SELECT id, so_hieu, ten_day_du, ngay_ban_hanh, ngay_hieu_luc FROM van_ban WHERE so_hieu = ?", so_hieu_nguon)
    report, mem = preview(conn, van_ban_dich_id)
    mem.close()
    kq = {r.lenh_id: r for r in report.results}
    rows = conn.execute("SELECT * FROM lenh_sua_doi WHERE van_ban_nguon_id = ? AND van_ban_dich_id = ? ORDER BY thu_tu",
                        (src["id"], van_ban_dich_id)).fetchall()
    out = [f"# Lệnh sửa đổi của {src['so_hieu']} — {src['ten_day_du']}", "",
           f"Ngày ban hành {src['ngay_ban_hanh']}, hiệu lực {src['ngay_hieu_luc']}. {len(rows)} lệnh; "
           f"áp thử: {sum(1 for r in rows if kq.get(r['id']) and kq[r['id']].ok)} chạy được, "
           f"{sum(1 for r in rows if kq.get(r['id']) and not kq[r['id']].ok)} lỗi.", "",
           "Đối chiếu từng lệnh với văn bản luật sửa đổi rồi mới duyệt.", ""]
    for r in rows:
        res = kq.get(r["id"])
        trang_thai = "OK" if res and res.ok else "LỖI"
        out.append(f"## #{r['thu_tu']} {r['vi_tri_nguon']} — {r['loai_thao_tac']} — {r['tham_chieu_dich']}  [{trang_thai}; {r['trang_thai_duyet']}]")
        if r["hieu_luc_tu"]:
            out.append(f"- Hiệu lực từ: {r['hieu_luc_tu']} ({r['can_cu_hieu_luc'] or ''})")
        if r["cum_tu_cu"] is not None or r["cum_tu_moi"] is not None:
            out.append(f"- Cụm từ: “{r['cum_tu_cu'] or ''}” → “{r['cum_tu_moi'] or ''}” (phạm vi: {r['pham_vi'] or 'đơn vị'})")
        try:
            kieu = (json.loads(r["dich_json"]) or {}).get("kieu") if r["dich_json"] else None
        except ValueError:
            kieu = None
        if kieu:
            out.append(f"- Kiểu thay từ: {kieu}")
        if r["noi_dung_moi"]:
            out.append(f"- Nội dung mới: {_cut(r['noi_dung_moi'])}")
        if res:
            for p in res.problems:
                out.append(f"- {p.level}: {p.message}")
            if res.ok:
                out.append(f"- Kết quả áp thử: +{res.versions_created} phiên bản, đóng {res.versions_closed}, nút mới {res.nodes_created}")
        out.append("")
    return "\n".join(out)
