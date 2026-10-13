"""Xuất bảng duyệt nhãn từ eval/bo_cau_hoi.json (id, câu hỏi, Điều, tiêu đề Điều; chia theo tập) thành markdown để đọc.

  python scripts/xuat_xem_duyet.py                      # mọi tập -> eval/xem_duyet.md
  python scripts/xuat_xem_duyet.py --tap dev --ra -     # in tập dev ra màn hình

Bảng được sinh ra từ file nguồn, đừng sửa tay: sửa eval/bo_cau_hoi.json rồi xuất lại.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, BoCauHoiError, bang_xem_duyet, doc_bo  # noqa: E402
from src.index.cau_hoi import gom_dieu  # noqa: E402
from src.index.store import open_index  # noqa: E402


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=(*TAP, "tat_ca"), default="tat_ca")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--ra", default=str(ROOT / "eval" / "xem_duyet.md"), help='file markdown ghi ra, "-" để in ra màn hình')
    args = ap.parse_args()
    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    try:
        cau = doc_bo(args.bo_cau_hoi, args.tap, None)
    except BoCauHoiError as e:
        sys.exit(f"LỖI: {e}")
    tieu_de = {d: v["tieu_de"] for d, v in gom_dieu(open_index(ip)).items()}
    md = bang_xem_duyet(cau, tieu_de)
    if args.ra == "-":
        print(md)
    else:
        Path(args.ra).write_text(md, encoding="utf-8", newline="\n")
        print(f"Đã ghi {args.ra} ({len(cau)} câu).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
