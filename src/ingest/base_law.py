"""Chuẩn bị (stage) và nạp VĂN BẢN GỐC vào SQLite.

stage_base_law: docx -> parse -> validate -> raw/<slug>/{file gốc, parsed.json}
ingest_base_law: parsed.json + review.json hợp lệ -> van_ban, log_nap, don_vi_luat, phien_ban_noi_dung (một transaction)
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.ingest.docx_text import extract_docx
from src.parse.base_law import parse_base_law
from src.parse.model import Node, ParsedLaw
from src.review.base_law_review import blocking_problems, file_sha256, load_parsed, load_review, save_parsed, slugify_so_hieu
from src.validate.base_law import Flag, validate_base_law

STEP = 1000     # thu_tu cách quãng để sau này chèn không phải đánh số lại


class IngestError(Exception):
    pass


@dataclass
class Staged:
    law: ParsedLaw
    flags: list[Flag]
    directory: Path
    parsed_path: Path
    parsed_sha256: str
    raw_copy: Path


def stage_base_law(
    docx_path: str | Path,
    raw_root: str | Path,
    *,
    ten_viet_tat: str | None = None,
    so_hieu: str | None = None,
) -> Staged:
    docx_path = Path(docx_path)
    extracted = extract_docx(docx_path)
    law = parse_base_law(
        extracted.lines, extracted.header_text, ten_viet_tat=ten_viet_tat, so_hieu=so_hieu, source=extracted.source_info()
    )
    flags = validate_base_law(law)
    if not law.meta.so_hieu:
        raise IngestError("Không đọc được số hiệu; chạy lại với --so-hieu")
    directory = Path(raw_root) / slugify_so_hieu(law.meta.so_hieu)
    directory.mkdir(parents=True, exist_ok=True)
    raw_copy = directory / docx_path.name
    if raw_copy.exists() and file_sha256(raw_copy) != extracted.sha256:
        raise IngestError(f"{raw_copy} đã có và KHÁC file đầu vào; không ghi đè file gốc. Kiểm tra lại đầu vào.")
    if not raw_copy.exists():
        shutil.copy2(docx_path, raw_copy)
    parsed_path = directory / "parsed.json"
    sha = save_parsed(law, parsed_path)
    return Staged(law, flags, directory, parsed_path, sha, raw_copy)


def _insert_nodes(conn: sqlite3.Connection, nodes: list[Node], van_ban_id: int, cha_id: int | None, meta: dict) -> int:
    count = 0
    for k, node in enumerate(nodes, start=1):
        dv_id = conn.execute(
            "INSERT INTO don_vi_luat (van_ban_id, cha_id, loai) VALUES (?, ?, ?)", (van_ban_id, cha_id, node.loai)
        ).lastrowid
        conn.execute(
            """INSERT INTO phien_ban_noi_dung
               (don_vi_id, ky_hieu, thu_tu, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den,
                van_ban_tao_ra_id, lenh_tao_ra_id, lenh_dong_id, doi_chieu_hop_nhat, nguoi_duyet, ngay_duyet)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, 'chua_doi_chieu', ?, ?)""",
            (dv_id, node.ky_hieu, k * STEP, node.tieu_de, node.noi_dung, meta["hieu_luc_tu"], van_ban_id,
             meta["nguoi_duyet"], meta["ngay_duyet"]),
        )
        count += 1 + _insert_nodes(conn, node.children, van_ban_id, dv_id, meta)
    return count


def ingest_base_law(conn: sqlite3.Connection, directory: str | Path, *, raw_root: str | Path | None = None) -> dict:
    """Nạp văn bản gốc đã stage + đã duyệt. Trả về thống kê. Ném IngestError nếu chưa đủ điều kiện."""
    directory = Path(directory)
    parsed_path = directory / "parsed.json"
    if not parsed_path.exists():
        raise IngestError(f"Không có {parsed_path}; chạy parse_base_law.py trước.")
    law = load_parsed(parsed_path)
    review = load_review(directory / "review.json")
    parsed_sha = file_sha256(parsed_path)
    problems = blocking_problems(law, review, parsed_sha)
    if problems:
        raise IngestError("Chưa thể nạp:\n  - " + "\n  - ".join(problems))

    raw_files = [p for p in directory.glob("*.docx")]
    src_name = law.source.get("name")
    raw_copy = directory / src_name if src_name else None
    if raw_copy is None or not raw_copy.exists():
        raise IngestError(f"Không thấy file gốc {src_name!r} trong {directory} (thấy: {[p.name for p in raw_files]})")
    if file_sha256(raw_copy) != law.source.get("sha256"):
        raise IngestError("File gốc trong raw/ đã bị đổi so với lúc parse (sha256 khác).")

    m = law.meta
    assert m.so_hieu and m.ten_day_du and m.loai and m.ngay_hieu_luc     # blocking_problems đã chặn thiếu metadata (mức LỖI)
    if conn.execute("SELECT 1 FROM van_ban WHERE so_hieu = ?", (m.so_hieu,)).fetchone():
        raise IngestError(f"Văn bản {m.so_hieu} đã có trong CSDL.")

    # Lưu dấu '/' trên mọi hệ điều hành (as_posix) để CSDL không phụ thuộc Windows hay Linux.
    root = Path(raw_root) if raw_root else None
    rel_raw = raw_copy.relative_to(root).as_posix() if root and raw_copy.is_relative_to(root) else raw_copy.as_posix()
    flags = validate_base_law(law)
    waived = review.get("mien_loi", {})
    ghi_chu = f"parse regex; {len(flags)} cờ validator; miễn {len(waived)} lỗi: " + "; ".join(
        f"{k} => {v}" for k, v in sorted(waived.items())
    ) if waived else f"parse regex; {len(flags)} cờ validator; không miễn lỗi"
    with conn:
        van_ban_id = conn.execute(
            """INSERT INTO van_ban (so_hieu, ten_viet_tat, ten_day_du, loai, ngay_ban_hanh, ngay_hieu_luc_theo_van_ban,
                                    ngay_hieu_luc, trang_thai, nguon, file_goc)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'con_hieu_luc', ?, ?)""",
            (m.so_hieu, m.ten_viet_tat, m.ten_day_du, m.loai, m.ngay_ban_hanh, m.ngay_hieu_luc, m.ngay_hieu_luc,
             src_name, rel_raw),
        ).lastrowid
        conn.execute(
            "INSERT INTO log_nap (van_ban_id, file_nguon, duong_dan_raw, vai_tro, phuong_phap, mo_hinh_su_dung, ket_qua, ghi_chu) "
            "VALUES (?, ?, ?, 'goc', 'regex', NULL, 'thanh_cong', ?)",
            (van_ban_id, src_name, rel_raw, ghi_chu),
        )
        n = _insert_nodes(
            conn, law.roots, van_ban_id, None,
            {"hieu_luc_tu": m.ngay_hieu_luc, "nguoi_duyet": review["nguoi_duyet"], "ngay_duyet": review["ngay_duyet"]},
        )
    return {"van_ban_id": van_ban_id, "so_hieu": m.so_hieu, "so_nut": n, "so_loi_mien": len(waived)}
