"""Bước 1a: parse văn bản gốc (.docx) -> raw/<số hiệu>/parsed.json + báo cáo validator. Chưa ghi vào CSDL.

Ví dụ:  python scripts/parse_base_law.py "inbox/Bộ-luật-100-2015-QH13.docx" --ten-viet-tat BLHS
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import raw_dir  # noqa: E402
from src.ingest.base_law import IngestError, stage_base_law  # noqa: E402
from src.validate.base_law import format_report, has_errors  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--ten-viet-tat", help="tên viết tắt dùng để tra cứu, vd BLHS")
    ap.add_argument("--so-hieu", help="chỉ cần khi parser không đọc được số hiệu")
    args = ap.parse_args()
    try:
        staged = stage_base_law(args.docx, raw_dir(), ten_viet_tat=args.ten_viet_tat, so_hieu=args.so_hieu)
    except IngestError as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    print(format_report(staged.law, staged.flags))
    print(f"\nĐã ghi: {staged.parsed_path}")
    print("Bước tiếp: mở giao diện duyệt (streamlit run src/review/app_base_law.py), duyệt xong chạy scripts/ingest_base_law.py")
    return 1 if has_errors(staged.flags) else 0


if __name__ == "__main__":
    raise SystemExit(main())
