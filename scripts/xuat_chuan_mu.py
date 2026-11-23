"""Xuất câu hỏi MÙ (chỉ id và chữ câu hỏi, KHÔNG đáp án) cùng lời nhắc để một phiên Claude mới tách hành vi làm «chuẩn».

  python scripts/xuat_chuan_mu.py                     # tập dev -> eval/chuan_mu/cau_hoi_mu_dev.json và LOI_NHAC_CHUAN_MU.md
  python scripts/xuat_chuan_mu.py --chi-id dn15-dn34

Lời nhắc dùng đúng HE_THONG mà mô hình tinh chỉnh học, nên «chuẩn» và mô hình làm cùng một việc. Mỗi bản chuẩn phải do một phiên Claude MỚI
(không thấy đáp án Điều, không thấy file bộ đo) tạo ra; lặp 3 phiên để có trần (Claude với Claude). Lưu mỗi câu trả lời thành
eval/chuan_mu/claude_1.json, claude_2.json, claude_3.json rồi chạy scripts/so_voi_chuan.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo, loc_theo_id  # noqa: E402
from src.index.tap_train import HE_THONG  # noqa: E402


def ghi(p: Path, noi_dung: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tam = p.with_name(p.name + ".tmp")
    tam.write_text(noi_dung, encoding="utf-8", newline="\n")
    os.replace(tam, p)


def loi_nhac(cau: dict[str, str]) -> str:
    n = len(cau)
    mau = '{"' + next(iter(cau)) + '": {"hanh_vi": ["...", "..."]}, ...}'
    khoi = (HE_THONG + f"\n\nCó {n} tình huống ĐỘC LẬP dưới đây, đánh số theo id. Với MỖI tình huống, làm đúng như hướng dẫn trên và xử lý riêng từng tình huống "
            f"(không liên hệ giữa các tình huống). Trả về MỘT JSON duy nhất dạng {mau} có đủ {n} id, không thêm chữ nào khác.\n\n"
            + "\n".join(f"{i}: {q}" for i, q in cau.items()))
    return ("# Lời nhắc cho bản tách CHUẨN (Claude làm mù)\n\n"
            "Cách làm: mở một phiên Claude MỚI (không có ngữ cảnh dự án Lexo, không đính kèm file bộ đo, không nhắc tới số Điều), dán nguyên khối dưới đây, "
            "lưu câu trả lời JSON thành `eval/chuan_mu/claude_N.json`. Lặp 3 lần, mỗi lần một phiên mới (đừng bảo Claude \"làm lại\" trong cùng phiên). "
            "Không sửa tay câu trả lời; nếu JSON hỏng thì chạy lại phiên đó.\n\n"
            "```text\n" + khoi + "\n```\n")


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=TAP, default="dev")
    ap.add_argument("--chi-id", default=None)
    ap.add_argument("--ra", type=Path, default=ROOT / "eval" / "chuan_mu", help="thư mục ghi")
    ap.add_argument("--da-chot", action="store_true", help="bắt buộc với tập đóng băng (đưa chữ câu hỏi đóng băng cho một phiên bên ngoài)")
    args = ap.parse_args(argv)
    if args.tap in TAP_DONG_BANG and not args.da_chot:
        sys.exit(f"LỖI: tập {args.tap!r} là tập đóng băng; không xuất câu hỏi của nó nếu chưa chốt cấu hình (thêm --da-chot).")
    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap, "nhieu_dieu")
        if args.chi_id:
            bo = loc_theo_id(bo, args.chi_id)
    except BoCauHoiError as e:
        sys.exit(f"LỖI: {e}")
    cau = {c["id"]: c["cau_hoi"] for c in bo}                    # CHỈ id và chữ câu hỏi; không có trường dieu
    ghi(args.ra / f"cau_hoi_mu_{args.tap}.json", json.dumps(cau, ensure_ascii=False, indent=1) + "\n")
    ghi(args.ra / "LOI_NHAC_CHUAN_MU.md", loi_nhac(cau))
    print(f"Đã ghi {len(cau)} câu mù [{args.tap}] vào {args.ra} (cau_hoi_mu_{args.tap}.json, LOI_NHAC_CHUAN_MU.md). Không có đáp án Điều.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
