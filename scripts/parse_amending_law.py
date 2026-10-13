"""Bước 2a: parse luật sửa đổi (.docx) -> raw/<số hiệu>/amending.json + báo cáo validator. Chưa ghi vào CSDL.

Ví dụ:  python scripts/parse_amending_law.py "inbox/Luật-12-2017-QH14.docx"
        python scripts/parse_amending_law.py "inbox/59_2024_QH15_606865.docx"

Phạm vi (văn bản nào được áp dụng sửa đổi) lấy từ config.yaml, mục pham_vi_sua_doi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import amending_scope, raw_dir  # noqa: E402
from src.ingest.amending_law import IngestError, stage_amending_law  # noqa: E402
from src.validate.amending import format_report, has_errors  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--so-hieu", help="chỉ cần khi parser không đọc được số hiệu")
    ap.add_argument("--dieu-sua-doi", help="ký hiệu các Điều chứa lệnh sửa đổi, cách nhau dấu phẩy (mặc định tự nhận theo tiêu đề)")
    args = ap.parse_args()
    aliases, scope = amending_scope()
    dieu = [x.strip() for x in args.dieu_sua_doi.split(",")] if args.dieu_sua_doi else None
    try:
        staged = stage_amending_law(args.docx, raw_dir(), aliases=aliases, pham_vi_so_hieu=scope,
                                    so_hieu=args.so_hieu, dieu_sua_doi=dieu)
    except IngestError as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    print(format_report(staged.law, staged.flags))
    print(f"\nĐã ghi: {staged.amending_path}")
    return 1 if has_errors(staged.flags) else 0


if __name__ == "__main__":
    raise SystemExit(main())
