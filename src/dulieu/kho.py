"""Kết nối và khởi tạo db/du_lieu.sqlite (dữ liệu huấn luyện + đánh giá kèm nguồn gốc và lịch sử duyệt nhãn)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 2


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Mở kết nối: bật khóa ngoại, truy cập hàng theo tên cột."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Tạo bảng từ schema.sql. Gọi lại an toàn; DB có phiên bản schema khác thì báo lỗi (dựng lại bằng --reset)."""
    hien_tai = conn.execute("PRAGMA user_version").fetchone()[0]
    if hien_tai == SCHEMA_VERSION:
        return
    if hien_tai != 0:
        raise RuntimeError(
            f"du_lieu.sqlite có schema phiên bản {hien_tai}, mã nguồn cần {SCHEMA_VERSION}. "
            "Dựng lại bằng: python scripts/nhap_du_lieu.py --reset (DB cũ được đổi tên thành bản sao lưu, không mất)."
        )
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
