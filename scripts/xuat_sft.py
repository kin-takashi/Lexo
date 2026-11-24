"""Xuất tập huấn luyện bước "tách hành vi" từ train/tinh_huong.json ra JSONL định dạng messages (dùng cho LoRA / SFT).

  python scripts/xuat_sft.py                      # train/sft_train.jsonl + train/sft_val.jsonl (val ~10%, chia cố định theo id)
  python scripts/xuat_sft.py --val-ti-le 0.15
  python scripts/xuat_sft.py --chi-da-duyet       # chỉ lấy mẫu trang_thai = da_duyet

Đích của mô hình CHỈ là {"hanh_vi": [mo_ta, ...]}: không có số Điều. Bộ đo eval/bo_cau_hoi.json không bao giờ đi vào đây.
Tập val dùng để theo dõi loss khi huấn luyện, KHÔNG phải bộ đo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.index.tap_train import MAC_DINH, TapTrainError, doc_train, dong_sft, kiem_tra_hop_le, tap_cua  # noqa: E402


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, default=MAC_DINH)
    ap.add_argument("--ra-dir", type=Path, default=ROOT / "train")
    ap.add_argument("--val-ti-le", type=float, default=0.1)
    ap.add_argument("--chi-da-duyet", action="store_true")
    args = ap.parse_args()
    if not 0 <= args.val_ti_le < 1:
        sys.exit("LỖI: --val-ti-le phải trong [0, 1)")
    try:
        mau = doc_train(args.train)
    except TapTrainError as e:
        sys.exit(f"LỖI: {e}")
    loi = kiem_tra_hop_le(mau)
    if loi:
        sys.exit("LỖI: file có lỗi, chạy python scripts/kiem_tra_train.py rồi sửa (đầu tiên: " + loi[0] + ")")
    if args.chi_da_duyet:
        mau = [x for x in mau if x.get("trang_thai") == "da_duyet"]
        if not mau:
            sys.exit("LỖI: chưa có mẫu nào da_duyet")
    ra = {"train": [], "val": []}
    for x in mau:
        ra[tap_cua(x["id"], args.val_ti_le)].append(dong_sft(x))
    args.ra_dir.mkdir(parents=True, exist_ok=True)
    for ten, dong in ra.items():
        p = args.ra_dir / f"sft_{ten}.jsonl"
        p.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong), encoding="utf-8", newline="\n")
        print(f"Đã ghi {p} ({len(dong)} dòng)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
