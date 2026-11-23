"""Ghi hiệu lực của cả một bộ luật: hoãn ngày bắt đầu (nghị quyết) hoặc ngày hết hiệu lực (bị bộ luật mới thay).

  xem                                  các bộ luật chính trong kho và khoảng hiệu lực của từng bộ
  hoan  --dich SỐ_HIỆU --ngay-moi YYYY-MM-DD --nguon SỐ_HIỆU_NGHỊ_QUYẾT --ten-nguon "..." --ngay-ban-hanh YYYY-MM-DD
        --can-cu "..." --nguoi TÊN [--hieu-luc-tu YYYY-MM-DD] [--vi-tri "Điều 1"] [--ghi-chu "..."] [--ap-dung]
  het   --so-hieu SỐ_HIỆU --ngay-het YYYY-MM-DD [--thay-boi SỐ_HIỆU] [--ap-dung]

Mặc định chỉ CHẠY THỬ trên bản sao trong bộ nhớ và in ra thay đổi; không ghi gì vào CSDL. Thêm --ap-dung để ghi thật
(tự sao lưu db/luat.sqlite.bak-THỜI-GIAN trước). Sau khi áp dụng, chạy lại scripts/build_index.py để chỉ mục tìm kiếm theo đúng khoảng hiệu lực mới.

Ví dụ (BLHS 2015 bắt đầu có hiệu lực từ 01/01/2018, theo Nghị quyết 41/2017/QH14 Điều 1 khoản 1 điểm a):
  python scripts/hoan_hieu_luc.py hoan --dich 100/2015/QH13 --ngay-moi 2018-01-01 --nguon 41/2017/QH14 ^
      --ten-nguon "Nghị quyết số 41/2017/QH14 về việc thi hành Bộ luật hình sự số 100/2015/QH13 ..." ^
      --ngay-ban-hanh 2017-06-20 --hieu-luc-tu 2017-07-05 --vi-tri "Điều 1 khoản 1 điểm a" ^
      --can-cu "Điều 1 khoản 1 điểm a Nghị quyết 41/2017/QH14: từ 01/01/2018 BLHS 2015 có hiệu lực" --nguoi "Tên bạn"
Ví dụ (BLHS 1999 hết hiệu lực khi BLHS 2015 bắt đầu có hiệu lực; sau khi đã nạp BLHS 1999):
  python scripts/hoan_hieu_luc.py het --so-hieu 15/1999/QH10 --ngay-het 2018-01-01 --thay-boi 100/2015/QH13
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.apply.hieu_luc_vb import HieuLucError, dat_het_hieu_luc, ghi_hoan_hieu_luc  # noqa: E402
from src.apply.rebuild import RebuildError  # noqa: E402
from src.config import db_path  # noqa: E402
from src.query.lookup import fmt_date, ngay_cuoi_hieu_luc, van_ban_goc  # noqa: E402
from src.store import connect  # noqa: E402


def _cua_so(conn: sqlite3.Connection, so_hieu: str) -> dict[int, tuple]:
    """{phiên bản id: (hiệu lực từ, đến)} của mọi nút trong văn bản, để đếm số khoảng hiệu lực bị đổi."""
    return {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT p.id, p.hieu_luc_tu, p.hieu_luc_den FROM phien_ban_noi_dung p JOIN don_vi_luat d ON d.id = p.don_vi_id "
        "JOIN van_ban v ON v.id = d.van_ban_id WHERE v.so_hieu = ?", (so_hieu,))}


def _in_bang(conn: sqlite3.Connection) -> None:
    rows = van_ban_goc(conn)
    if not rows:
        print("Chưa có bộ luật chính nào trong kho.")
        return
    print(f"{'Số hiệu':<16}{'Viết tắt':<10}{'Có hiệu lực từ':<16}{'Hiệu lực đến (gồm)':<20}Theo văn bản")
    for r in rows:
        print(f"{r['so_hieu']:<16}{r['ten_viet_tat']:<10}{fmt_date(r['ngay_hieu_luc']):<16}"
              f"{fmt_date(ngay_cuoi_hieu_luc(r)) if r['ngay_het_hieu_luc'] else 'đang hiệu lực':<20}{fmt_date(r['ngay_hieu_luc_theo_van_ban'])}")


def _tom_tat(truoc: dict, sau: dict) -> str:
    doi = [k for k in sau if truoc.get(k) != sau[k]]
    mau = "; ".join(f"{truoc[k][0]}→{sau[k][0]} / {truoc[k][1]}→{sau[k][1]}" for k in doi[:3])
    return f"{len(doi)}/{len(sau)} phiên bản đổi khoảng hiệu lực" + (f" (vd {mau})" if doi else "")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("xem")
    h = sub.add_parser("hoan")
    h.add_argument("--dich", required=True)
    h.add_argument("--ngay-moi", required=True)
    h.add_argument("--nguon", required=True)
    h.add_argument("--ten-nguon", required=True)
    h.add_argument("--ngay-ban-hanh", required=True)
    h.add_argument("--hieu-luc-tu", default=None)
    h.add_argument("--can-cu", required=True)
    h.add_argument("--nguoi", required=True)
    h.add_argument("--vi-tri", default=None)
    h.add_argument("--ghi-chu", default=None)
    k = sub.add_parser("het")
    k.add_argument("--so-hieu", required=True)
    k.add_argument("--ngay-het", required=True)
    k.add_argument("--thay-boi", default=None)
    for s in (h, k):
        s.add_argument("--ap-dung", action="store_true", help="ghi thật vào CSDL (mặc định: chạy thử trên bản sao)")
    args = ap.parse_args()
    path = args.db or db_path()
    if not Path(path).exists():
        print(f"Không thấy CSDL {path}", file=sys.stderr)
        return 2
    real = connect(path)
    if args.cmd == "xem":
        _in_bang(real)
        return 0

    dich = args.dich if args.cmd == "hoan" else args.so_hieu
    if real.execute("SELECT 1 FROM van_ban WHERE so_hieu = ?", (dich,)).fetchone() is None:
        print(f"Chưa có văn bản {dich} trong CSDL.", file=sys.stderr)
        return 2
    if args.ap_dung:
        bak = Path(path).with_name(Path(path).name + datetime.now().strftime(".bak-%Y%m%d-%H%M%S"))
        real.close()                                  # sao chép nguyên tệp (CSDL không có tiến trình khác dùng); không dùng sqlite3.backup vì nó tạo
        shutil.copy2(path, bak)                       # tệp -journal tạm cạnh bản sao, ổ chia sẻ có thể từ chối ("disk I/O error")
        if bak.stat().st_size != Path(path).stat().st_size:
            print("[LỖI] Sao lưu không đủ dung lượng, dừng lại.", file=sys.stderr)
            return 1
        real = connect(path)
        print(f"[OK] Đã sao lưu CSDL: {bak.name}")
        conn = real
    else:
        conn = connect(":memory:")
        real.backup(conn)
    truoc = _cua_so(conn, dich)
    try:
        if args.cmd == "hoan":
            r = ghi_hoan_hieu_luc(conn, args.dich, args.ngay_moi, so_hieu_nguon=args.nguon, ten_nguon=args.ten_nguon,
                                  ngay_ban_hanh_nguon=args.ngay_ban_hanh, can_cu=args.can_cu, nguoi=args.nguoi, hieu_luc_tu=args.hieu_luc_tu,
                                  vi_tri_nguon=args.vi_tri, ghi_chu=args.ghi_chu, commit=args.ap_dung)
            if r["da_co"]:
                print(f"Lệnh hoãn hiệu lực này đã có (#{r['lenh_id']}); không có gì để làm.")
                return 0
            print(f"Ngày bắt đầu hiệu lực của {args.dich}: {fmt_date(r['ngay_cu'])} → {fmt_date(r['ngay_moi'])} (theo {args.nguon}, lệnh #{r['lenh_id']}).")
        else:
            r = dat_het_hieu_luc(conn, args.so_hieu, args.ngay_het, thay_boi=args.thay_boi, commit=args.ap_dung)
            print(f"{args.so_hieu} hết hiệu lực từ {fmt_date(r['ngay_het'])} (ngày cuối còn hiệu lực: {fmt_date(ngay_cuoi_hieu_luc(conn.execute('SELECT * FROM van_ban WHERE id = ?', (r['van_ban_id'],)).fetchone()))}).")
            for w in r["canh_bao"]:
                print("  ! " + w)
    except HieuLucError as e:
        print(f"[LỖI] {e}", file=sys.stderr)
        return 1
    except RebuildError as e:
        print(f"[LỖI] dựng lại phiên bản thất bại, CSDL không đổi:\n{e}", file=sys.stderr)
        return 1
    rep = r["bao_cao"]
    print(f"Dựng lại {dich}: {rep.n_ok} lệnh chạy được, {rep.n_loi} lỗi; " + _tom_tat(truoc, _cua_so(conn, dich)))
    if args.ap_dung:
        print("[OK] Đã ghi vào CSDL. Chạy tiếp: python scripts/build_index.py  (cập nhật khoảng hiệu lực trong chỉ mục tìm kiếm)")
    else:
        print("(chạy thử, chưa ghi gì; thêm --ap-dung để ghi thật)")
    _in_bang(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
