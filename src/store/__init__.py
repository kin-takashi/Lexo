"""Kho dữ liệu SQLite: kết nối và khởi tạo schema (Bước 0)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 3


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Mở kết nối: bật khóa ngoại (SQLite mặc định tắt) và cho truy cập hàng theo tên cột."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Tạo bảng, chỉ mục, trigger từ schema.sql. Gọi lại an toàn.

    DB đã có phiên bản schema khác thì báo lỗi: phien_ban_noi_dung là dữ liệu dẫn xuất nên có thể dựng
    lại DB; nếu cần giữ lenh_sua_doi đã duyệt thì phải viết migration.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == SCHEMA_VERSION:
        return
    if current != 0:
        raise RuntimeError(
            f"DB có schema phiên bản {current}, mã nguồn cần phiên bản {SCHEMA_VERSION}. "
            "Dựng lại DB bằng: python scripts/init_db.py --reset (DB cũ được đổi tên thành bản sao lưu, không mất). "
            "Sau đó nạp lại văn bản: raw/ và review.json vẫn còn nguyên."
        )
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def backup_and_remove(path: str | Path) -> Path | None:
    """Đổi tên file DB cũ thành '<tên>.bak-YYYYmmdd-HHMMSS' (không xoá). Trả về đường dẫn bản sao lưu, None nếu không có file."""
    from datetime import datetime

    path = Path(path)
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    path.rename(backup)
    return backup
