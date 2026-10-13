"""Kiểm tra eval/bo_cau_hoi.json sau khi sửa tay: lỗi định dạng, id / câu trùng, Điều trùng giữa các tập, thống kê theo tập và nguồn.

  python scripts/kiem_tra_bo_cau_hoi.py                     # kiểm định dạng và thống kê
  python scripts/kiem_tra_bo_cau_hoi.py --index <chi_muc>   # còn kiểm mọi số Điều đáp án có thật trong chỉ mục

Thoát 0 nếu hợp lệ, 1 nếu có lỗi (in từng lỗi kèm id câu).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, BoCauHoiError, doc_bo, kiem_tra_hop_le, thong_ke  # noqa: E402


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--index", type=Path, default=None, help="chỉ mục để kiểm số Điều có thật (mặc định: chỉ mục đang dùng nếu có)")
    ap.add_argument("--khong-chi-muc", action="store_true", help="bỏ qua việc kiểm số Điều trong chỉ mục")
    args = ap.parse_args()
    try:
        cau = doc_bo(args.bo_cau_hoi, None, None)
    except BoCauHoiError as e:
        print(f"LỖI: {e}")
        return 1
    loi = kiem_tra_hop_le(cau)
    if not args.khong_chi_muc:
        ip = args.index or index_path()
        if ip.exists():
            from src.index.cau_hoi import gom_dieu
            from src.index.store import open_index
            co = set(gom_dieu(open_index(ip)))
            loi += [f"{x.get('id')}: Điều {d} không có trong chỉ mục" for x in cau for d in x.get("dieu", []) if f"dieu {d}" not in co]
        else:
            print(f"(không thấy chỉ mục {ip}: bỏ qua kiểm số Điều có thật)")
    tk = thong_ke(cau)
    print(f"{args.bo_cau_hoi.name}: {len(cau)} câu")
    for t in ("tap", "loai", "nguon", "trang_thai"):
        print(f"  {t}: " + ", ".join(f"{k} {v}" for k, v in sorted(tk[t].items(), key=lambda kv: str(kv[0]))))
    dieu = {tap: {d for x in cau if x.get("tap") == tap and x.get("loai") == "don" for d in x.get("dieu", [])} for tap in TAP}
    print("  số Điều đáp án (loại don): " + ", ".join(f"{t} {len(v)}" for t, v in dieu.items()) + f"; tổng {len(set().union(*dieu.values()))}")
    for x in loi:
        print(f"  ! {x}")
    print("HỢP LỆ" if not loi else f"CÓ {len(loi)} LỖI")
    return 0 if not loi else 1


if __name__ == "__main__":
    sys.exit(main())
