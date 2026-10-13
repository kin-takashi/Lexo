"""Tìm điều luật theo mô tả bằng lời (cần đã chạy scripts/build_index.py).

  python scripts/tim_kiem.py "mượn tiền rồi bỏ trốn không trả"
  python scripts/tim_kiem.py "lén lấy xe máy" --ngay 2017-12-31      # theo bản có hiệu lực tại ngày đó
  python scripts/tim_kiem.py "cất giữ ma túy" --che-do vector        # hoặc fts, hybrid; mặc định là vector theo số đo
  python scripts/tim_kiem.py "cất giữ ma túy" --chunk                # xem từng đoạn thay vì gộp theo Điều
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import db_path, index_path, load_config  # noqa: E402
from src.index.chunks import build_chunks, van_tay  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.search import CHE_DO, MAC_DINH, gop_theo_dieu, tim  # noqa: E402
from src.index.store import open_index, van_tay_da_luu  # noqa: E402


def cat(s: str, n: int = 150) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cau_hoi")
    ap.add_argument("--ngay", default=None, help="YYYY-MM-DD (mặc định hôm nay)")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--che-do", choices=CHE_DO, default=MAC_DINH)
    ap.add_argument("--dung-cau-hoi", dest="he_so_cau_hoi", type=float, default=0.0, metavar="HE_SO",
                    help="dùng câu hỏi sinh sẵn (scripts/sinh_cau_hoi.py) với hệ số này, vd 0.9; 0 = không dùng")
    ap.add_argument("--chunk", action="store_true", help="hiện từng đoạn, không gộp theo Điều")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true", help="dùng vector giả (chỉ để thử đường ống)")
    ap.add_argument("--khong-kiem-tra-cu", action="store_true", help="không so với CSDL luật xem chỉ mục đã cũ chưa")
    args = ap.parse_args()

    ngay = args.ngay or date.today().isoformat()
    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    idx = open_index(ip)
    emb = HashEmbedder() if args.gia else tu_config(load_config(), model=args.model, endpoint=args.endpoint)

    if not args.khong_kiem_tra_cu and db_path().exists():                                 # chỉ mục có còn khớp CSDL luật không
        try:
            mc = sqlite3.connect(f"{db_path().resolve().as_uri()}?mode=ro", uri=True)
            mc.row_factory = sqlite3.Row
            vb = mc.execute("SELECT id FROM van_ban WHERE so_hieu = '100/2015/QH13'").fetchone()
            if vb and van_tay(build_chunks(mc, vb["id"])) != van_tay_da_luu(idx):
                print("CẢNH BÁO: CSDL luật đã đổi so với lúc dựng chỉ mục. Chạy lại scripts/build_index.py (chỉ tính lại phần đổi).", file=sys.stderr)
            mc.close()
        except sqlite3.Error:
            pass

    try:
        kq = tim(idx, args.cau_hoi, embedder=emb, ngay=ngay, k=max(args.k * 4, 20) if not args.chunk else args.k, che_do=args.che_do, he_so_cau_hoi=args.he_so_cau_hoi)
    except (EmbedError, ValueError) as e:
        sys.exit(f"LỖI: {e}")
    print(f"Câu hỏi: {args.cau_hoi}\n(bản có hiệu lực tại ngày {ngay}; chế độ {args.che_do}; mô hình {emb.name})")
    for w in kq.canh_bao:
        print(f"Lưu ý: {w}")
    if not kq.hits:
        print("Không tìm thấy kết quả.")
        return 0

    def dong_hang(h) -> str:
        v = f"vector {h.cosine:.3f} (hạng {h.hang_vector})" if h.hang_vector else "vector -"
        f = f"từ khoá hạng {h.hang_fts}" if h.hang_fts else "từ khoá -"
        return f"{v} | {f}"

    if args.chunk:
        for i, h in enumerate(kq.hits[: args.k], 1):
            print(f"\n{i}. {h.key}  [điểm {h.diem:.4f}]\n   {cat(h.noi_dung) if h.noi_dung else cat(h.text)}\n   {dong_hang(h)}")
    else:
        for i, d in enumerate(gop_theo_dieu(kq.hits, args.k), 1):
            h = d.doan_noi_dung or d.tot_nhat
            chu = cat(h.noi_dung) if h.noi_dung else "(khớp tiêu đề Điều; nội dung nằm ở các khoản)"
            print(f"\n{i}. {d.tieu_de}  [điểm {d.diem:.4f}, {d.so_doan} đoạn ứng viên]\n   đoạn nội dung tốt nhất: {h.key}\n   {chu}\n   {dong_hang(h)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
