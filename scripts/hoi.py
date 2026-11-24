"""Hỏi agent từ dòng lệnh (cùng agent với giao diện src/ui/app_tra_cuu.py).

  python scripts/hoi.py "Điều 173"
  python scripts/hoi.py "khoản 2 Điều 173 tại ngày 01/01/2018"
  python scripts/hoi.py "lịch sử sửa đổi Điều 173"
  python scripts/hoi.py "so sánh Điều 173 bản gốc và hiện hành"
  python scripts/hoi.py "Những luật nào đã sửa đổi Bộ luật Hình sự?"
  python scripts/hoi.py "lén lấy xe máy của hàng xóm"                  # tìm theo mô tả (theo nghĩa nếu có Ollama, không thì theo từ khoá)
  python scripts/hoi.py "<tình huống dài>" --khong-tach                 # không tách hành vi
  python scripts/hoi.py "lén lấy xe máy" --json                         # TraLoi đầy đủ dạng JSON
  python scripts/hoi.py                                                 # hỏi nhiều lượt; gõ dòng trống để thoát
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.agent import Agent, thanh_van_ban  # noqa: E402
from src.agent.cong_cu import CongCu, KhoLoi  # noqa: E402


def main() -> int:
    for s in (sys.stdout, sys.stderr):                        # cửa sổ/redirect trên Windows có thể không phải UTF-8
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cau", nargs="*", help="câu hỏi (bỏ trống: hỏi nhiều lượt)")
    ap.add_argument("--ngay", default=None, help="ngày xem mặc định YYYY-MM-DD khi câu không nêu ngày")
    ap.add_argument("--khong-tach", action="store_true", help="không tách tình huống thành hành vi")
    ap.add_argument("--xep-lai", action="store_true", help="bật bước xếp lại (cần mô hình bge-reranker, xem README Bước 4c)")
    ap.add_argument("-m", type=int, default=None, help="số Điều cho mỗi hành vi (mặc định theo config.yaml, 3)")
    ap.add_argument("-k", type=int, default=5, help="số Điều khi tìm một mô tả (mặc định 5)")
    ap.add_argument("--json", action="store_true", help="in TraLoi dạng JSON")
    ap.add_argument("--gia", action="store_true", help="vector giả + tách giả (chỉ để thử đường ống, kết quả vô nghĩa)")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--index", type=Path, default=None)
    args = ap.parse_args()
    try:
        cc = CongCu.mo(db=args.db, index=args.index, gia=args.gia or None)
    except KhoLoi as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    ag = Agent(cc)
    for w in cc.canh_bao_khoi_dong:
        print(f"Lưu ý: {w}", file=sys.stderr)

    def hoi(cau: str) -> None:
        tl = ag.hoi(cau, ngay=args.ngay, tach=not args.khong_tach, xep_lai=True if args.xep_lai else None, m=args.m, k=args.k)
        print(json.dumps(tl.to_dict(), ensure_ascii=False, indent=1, default=str) if args.json else thanh_van_ban(tl))

    if args.cau:
        hoi(" ".join(args.cau))
        return 0
    for t in cc.trang_thai():
        print(f"[{'x' if t['ok'] else ' '}] {t['ten']}: {t['mo_ta']}")
    print("Gõ câu hỏi (dòng trống để thoát).")
    while True:
        try:
            cau = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cau:
            break
        hoi(cau)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
