"""Bước 2b: trích LỆNH SỬA ĐỔI từ luật sửa đổi đã parse (raw/<slug>/amending.json), ghi commands.json và (tuỳ chọn) nạp vào CSDL
ở trạng thái chờ duyệt. Không dùng LLM. Mục nào không hiểu được sẽ được liệt kê để người dùng xử lý tay — không tự đoán.

Ví dụ:  python scripts/extract_commands.py 12-2017-QH14 86-2025-QH15 59-2024-QH15            # chỉ trích + xem độ phủ
        python scripts/extract_commands.py 12-2017-QH14 86-2025-QH15 59-2024-QH15 --nap      # trích rồi nạp (chờ duyệt)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import amending_scope, db_path, raw_dir  # noqa: E402
from src.extract.regex_extractor import extract_commands  # noqa: E402
from src.ingest.amending_commands import load_extraction  # noqa: E402
from src.ingest.amending_law import load_amending  # noqa: E402
from src.ingest.base_law import IngestError  # noqa: E402
from src.store import connect, init_db  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):                # cửa sổ/redirect trên Windows có thể không phải UTF-8
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="+", help="thư mục trong raw/ của luật sửa đổi, vd 12-2017-QH14")
    ap.add_argument("--dich", default=None, help="số hiệu văn bản bị sửa (mặc định: văn bản đầu tiên trong pham_vi_sua_doi của config.yaml)")
    ap.add_argument("--nap", action="store_true", help="nạp lệnh vào CSDL (trạng thái chờ duyệt)")
    ap.add_argument("--thay", action="store_true", help="nạp lại, thay các lệnh chờ duyệt cũ (không thay nếu đã có lệnh được duyệt/từ chối)")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    _, scope = amending_scope()
    dich = args.dich or (sorted(scope)[0] if scope else None)
    if args.nap and not dich:
        print("Chưa biết văn bản đích: điền pham_vi_sua_doi.van_ban trong config.yaml hoặc dùng --dich.", file=sys.stderr)
        return 2
    conn = None
    if args.nap:
        path = args.db or db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(path)
        init_db(conn)
    rc = 0
    try:
        for slug in args.slug:
            directory = raw_dir() / slug
            src = directory / "amending.json"
            if not src.exists():
                print(f"[{slug}] thiếu {src}; chạy scripts/parse_amending_law.py trước.", file=sys.stderr)
                rc = 2
                continue
            law = load_amending(src)
            res = extract_commands(law)
            (directory / "commands.json").write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            kinds: dict[str, int] = {}
            for c in res.commands:
                kinds[c.loai_thao_tac] = kinds.get(c.loai_thao_tac, 0) + 1
            print(f"[{law.meta.so_hieu}] {res.n_parsed_leaf}/{res.n_leaf} mục lệnh trong phạm vi được hiểu ({res.coverage():.1%}); "
                  f"{len(res.commands)} lệnh: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
            for u in res.unparsed:
                print(f"    CHƯA HIỂU {u.vi_tri_nguon}: {u.reason} — {u.text[:140]}")
                rc = max(rc, 1)
            if conn is not None:
                try:
                    st = load_extraction(conn, law, res, van_ban_dich_so_hieu=dich, file_nguon=law.source.get("name", slug),
                                         duong_dan_raw=str(directory), thay_lenh_cho_duyet=args.thay)
                except IngestError as e:
                    print(f"    LỖI nạp: {e}", file=sys.stderr)
                    rc = 2
                    continue
                print(f"    đã nạp {st['so_lenh']} lệnh chờ duyệt vào {conn.execute('PRAGMA database_list').fetchone()[2]}")
    finally:
        if conn is not None:
            conn.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
