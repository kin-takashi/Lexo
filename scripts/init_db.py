"""Tạo (hoặc kiểm tra) file SQLite theo schema.

    python scripts/init_db.py               # dùng paths.db trong config.yaml (mặc định db/luat.sqlite)
    python scripts/init_db.py --db X.sqlite # chỉ định file khác
    python scripts/init_db.py --reset       # DB cũ khác phiên bản schema: đổi tên thành bản sao lưu rồi tạo mới

Chạy lại an toàn: DB đã đúng phiên bản thì không đổi gì.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # để import được src.* khi chạy như script

from src.store import SCHEMA_VERSION, backup_and_remove, connect, init_db  # noqa: E402


def db_path_from_config() -> Path:
    import yaml

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return ROOT / cfg["paths"]["db"]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Tạo DB SQLite của Lexo theo schema.")
    parser.add_argument("--db", type=Path, help="đường dẫn file SQLite (mặc định lấy từ config.yaml)")
    parser.add_argument("--reset", action="store_true",
                        help="đổi tên DB hiện có thành bản sao lưu (.bak-thời gian) rồi tạo DB mới đúng phiên bản")
    args = parser.parse_args()

    path = args.db or db_path_from_config()
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        backup = backup_and_remove(path)
        if backup:
            print(f"[OK] DB cũ đã đổi tên thành {backup.name}")
    conn = connect(path)
    try:
        init_db(conn)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
    except RuntimeError as e:
        print(f"[LỖI] {e}")
        return 1
    finally:
        conn.close()
    print(f"[OK] {path} — schema phiên bản {SCHEMA_VERSION}")
    print("Bảng: " + ", ".join(tables))
    return 0


if __name__ == "__main__":
    sys.exit(main())
