"""Kiểm tra train/tinh_huong.json: lỗi định dạng, rò rỉ sang bộ đo, thống kê, và độ phủ các Điều về tội phạm.

  python scripts/kiem_tra_train.py                         # định dạng + rò rỉ + thống kê (+ phủ nếu có chỉ mục)
  python scripts/kiem_tra_train.py --index <chi_muc>       # còn kiểm số Điều đáp án có thật và liệt kê Điều chưa có mẫu nào
  python scripts/kiem_tra_train.py --bat-buoc-phu          # coi Điều chưa phủ là lỗi (thoát 1)

Thoát 0 nếu hợp lệ, 1 nếu có lỗi (in từng lỗi kèm id).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path  # noqa: E402
from src.index import bo_cau_hoi  # noqa: E402
from src.index.tap_train import MAC_DINH, TapTrainError, dieu_da_phu, doc_train, kiem_tra_hop_le, thong_ke  # noqa: E402


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, default=MAC_DINH)
    ap.add_argument("--bo-cau-hoi", type=Path, default=bo_cau_hoi.MAC_DINH, help="bộ đo để dò rò rỉ")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--khong-chi-muc", action="store_true")
    ap.add_argument("--bat-buoc-phu", action="store_true", help="Điều về tội phạm chưa có mẫu nào = lỗi")
    args = ap.parse_args()
    try:
        mau = doc_train(args.train)
    except TapTrainError as e:
        print(f"LỖI: {e}")
        return 1
    try:
        cau_do = [x["cau_hoi"] for x in bo_cau_hoi.doc_bo(args.bo_cau_hoi, None, None)]
    except bo_cau_hoi.BoCauHoiError as e:
        print(f"(không đọc được bộ đo, bỏ qua dò rò rỉ: {e})")
        cau_do = []
    loi = kiem_tra_hop_le(mau, cau_do)
    phu = dieu_da_phu(mau)
    chua_phu: list[str] = []
    if not args.khong_chi_muc:
        ip = args.index or index_path()
        if ip.exists():
            from src.index.cau_hoi import gom_dieu, loc_dieu_toi_pham
            from src.index.store import open_index
            g = gom_dieu(open_index(ip))
            co = set(g)
            loi += [f"Điều {d} (đáp án) không có trong chỉ mục" for d in sorted(phu, key=lambda s: (len(s), s)) if f"dieu {d}" not in co]
            toi = sorted((d.split()[1] for d in loc_dieu_toi_pham(g)), key=lambda s: (int(re.match(r"\d+", s).group()), s))
            chua_phu = [d for d in toi if d not in phu]
            print(f"phủ: {len(toi) - len(chua_phu)}/{len(toi)} Điều về tội phạm có ít nhất một hành vi làm đáp án")
            if chua_phu:
                print("  chưa phủ: " + ", ".join(f"{d}" for d in chua_phu))
            if args.bat_buoc_phu:
                loi += [f"Điều {d} chưa có mẫu nào" for d in chua_phu]
        else:
            print(f"(không thấy chỉ mục {ip}: bỏ qua kiểm số Điều có thật và độ phủ)")
    tk = thong_ke(mau)
    print(f"{args.train.name}: {tk['so_mau']} mẫu, {tk['tong_hanh_vi']} hành vi (đối chiếu {len(cau_do)} câu của bộ đo)")
    for t in ("loai", "nguon", "trang_thai"):
        print(f"  {t}: " + ", ".join(f"{k} {v}" for k, v in sorted(tk[t].items(), key=lambda kv: str(kv[0]))))
    print("  số hành vi / mẫu: " + ", ".join(f"{k}: {v}" for k, v in tk["so_hanh_vi"].items()))
    if phu:
        ds = sorted(phu.values())
        print(f"  số lần mỗi Điều làm đáp án: nhỏ nhất {ds[0]}, trung vị {ds[len(ds) // 2]}, lớn nhất {ds[-1]} ({len(phu)} Điều khác nhau)")
    for x in loi:
        print(f"  ! {x}")
    print("HỢP LỆ" if not loi else f"CÓ {len(loi)} LỖI")
    return 0 if not loi else 1


if __name__ == "__main__":
    sys.exit(main())
