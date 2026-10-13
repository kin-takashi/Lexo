"""Bước 2c: xem trước, duyệt và áp lệnh sửa đổi lên văn bản gốc.

  tong-quan  <so_hieu_dich>                 số lệnh theo luật sửa đổi và trạng thái duyệt
  xem-truoc  <so_hieu_dich> [--luu FILE]    chạy thử trên bản sao trong bộ nhớ (kể cả lệnh chưa duyệt); không đổi CSDL
  bao-cao    <so_hieu_dich> <so_hieu_nguon> [--xuat FILE]   bảng markdown để đối chiếu và duyệt từng lệnh
  duyet      <so_hieu_dich> <so_hieu_nguon> --nguoi TEN [--ghi-chu ...]   duyệt cả lô (chỉ khi xem trước không có lệnh lỗi)
  ap-dung    <so_hieu_dich>                 dựng lại phiên bản từ các lệnh ĐÃ DUYỆT (idempotent, hoàn tác hết nếu có lệnh lỗi)

Ví dụ:  python scripts/apply_commands.py xem-truoc 100/2015/QH13
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.apply.approve import ApproveError, bao_cao_markdown, duyet_theo_lo, tong_quan  # noqa: E402
from src.apply.rebuild import CANH_BAO, RebuildError, preview, rebuild  # noqa: E402
from src.config import db_path, raw_dir  # noqa: E402
from src.store import connect  # noqa: E402


def _print_report(rep, limit: int = 40) -> None:
    print(f"Ngày hiệu lực văn bản gốc: {rep.ngay_hieu_luc_goc}; {len(rep.results)} lệnh: {rep.n_ok} chạy được, {rep.n_loi} lỗi.")
    for r in [r for r in rep.results if not r.ok][:limit]:
        print(f"  ✗ #{r.lenh_id} {r.loai_thao_tac} {r.vi_tri_nguon} (hiệu lực {r.hieu_luc_tu}): {r.problems[0].message}")
    warns = rep.problems(CANH_BAO)
    if warns:
        print(f"{len(warns)} cảnh báo:")
        for r, p in warns[:limit]:
            print(f"  ! #{r.lenh_id} {r.loai_thao_tac} {r.vi_tri_nguon}: {p.message}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):                # cửa sổ/redirect trên Windows có thể không phải UTF-8
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("tong-quan", "xem-truoc", "ap-dung"):
        s = sub.add_parser(name, parents=[common])
        s.add_argument("dich")
        if name == "xem-truoc":
            s.add_argument("--luu", type=Path, help="lưu bản xem trước thành file SQLite để tra thử (scripts/lookup.py --db FILE)")
    for name in ("bao-cao", "duyet"):
        s = sub.add_parser(name, parents=[common])
        s.add_argument("dich")
        s.add_argument("nguon")
        if name == "bao-cao":
            s.add_argument("--xuat", type=Path)
        else:
            s.add_argument("--nguoi", required=True, help="tên người duyệt (ghi vào CSDL)")
            s.add_argument("--ghi-chu", default=None)
    args = ap.parse_args()
    path = args.db or db_path()
    if not path.exists():
        print(f"Chưa có CSDL {path}.", file=sys.stderr)
        return 2
    conn = connect(path)
    try:
        row = conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (args.dich,)).fetchone()
        if row is None:
            print(f"Không có văn bản {args.dich} trong CSDL.", file=sys.stderr)
            return 2
        vb = row["id"]
        if args.cmd == "tong-quan":
            for r in tong_quan(conn, vb):
                print(f"{r['so_hieu']} (ban hành {r['ngay_ban_hanh']}, hiệu lực {r['ngay_hieu_luc']}): {r['tong']} lệnh — "
                      f"chờ duyệt {r['cho_duyet']}, đã duyệt {r['da_duyet']}, từ chối {r['tu_choi']}")
        elif args.cmd == "xem-truoc":
            rep, mem = preview(conn, vb)
            _print_report(rep)
            if args.luu:
                args.luu.parent.mkdir(parents=True, exist_ok=True)
                args.luu.unlink(missing_ok=True)
                mem.execute("VACUUM INTO ?", (str(args.luu),))
                print(f"Đã lưu bản xem trước: {args.luu}")
            mem.close()
            return 0 if rep.n_loi == 0 else 1
        elif args.cmd == "bao-cao":
            text = bao_cao_markdown(conn, args.nguon, vb)
            out = args.xuat or raw_dir() / args.nguon.replace("/", "-") / "lenh_cho_duyet.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"Đã ghi {out}")
        elif args.cmd == "duyet":
            n = duyet_theo_lo(conn, args.nguon, vb, nguoi=args.nguoi, ghi_chu=args.ghi_chu)
            print(f"Đã duyệt {n} lệnh của {args.nguon} (người duyệt: {args.nguoi}). Chạy 'ap-dung' để dựng phiên bản.")
        elif args.cmd == "ap-dung":
            rep = rebuild(conn, vb)
            _print_report(rep)
            hd_ = rep.hieu_dinh
            if hd_.ket_qua:
                print(f"Hiệu đính kỹ thuật: {hd_.n_ap}/{len(hd_.ket_qua)} quy tắc đã duyệt đã áp.")
                for r_ in hd_.khong_ap_duoc():
                    print(f"  ! #{r_.id} {r_.khoa}: không áp được ({'không có nút' if not r_.co_nut else 'không còn chỗ nào chứa từ cũ'})")
            print("Đã dựng lại phiên bản từ các lệnh đã duyệt.")
    except (ApproveError, RebuildError) as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
