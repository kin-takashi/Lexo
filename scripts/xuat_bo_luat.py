"""Xuất bản hợp nhất của một bộ luật tại một ngày (mặc định: hôm nay) ra Markdown và/hoặc Word.

  python scripts/xuat_bo_luat.py                                  # BLHS 2015 hôm nay -> xuat/BLHS-100-2015-QH13_<ngày>.md và .docx
  python scripts/xuat_bo_luat.py --ngay 2018-01-01 --dinh-dang md
  python scripts/xuat_bo_luat.py --khong-doi-chieu                 # không đối chiếu lại với văn bản hợp nhất khi xuất
  python scripts/xuat_bo_luat.py --xem-truoc                       # CHƯA DUYỆT: chạy thử trên bản sao, gồm cả lệnh/hiệu đính chờ duyệt (ghi rõ trong file)

Bản xuất ghi rõ: các văn bản đã hợp nhất, nguồn sửa đổi từng Điều, hiệu đính kỹ thuật đã áp (kèm người duyệt) và kết quả đối chiếu tự động
với văn bản hợp nhất chính thức (nếu raw/<văn bản hợp nhất>/vbhn.json có; xem scripts/doi_chieu_vbhn.py). Chỉ đọc CSDL.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.apply.rebuild import preview  # noqa: E402
from src.config import db_path, raw_dir  # noqa: E402
from src.query.xuat import dung_bo_luat, ra_docx, ra_markdown  # noqa: E402
from src.store import connect  # noqa: E402
from src.validate.vbhn import compare, items_from_db, nap_vbhn_json  # noqa: E402


def doi_chieu(conn, vb: int, ngay: str, slug: str) -> dict | None:
    p = raw_dir() / slug / "vbhn.json"
    if not p.exists():
        return None
    theirs, rep = nap_vbhn_json(p)
    res = compare(items_from_db(conn, vb, ngay), theirs, rep)
    return {"nhan": slug.replace("-", "/", 1), "ngay": ngay, "n_theirs": res.n_theirs, "n_match": res.n_match, "n_match_fold": res.n_match_fold,
            "n_noi_dung": sum(1 for d in res.diffs if d.kind != "khac_trinh_bay"),
            "n_trinh_bay": sum(1 for d in res.diffs if d.kind == "khac_trinh_bay"),
            "dieu_lech": [k.removeprefix("dieu ") for k in res.dieu_with_diffs() if k.startswith("dieu ")]
            + [k for k in res.dieu_with_diffs() if not k.startswith("dieu ")]}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dich", default="100/2015/QH13", help="số hiệu văn bản (mặc định BLHS 2015)")
    ap.add_argument("--ngay", default=None, help="ngày hiệu lực cần xuất, YYYY-MM-DD (mặc định: hôm nay)")
    ap.add_argument("--dinh-dang", nargs="+", choices=("md", "docx"), default=["md", "docx"])
    ap.add_argument("--ra", type=Path, default=ROOT / "xuat", help="thư mục ghi file (mặc định: xuat/)")
    ap.add_argument("--vbhn", default="135-VBHN-VPQH", help="thư mục trong raw/ của văn bản hợp nhất dùng để đối chiếu")
    ap.add_argument("--khong-doi-chieu", action="store_true")
    ap.add_argument("--xem-truoc", action="store_true", help="bản xem trước: áp cả lệnh sửa đổi và hiệu đính CHƯA duyệt (trên bản sao trong bộ nhớ)")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    path = args.db or db_path()
    if not path.exists():
        print(f"Chưa có CSDL {path}.", file=sys.stderr)
        return 2
    ngay = args.ngay or date.today().isoformat()
    conn = connect(path)
    try:
        row = conn.execute("SELECT id, ten_viet_tat FROM van_ban WHERE so_hieu = ?", (args.dich,)).fetchone()
        if row is None:
            print(f"Không có văn bản {args.dich} trong CSDL.", file=sys.stderr)
            return 2
        mem = None
        src = conn
        if args.xem_truoc:
            rep, mem = preview(conn, row["id"])
            src = mem
            if rep.n_loi:
                print(f"Cảnh báo: {rep.n_loi} lệnh không chạy được trong bản xem trước (xem scripts/apply_commands.py xem-truoc).", file=sys.stderr)
        dc = None if args.khong_doi_chieu else doi_chieu(src, row["id"], ngay, args.vbhn)
        bl = dung_bo_luat(src, row["id"], ngay, dc, xem_truoc=args.xem_truoc)
        if mem is not None:
            mem.close()
        if not bl.roots:
            print(f"Văn bản {args.dich} không có nội dung nào có hiệu lực tại ngày {ngay}.", file=sys.stderr)
            return 1
        stem = f"{row['ten_viet_tat'] or 'VB'}-{args.dich.replace('/', '-')}_{ngay}" + ("_XEM-TRUOC" if args.xem_truoc else "")
        args.ra.mkdir(parents=True, exist_ok=True)
        if "md" in args.dinh_dang:
            f = args.ra / f"{stem}.md"
            f.write_text(ra_markdown(bl), encoding="utf-8")
            print(f"Đã ghi {f}")
        if "docx" in args.dinh_dang:
            print(f"Đã ghi {ra_docx(bl, args.ra / (stem + '.docx'))}")
        print(f"{bl.n_dieu} Điều có hiệu lực tại {ngay}, {bl.n_dieu_da_sua} Điều có sửa đổi; {len(bl.hieu_dinh)} hiệu đính kỹ thuật đã áp"
              + (f"; đối chiếu {dc['nhan']}: {dc['n_match_fold']}/{dc['n_theirs']} nút khớp, {dc['n_noi_dung']} chỗ khác nội dung" if dc else "; chưa đối chiếu"))
        if args.xem_truoc:
            print(f"BẢN XEM TRƯỚC: đã gồm {bl.lenh_cho_duyet} lệnh sửa đổi và {bl.hieu_dinh_cho_duyet} quy tắc hiệu đính CHƯA được người duyệt.")
        elif bl.lenh_cho_duyet or bl.hieu_dinh_cho_duyet:
            print(f"Lưu ý: còn {bl.lenh_cho_duyet} lệnh sửa đổi và {bl.hieu_dinh_cho_duyet} đề xuất hiệu đính chưa duyệt (chưa nằm trong bản xuất).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
