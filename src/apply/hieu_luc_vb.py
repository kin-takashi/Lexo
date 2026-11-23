"""Ghi nhận hiệu lực của CẢ MỘT văn bản khi nguồn là văn bản khác mà kho chưa nạp nội dung.

Hai việc, đều làm bằng tay có người chịu trách nhiệm (không suy đoán từ nội dung luật):

  ghi_hoan_hieu_luc  nghị quyết lùi/hoãn ngày bắt đầu hiệu lực của một bộ luật
                     (vd Nghị quyết 144/2016/QH13 lùi BLHS 2015 từ 01/07/2016 sang 01/01/2018).
                     Ghi thành một lệnh `hoan_hieu_luc` ĐÃ DUYỆT (kèm văn bản nguồn + nhật ký nạp) rồi dựng lại phiên bản,
                     đúng đường mà engine vốn dùng cho lệnh sửa đổi nên có đủ nguồn gốc để truy vết.
  dat_het_hieu_luc   bộ luật bị bộ luật mới thay thế, hết hiệu lực từ một ngày
                     (vd BLHS 1999 hết hiệu lực khi BLHS 2015 bắt đầu có hiệu lực). Đặt `van_ban.ngay_het_hieu_luc` (ngày ĐẦU TIÊN
                     không còn hiệu lực, khoảng nửa mở) rồi dựng lại để mọi phiên bản bị cắt đúng ngày đó.

Cả hai chạy trong một SAVEPOINT: lỗi thì CSDL về nguyên trạng. `commit=False` để người gọi tự quyết (dùng cho chạy thử trên bản sao).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from .rebuild import RebuildReport, rebuild


class HieuLucError(ValueError):
    """Dữ liệu nhập không hợp lệ (ngày sai, văn bản không có...); CSDL không bị thay đổi."""


def _iso(v: str | None, ten: str) -> str:
    try:
        return date.fromisoformat(v).isoformat()      # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HieuLucError(f"{ten} phải có dạng YYYY-MM-DD, nhận được {v!r}") from None


def _tim(conn: sqlite3.Connection, so_hieu: str) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM van_ban WHERE so_hieu = ?", (so_hieu,)).fetchone()
    if r is None:
        raise HieuLucError(f"Chưa có văn bản {so_hieu} trong CSDL.")
    return r


def _rao(conn: sqlite3.Connection, name: str):
    """Context đơn giản: SAVEPOINT; thoát lỗi thì ROLLBACK TO, thoát êm thì RELEASE. Mở giao dịch trước để RELEASE không tự commit
    (commit=False phải thật sự chưa ghi)."""
    class _Sp:
        started = False

        def __enter__(self_):
            self_.started = not conn.in_transaction
            if self_.started:
                conn.execute("BEGIN")
            conn.execute(f"SAVEPOINT {name}")

        def __exit__(self_, et, ev, tb):
            if et is not None:
                conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
            if et is not None and self_.started:
                conn.rollback()
            return False
    return _Sp()


def ghi_hoan_hieu_luc(
    conn: sqlite3.Connection,
    so_hieu_dich: str,
    ngay_moi: str,
    *,
    so_hieu_nguon: str,
    ten_nguon: str,
    ngay_ban_hanh_nguon: str,
    can_cu: str,
    nguoi: str,
    hieu_luc_tu: str | None = None,
    loai_nguon: str = "nghi_quyet",
    vi_tri_nguon: str | None = None,
    ghi_chu: str | None = None,
    commit: bool = True,
) -> dict:
    """Ghi (idempotent) lệnh `hoan_hieu_luc`: văn bản `so_hieu_dich` bắt đầu có hiệu lực từ `ngay_moi` theo `so_hieu_nguon`.

    - Văn bản nguồn chưa có trong kho thì tạo một dòng `van_ban` chỉ có siêu dữ liệu (nội dung chưa nạp) cùng một dòng `log_nap`
      (phương pháp thủ công); đã có thì dùng lại, không sửa.
    - `hieu_luc_tu`: ngày nguồn có hiệu lực (mặc định = ngày ban hành); `can_cu`: vì sao ngày đó (ghi vào lệnh để người đọc kiểm chứng).
    - Đã duyệt sẵn dưới tên `nguoi`; dựng lại phiên bản của văn bản đích.
    Trả về {lenh_id, van_ban_nguon_id, da_co, ngay_cu, ngay_moi, bao_cao}."""
    ngay_moi = _iso(ngay_moi, "ngày hiệu lực mới")
    ban_hanh = _iso(ngay_ban_hanh_nguon, "ngày ban hành của văn bản nguồn")
    tu = _iso(hieu_luc_tu or ban_hanh, "ngày hiệu lực của văn bản nguồn")
    if not nguoi.strip():
        raise HieuLucError("Phải ghi tên người chịu trách nhiệm (nguoi).")
    if not can_cu.strip():
        raise HieuLucError("Phải ghi căn cứ (can_cu): vì sao ngày hiệu lực là ngày đó.")
    dich = _tim(conn, so_hieu_dich)
    if dich["ngay_ban_hanh"] and ngay_moi < dich["ngay_ban_hanh"]:
        raise HieuLucError(f"Ngày hiệu lực mới {ngay_moi} sớm hơn ngày ban hành {dich['ngay_ban_hanh']} của {so_hieu_dich}.")
    if tu < ban_hanh:
        raise HieuLucError("Ngày hiệu lực của văn bản nguồn không được sớm hơn ngày ban hành của nó.")
    with _rao(conn, "hlvb_hoan"):
        nguon = conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (so_hieu_nguon,)).fetchone()
        if nguon is None:
            nid = conn.execute(
                "INSERT INTO van_ban (so_hieu, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban, ngay_hieu_luc, trang_thai, nguon) "
                "VALUES (?, ?, ?, ?, ?, ?, 'con_hieu_luc', ?)",
                (so_hieu_nguon, ten_nguon, loai_nguon, ban_hanh, tu, tu, "ghi thủ công; nội dung văn bản chưa được nạp")).lastrowid
        else:
            nid = nguon["id"]
        ngay_cu = dich["ngay_hieu_luc_theo_van_ban"]
        trung = conn.execute(
            "SELECT id FROM lenh_sua_doi WHERE van_ban_nguon_id = ? AND van_ban_dich_id = ? AND loai_thao_tac = 'hoan_hieu_luc' "
            "AND ngay_hieu_luc_moi = ?", (nid, dich["id"], ngay_moi)).fetchone()
        if trung:
            return {"lenh_id": trung["id"], "van_ban_nguon_id": nid, "da_co": True, "ngay_cu": ngay_cu, "ngay_moi": ngay_moi, "bao_cao": None}
        log = conn.execute("SELECT id FROM log_nap WHERE van_ban_id = ? AND vai_tro = 'sua_doi' AND phuong_phap = 'thu_cong' ORDER BY id",
                           (nid,)).fetchone()
        log_id = log["id"] if log else conn.execute(
            "INSERT INTO log_nap (van_ban_id, file_nguon, vai_tro, phuong_phap, ket_qua, ghi_chu) "
            "VALUES (?, ?, 'sua_doi', 'thu_cong', 'thanh_cong', ?)",
            (nid, "(ghi thủ công, không có tệp nguồn)", f"nhập bởi {nguoi}")).lastrowid
        thu_tu = conn.execute("SELECT COALESCE(MAX(thu_tu), 0) + 1 FROM lenh_sua_doi WHERE log_nap_id = ?", (log_id,)).fetchone()[0]
        lenh_id = conn.execute(
            """INSERT INTO lenh_sua_doi (van_ban_nguon_id, log_nap_id, thu_tu, loai_thao_tac, van_ban_dich_id, tham_chieu_dich, dich_json,
                   ngay_hieu_luc_moi, hieu_luc_tu, can_cu_hieu_luc, vi_tri_nguon, trang_thai_duyet, nguoi_duyet, ngay_duyet, ghi_chu_duyet)
               VALUES (?, ?, ?, 'hoan_hieu_luc', ?, ?, NULL, ?, ?, ?, ?, 'da_duyet', ?, ?, ?)""",
            (nid, log_id, thu_tu, dich["id"], f"toàn bộ {so_hieu_dich}", ngay_moi, tu, can_cu, vi_tri_nguon, nguoi,
             date.today().isoformat(), ghi_chu)).lastrowid
        conn.execute("INSERT OR IGNORE INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id, ghi_chu) VALUES (?, 'hoan_hieu_luc', ?, ?)",
                     (nid, dich["id"], f"hiệu lực từ {ngay_moi}"))
        bao_cao: RebuildReport = rebuild(conn, dich["id"], commit=False)
    if commit:
        conn.commit()
    return {"lenh_id": lenh_id, "van_ban_nguon_id": nid, "da_co": False, "ngay_cu": ngay_cu, "ngay_moi": ngay_moi, "bao_cao": bao_cao}


def dat_het_hieu_luc(
    conn: sqlite3.Connection,
    so_hieu: str,
    ngay_het: str,
    *,
    thay_boi: str | None = None,
    commit: bool = True,
) -> dict:
    """Văn bản `so_hieu` hết hiệu lực từ `ngay_het` (ngày đầu tiên KHÔNG còn hiệu lực; ngày cuối còn hiệu lực là hôm trước).
    `thay_boi`: số hiệu bộ luật thay thế (ghi quan hệ 'thay_the'). Dựng lại phiên bản để mọi khoảng hiệu lực bị cắt đúng ngày đó.
    Trả về {van_ban_id, ngay_het, canh_bao: [..], bao_cao}."""
    ngay_het = _iso(ngay_het, "ngày hết hiệu lực")
    vb = _tim(conn, so_hieu)
    if vb["ngay_hieu_luc"] and ngay_het <= vb["ngay_hieu_luc"]:
        raise HieuLucError(f"Ngày hết hiệu lực {ngay_het} không sau ngày bắt đầu hiệu lực {vb['ngay_hieu_luc']} của {so_hieu}.")
    canh_bao: list[str] = []
    moi = _tim(conn, thay_boi) if thay_boi else None
    if moi is not None and moi["ngay_hieu_luc"] and moi["ngay_hieu_luc"] != ngay_het:
        canh_bao.append(f"{thay_boi} bắt đầu hiệu lực {moi['ngay_hieu_luc']}, khác ngày hết hiệu lực {ngay_het} của {so_hieu}: "
                        "giữa hai mốc sẽ có khoảng trống hoặc chồng nhau.")
    with _rao(conn, "hlvb_het"):
        conn.execute("UPDATE van_ban SET ngay_het_hieu_luc = ?, trang_thai = ? WHERE id = ?",
                     (ngay_het, "het_hieu_luc" if ngay_het <= date.today().isoformat() else "con_hieu_luc", vb["id"]))
        if moi is not None:
            conn.execute("INSERT OR IGNORE INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id, ghi_chu) VALUES (?, 'thay_the', ?, ?)",
                         (moi["id"], vb["id"], f"{so_hieu} hết hiệu lực từ {ngay_het}"))
        bao_cao = rebuild(conn, vb["id"], commit=False)
    if commit:
        conn.commit()
    return {"van_ban_id": vb["id"], "ngay_het": ngay_het, "canh_bao": canh_bao, "bao_cao": bao_cao}
