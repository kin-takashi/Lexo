"""Nạp KẾT QUẢ TRÍCH LỆNH của một luật sửa đổi vào SQLite ở trạng thái 'cho_duyet'.

Ghi: van_ban (luật sửa đổi), log_nap (vai_tro 'sua_doi'), lenh_sua_doi (mọi lệnh, chờ duyệt), quan_he_van_ban ('sua_doi'),
dieu_khoan_van_ban (nguyên văn Điều hiệu lực / chuyển tiếp). CHƯA đổi phien_ban_noi_dung: việc đó do apply.rebuild làm, và chỉ dùng
lệnh đã duyệt. Mục nào bộ trích không hiểu (unparsed) KHÔNG vào CSDL — chỉ nằm trong commands.json và ghi_chu của log_nap.
"""
from __future__ import annotations

import json
import sqlite3

from src.apply.rebuild import clear_derived
from src.extract.regex_extractor import ExtractionResult
from src.ingest.base_law import IngestError
from src.parse.amending import AmendingLaw


def load_extraction(
    conn: sqlite3.Connection,
    law: AmendingLaw,
    result: ExtractionResult,
    *,
    van_ban_dich_so_hieu: str,
    file_nguon: str,
    duong_dan_raw: str | None = None,
    thay_lenh_cho_duyet: bool = False,
) -> dict:
    m = law.meta
    for name in ("so_hieu", "ten_day_du", "loai", "ngay_ban_hanh", "ngay_hieu_luc"):
        if not getattr(m, name):
            raise IngestError(f"Luật sửa đổi thiếu {name}; chưa thể nạp (kiểm tra amending.json)")
    dest = conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (van_ban_dich_so_hieu,)).fetchone()
    if dest is None:
        raise IngestError(f"Văn bản đích {van_ban_dich_so_hieu} chưa có trong CSDL; nạp văn bản gốc trước")
    dest_id = dest["id"]
    src = conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (m.so_hieu,)).fetchone()
    with conn:
        if src is not None:
            n_approved = conn.execute("SELECT COUNT(*) FROM lenh_sua_doi WHERE van_ban_nguon_id = ? AND trang_thai_duyet <> 'cho_duyet'",
                                      (src["id"],)).fetchone()[0]
            if not thay_lenh_cho_duyet:
                raise IngestError(f"{m.so_hieu} đã có trong CSDL; dùng --thay để nạp lại các lệnh chờ duyệt")
            if n_approved:
                raise IngestError(f"{m.so_hieu} đã có {n_approved} lệnh được duyệt/từ chối; không nạp đè để khỏi mất kết quả duyệt")
            clear_derived(conn, dest_id)          # phiên bản dẫn xuất tham chiếu lệnh nên phải xoá trước
            conn.execute("DELETE FROM lenh_sua_doi WHERE van_ban_nguon_id = ?", (src["id"],))
            conn.execute("DELETE FROM log_nap WHERE van_ban_id = ? AND vai_tro = 'sua_doi'", (src["id"],))
            conn.execute("DELETE FROM dieu_khoan_van_ban WHERE van_ban_id = ?", (src["id"],))
            src_id = src["id"]
            conn.execute("UPDATE van_ban SET ngay_ban_hanh = ?, ngay_hieu_luc_theo_van_ban = ?, ngay_hieu_luc = ? WHERE id = ?",
                         (m.ngay_ban_hanh, m.ngay_hieu_luc, m.ngay_hieu_luc, src_id))
        else:
            src_id = conn.execute(
                """INSERT INTO van_ban (so_hieu, ten_viet_tat, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban,
                                        ngay_hieu_luc, trang_thai, nguon, file_goc)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, 'con_hieu_luc', ?, ?)""",
                (m.so_hieu, m.ten_day_du, m.loai, m.ngay_ban_hanh, m.ngay_hieu_luc, m.ngay_hieu_luc, file_nguon,
                 duong_dan_raw)).lastrowid
        ghi_chu = (f"trích lệnh bằng regex; {result.n_leaf} mục lệnh trong phạm vi, hiểu {result.n_parsed_leaf} "
                   f"({result.coverage():.1%}), {len(result.commands)} lệnh; chưa hiểu {len(result.unparsed)}: "
                   + ", ".join(u.item_id for u in result.unparsed[:20]))
        log_id = conn.execute(
            "INSERT INTO log_nap (van_ban_id, file_nguon, duong_dan_raw, vai_tro, phuong_phap, mo_hinh_su_dung, ket_qua, ghi_chu) "
            "VALUES (?, ?, ?, 'sua_doi', 'regex', NULL, 'thanh_cong', ?)", (src_id, file_nguon, duong_dan_raw, ghi_chu)).lastrowid
        hl = law.dieu_hieu_luc
        can_cu = (f"Điều {hl.ky_hieu} {m.so_hieu} (ngày hiệu lực mặc định của luật)" if hl else f"{m.so_hieu} (mặc định)")
        for k, c in enumerate(result.commands, start=1):
            conn.execute(
                """INSERT INTO lenh_sua_doi (van_ban_nguon_id, log_nap_id, thu_tu, loai_thao_tac, van_ban_dich_id, tham_chieu_dich,
                       dich_json, noi_dung_moi, cum_tu_cu, cum_tu_moi, pham_vi, hieu_luc_tu, can_cu_hieu_luc, vi_tri_nguon,
                       khoi_nguon, nguon_dong_tu, nguon_dong_den, lenh_goc_json, trang_thai_duyet)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cho_duyet')""",
                (src_id, log_id, k, c.loai_thao_tac, dest_id, c.tham_chieu_dich,
                 json.dumps(c.dich, ensure_ascii=False) if c.dich is not None else None, c.noi_dung_moi, c.cum_tu_cu, c.cum_tu_moi,
                 c.pham_vi, m.ngay_hieu_luc, can_cu, c.vi_tri_nguon, c.item_id, c.nguon_dong_tu, c.nguon_dong_den,
                 json.dumps(c.to_dict(), ensure_ascii=False)))
        conn.execute("INSERT OR IGNORE INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id) VALUES (?, 'sua_doi', ?)",
                     (src_id, dest_id))
        for loai, clause in (("hieu_luc", law.dieu_hieu_luc), ("chuyen_tiep", law.dieu_chuyen_tiep)):
            if clause is not None:
                conn.execute("INSERT INTO dieu_khoan_van_ban (van_ban_id, loai, vi_tri, noi_dung, thu_tu) VALUES (?, ?, ?, ?, 0)",
                             (src_id, loai, f"Điều {clause.ky_hieu}", f"{clause.tieu_de}\n{clause.noi_dung}".strip()))
    return {"van_ban_nguon_id": src_id, "log_nap_id": log_id, "so_lenh": len(result.commands), "so_chua_hieu": len(result.unparsed)}
