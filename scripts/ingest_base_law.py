"""Bước 1b: nạp văn bản gốc ĐÃ DUYỆT (raw/<số hiệu>/parsed.json + review.json) vào SQLite.

Ví dụ:  python scripts/ingest_base_law.py 100-2015-QH13
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import db_path, raw_dir  # noqa: E402
from src.ingest.base_law import IngestError, ingest_base_law  # noqa: E402
from src.store import connect, init_db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="tên thư mục trong raw/, vd 100-2015-QH13")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    directory = raw_dir() / args.slug
    path = args.db or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        init_db(conn)
        stats = ingest_base_law(conn, directory, raw_root=raw_dir())
    except (IngestError, RuntimeError) as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    print(f"Đã nạp {stats['so_hieu']}: {stats['so_nut']} nút, {stats['so_loi_mien']} lỗi được miễn -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
