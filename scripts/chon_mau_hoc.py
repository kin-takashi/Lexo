"""Xuất tập học sạch (không trùng tổ hợp Điều với bộ đo) và các tập con lồng nhau, định dạng SFT (messages).

  python scripts/chon_mau_hoc.py                         # ghi train/sach/
  python scripts/chon_mau_hoc.py --hat 7 --co 50 100     # đổi hạt, đổi các cỡ

Ghi: sft_train_sach.jsonl (đủ), sft_train_n<k>.jsonl (k mẫu đầu của xếp hạng), sft_val_sach.jsonl (tập val cố định theo id, đã bỏ mẫu trùng),
xep_hang.json (hạt, thứ tự, id bị loại, mã băm nguồn) và SHA256SUMS. Tập val chỉ để theo dõi loss, không phải bộ đo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.index import bo_cau_hoi  # noqa: E402
from src.index.chon_mau import mau_trung, xep_hang  # noqa: E402
from src.index.tap_train import MAC_DINH, doc_train, dong_sft, kiem_tra_hop_le, tap_cua  # noqa: E402


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _ghi_jsonl(p: Path, mau: list[dict]) -> None:
    p.write_text("".join(json.dumps(dong_sft(x), ensure_ascii=False) + "\n" for x in mau), encoding="utf-8", newline="\n")


def _tom_tat(ten: str, mau: list[dict]) -> str:
    so_hv = Counter(min(len(x["hanh_vi"]), 4) for x in mau)
    dieu = {h["dieu"][0] for x in mau for h in x["hanh_vi"]}
    dai = sum(len(x["tinh_huong"]) for x in mau) // max(len(mau), 1)
    return (f"{ten}: {len(mau)} mẫu, {sum(len(x['hanh_vi']) for x in mau)} hành vi, {len(dieu)} Điều khác nhau, "
            f"số hành vi/mẫu " + ", ".join(f"{'4+' if k == 4 else k}: {so_hv[k]}" for k in sorted(so_hv)) + f", dài TB {dai} ký tự")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, default=MAC_DINH)
    ap.add_argument("--bo-cau-hoi", type=Path, default=bo_cau_hoi.MAC_DINH)
    ap.add_argument("--ra-dir", type=Path, default=ROOT / "train" / "sach")
    ap.add_argument("--hat", type=int, default=42)
    ap.add_argument("--co", type=int, nargs="+", default=[50, 100, 200])
    ap.add_argument("--val-ti-le", type=float, default=0.1)
    args = ap.parse_args()
    mau = doc_train(args.train)
    loi = kiem_tra_hop_le(mau)
    if loi:
        sys.exit("LỖI: tập học có lỗi, chạy scripts/kiem_tra_train.py (đầu tiên: " + loi[0] + ")")
    cau_do = bo_cau_hoi.doc_bo(args.bo_cau_hoi, None, None)
    bo = mau_trung(mau, cau_do)
    bo_set = set(bo)
    sach = [x for x in mau if x["id"] not in bo_set]
    tr = [x for x in sach if tap_cua(x["id"], args.val_ti_le) == "train"]
    va = [x for x in sach if tap_cua(x["id"], args.val_ti_le) == "val"]
    thu_tu = xep_hang(tr, args.hat)
    theo_id = {x["id"]: x for x in tr}
    args.ra_dir.mkdir(parents=True, exist_ok=True)
    tep = ["sft_train_sach.jsonl", "sft_val_sach.jsonl"]
    _ghi_jsonl(args.ra_dir / tep[0], [theo_id[i] for i in thu_tu])
    _ghi_jsonl(args.ra_dir / tep[1], sorted(va, key=lambda x: x["id"]))
    print(f"loại {len(bo)} mẫu trùng tổ hợp Điều với bộ đo (train {sum(tap_cua(i, args.val_ti_le) == 'train' for i in bo)}, val {sum(tap_cua(i, args.val_ti_le) == 'val' for i in bo)})")
    print(_tom_tat("train sạch (đủ)", tr))
    for k in sorted(set(args.co)):
        if not 0 < k < len(tr):
            sys.exit(f"LỖI: cỡ {k} phải nằm trong (0, {len(tr)})")
        ten = f"sft_train_n{k}.jsonl"
        tep.append(ten)
        con = [theo_id[i] for i in thu_tu[:k]]
        _ghi_jsonl(args.ra_dir / ten, con)
        print(_tom_tat(f"  n{k}", con))
    print(_tom_tat("val sạch", va))
    xep = {"hat": args.hat, "nguon_sha256": _sha(args.train), "bo_do_sha256": _sha(args.bo_cau_hoi), "val_ti_le": args.val_ti_le,
           "id_bi_loai": bo, "id_theo_thu_tu": thu_tu, "id_val": sorted(x["id"] for x in va)}
    (args.ra_dir / "xep_hang.json").write_text(json.dumps(xep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tep.append("xep_hang.json")
    (args.ra_dir / "SHA256SUMS").write_text("".join(f"{_sha(args.ra_dir / t)}  {t}\n" for t in tep), encoding="utf-8", newline="\n")
    print(f"Đã ghi {len(tep) + 1} file vào {args.ra_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
